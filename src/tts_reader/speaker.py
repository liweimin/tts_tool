from __future__ import annotations

import asyncio
import ctypes
from datetime import timezone as _tz
from email.utils import parsedate_to_datetime as _parsedate_to_datetime
import logging
import os
from pathlib import Path
import tempfile
import threading
import time

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
import pythoncom
import edge_tts
import edge_tts.communicate as _edge_communicate
import edge_tts.constants as _edge_constants
from edge_tts.drm import DRM as _EdgeDRM


_LOGGER = logging.getLogger(__name__)
_WINMM = ctypes.windll.winmm

_EDGE_TOKEN = getattr(_edge_constants, "TRUSTED_CLIENT_TOKEN", "6A5AA1D4EAFF4E9FB37E23D68491D6F4")
_EDGE_WSS_URL_PRIMARY = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    f"?Ocp-Apim-Subscription-Key={_EDGE_TOKEN}"
)
_EDGE_WSS_URL_LEGACY = getattr(
    _edge_constants,
    "WSS_URL",
    f"wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken={_EDGE_TOKEN}",
)


def _parse_rfc2616_date_safe(date: str) -> float | None:
    """Locale-independent RFC 2616 HTTP Date parser for Edge-TTS clock skew handling."""
    try:
        parsed = _parsedate_to_datetime(date)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_tz.utc)
    return parsed.timestamp()


def _set_edge_wss_url(url: str) -> None:
    _edge_constants.WSS_URL = url
    _edge_communicate.WSS_URL = url


_EdgeDRM.parse_rfc2616_date = staticmethod(_parse_rfc2616_date_safe)
_set_edge_wss_url(_EDGE_WSS_URL_PRIMARY)


def _format_edge_rate(rate: int) -> str:
    """Convert SAPI-style rate (~180 baseline) to Edge-TTS percentage format (e.g. +0%, +20%, -15%)."""
    if rate == 180:
        return "+0%"
    if rate > 180:
        pct = int(round((rate - 180) / 180.0 * 100))
        return f"+{pct}%"
    pct = int(round((180 - rate) / 180.0 * 100))
    return f"-{pct}%"


def _mci_send(cmd: str) -> tuple[int, str]:
    buf = ctypes.create_unicode_buffer(128)
    err = _WINMM.mciSendStringW(cmd, buf, 128, None)
    return err, buf.value


def _stop_and_close_mci(alias: str) -> None:
    _WINMM.mciSendStringW(f"stop {alias}", None, 0, None)
    _WINMM.mciSendStringW(f"close {alias}", None, 0, None)


class Speaker:
    def __init__(
        self,
        rate: int = 180,
        voice_contains: str = "",
        engine: str = "edge",
        edge_voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> None:
        self._rate = rate
        self._voice_contains = voice_contains.strip().lower()
        self._engine_type = engine.strip().lower() or "edge"
        self._edge_voice = edge_voice.strip() or "zh-CN-XiaoxiaoNeural"

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._request_event = threading.Event()
        self._state_lock = threading.Lock()

        self._pending_text: str | None = None
        self._pending_rate: int | None = None
        self._pending_voice_contains: str | None = None
        self._pending_engine: str | None = None
        self._pending_edge_voice: str | None = None

        self._interrupt_only = False
        self._is_speaking = False
        self._generation = 0
        self._startup_error: Exception | None = None

        # SAPI COM objects
        self._sapi_engine: pyttsx3.Engine | None = None
        self._default_voice_id: str | None = None

        # Active async task for Edge-TTS
        self._active_loop: asyncio.AbstractEventLoop | None = None
        self._active_async_task: asyncio.Task | None = None

        # Temp directory for Edge-TTS audio files
        self._temp_dir = Path(tempfile.gettempdir()) / "tts_reader"
        try:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            _LOGGER.warning("Could not create temp dir %s", self._temp_dir, exc_info=True)

        self._mci_alias = f"tts_reader_mci_{os.getpid()}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=5.0)
        if self._startup_error:
            raise RuntimeError("Failed to start speech engine") from self._startup_error

    def speak(self, text: str) -> None:
        if not text:
            return
        with self._state_lock:
            self._generation += 1
            self._pending_text = text
            self._interrupt_only = False
            self._is_speaking = True
            self._stop_active_playback_locked()
        self._request_event.set()
        _LOGGER.info("Speech request received (gen=%s): %s chars.", self._generation, len(text))

    def interrupt(self) -> None:
        with self._state_lock:
            self._generation += 1
            self._pending_text = None
            self._interrupt_only = True
            self._is_speaking = False
            self._stop_active_playback_locked()
        self._request_event.set()
        _LOGGER.info("Speech interrupt requested (gen=%s).", self._generation)

    def stop(self) -> None:
        self._stop_event.set()
        self.interrupt()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def update_settings(
        self,
        rate: int,
        voice_contains: str,
        engine: str = "edge",
        edge_voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> None:
        with self._state_lock:
            self._pending_rate = rate
            self._pending_voice_contains = voice_contains.strip().lower()
            self._pending_engine = engine.strip().lower() or "edge"
            self._pending_edge_voice = edge_voice.strip() or "zh-CN-XiaoxiaoNeural"
        self._request_event.set()
        _LOGGER.info(
            "Speaker settings update requested: rate=%s voice_contains=%s engine=%s edge_voice=%s",
            rate,
            voice_contains,
            engine,
            edge_voice,
        )

    def _stop_active_playback_locked(self) -> None:
        _stop_and_close_mci(self._mci_alias)
        if self._active_loop and self._active_async_task and not self._active_async_task.done():
            try:
                self._active_loop.call_soon_threadsafe(self._active_async_task.cancel)
            except Exception:
                pass
        if self._sapi_engine:
            try:
                self._sapi_engine.stop()
            except Exception:
                pass

    def _run(self) -> None:
        pythoncom.CoInitialize()
        try:
            self._init_sapi()
        except Exception as exc:
            _LOGGER.warning("SAPI init failed (offline speech may not work): %s", exc)

        self._ready_event.set()
        _LOGGER.info(
            "Speaker thread started. engine=%s edge_voice=%s rate=%s",
            self._engine_type,
            self._edge_voice,
            self._rate,
        )

        while not self._stop_event.is_set():
            self._apply_pending_settings()

            text = None
            gen = 0
            with self._state_lock:
                if self._request_event.is_set():
                    self._request_event.clear()
                    if not self._interrupt_only:
                        text = self._pending_text
                        gen = self._generation
                        self._pending_text = None
                    self._interrupt_only = False

            if text:
                self._handle_speech_request(text, gen)

            # Wait for next event or timeout
            self._request_event.wait(timeout=0.05)

        self._cleanup()
        pythoncom.CoUninitialize()
        _LOGGER.info("Speaker stopped.")

    def _init_sapi(self) -> None:
        if pyttsx3 is None:
            _LOGGER.warning("pyttsx3 is not installed, SAPI offline fallback unavailable.")
            return
        engine = pyttsx3.init()
        self._default_voice_id = str(engine.getProperty("voice"))
        engine.setProperty("rate", self._rate)
        self._apply_sapi_voice_preference(engine, self._voice_contains)
        self._sapi_engine = engine
        _LOGGER.info("SAPI engine initialized. default_voice=%s", self._default_voice_id)

    def _apply_pending_settings(self) -> None:
        with self._state_lock:
            pending_rate = self._pending_rate
            pending_voice = self._pending_voice_contains
            pending_engine = self._pending_engine
            pending_edge_voice = self._pending_edge_voice
            self._pending_rate = None
            self._pending_voice_contains = None
            self._pending_engine = None
            self._pending_edge_voice = None

        if all(x is None for x in (pending_rate, pending_voice, pending_engine, pending_edge_voice)):
            return

        if pending_rate is not None:
            self._rate = pending_rate
            if self._sapi_engine:
                try:
                    self._sapi_engine.setProperty("rate", pending_rate)
                except Exception:
                    pass

        if pending_voice is not None:
            self._voice_contains = pending_voice
            if self._sapi_engine:
                self._apply_sapi_voice_preference(self._sapi_engine, pending_voice)

        if pending_engine is not None:
            self._engine_type = pending_engine

        if pending_edge_voice is not None:
            self._edge_voice = pending_edge_voice

        _LOGGER.info(
            "Speaker settings applied: rate=%s engine=%s edge_voice=%s sapi_voice_contains=%s",
            self._rate,
            self._engine_type,
            self._edge_voice,
            self._voice_contains,
        )

    def _apply_sapi_voice_preference(self, engine: pyttsx3.Engine, voice_contains: str) -> None:
        if voice_contains:
            for voice in engine.getProperty("voices"):
                content = f"{voice.id} {voice.name}".lower()
                if voice_contains in content:
                    engine.setProperty("voice", voice.id)
                    return
        elif self._default_voice_id:
            engine.setProperty("voice", self._default_voice_id)

    def _is_gen_active(self, gen: int) -> bool:
        with self._state_lock:
            return gen == self._generation and not self._stop_event.is_set()

    def _handle_speech_request(self, text: str, gen: int) -> None:
        if not self._is_gen_active(gen):
            with self._state_lock:
                if gen == self._generation:
                    self._is_speaking = False
            return

        with self._state_lock:
            self._is_speaking = True
        _LOGGER.info("Speech playback starting for gen=%s, engine=%s", gen, self._engine_type)

        try:
            if self._engine_type == "edge":
                success = self._speak_edge_with_fallback(text, gen)
                if not success and self._is_gen_active(gen):
                    _LOGGER.warning("Edge-TTS unsuccessful, falling back to SAPI5 for gen=%s", gen)
                    self._speak_sapi(text, gen)
            else:
                self._speak_sapi(text, gen)
        finally:
            with self._state_lock:
                if gen == self._generation:
                    self._is_speaking = False
            _LOGGER.info("Speech playback completed or interrupted for gen=%s", gen)

    def _speak_edge_with_fallback(self, text: str, gen: int) -> bool:
        edge_file = self._temp_dir / f"tts_{os.getpid()}_{gen}.mp3"
        rate_str = _format_edge_rate(self._rate)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._state_lock:
            self._active_loop = loop

        try:
            synth_coro = self._async_edge_synthesize(text, self._edge_voice, rate_str, edge_file, gen)
            task = loop.create_task(synth_coro)
            with self._state_lock:
                self._active_async_task = task

            try:
                synthesized = loop.run_until_complete(task)
            except asyncio.CancelledError:
                _LOGGER.info("Edge-TTS task cancelled for gen=%s", gen)
                _cleanup_file(edge_file)
                return False
            except Exception as exc:
                _LOGGER.warning("Edge-TTS synthesis error (%s): %s", type(exc).__name__, exc)
                _cleanup_file(edge_file)
                return False
            finally:
                with self._state_lock:
                    self._active_async_task = None
        finally:
            with self._state_lock:
                self._active_loop = None
            try:
                loop.close()
            except Exception:
                pass

        if not synthesized or not self._is_gen_active(gen):
            _cleanup_file(edge_file)
            return False

        try:
            return self._play_audio_mci(edge_file, gen)
        finally:
            _cleanup_file(edge_file)

    async def _async_edge_synthesize(
        self, text: str, voice: str, rate: str, output_file: Path, gen: int
    ) -> bool:
        endpoints = [_EDGE_WSS_URL_PRIMARY, _EDGE_WSS_URL_LEGACY]
        last_exc: Exception | None = None

        for idx, url in enumerate(endpoints):
            if not self._is_gen_active(gen):
                return False
            _set_edge_wss_url(url)
            try:
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                with open(output_file, "wb") as f:
                    async for chunk in communicate.stream():
                        if not self._is_gen_active(gen):
                            return False
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                if output_file.exists() and output_file.stat().st_size > 0:
                    return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                _cleanup_file(output_file)
                if idx == 0 and self._is_gen_active(gen):
                    _LOGGER.warning(
                        "Primary Edge-TTS endpoint failed (%s: %s), retrying legacy endpoint...",
                        type(exc).__name__,
                        exc,
                    )

        _set_edge_wss_url(_EDGE_WSS_URL_PRIMARY)
        if last_exc is not None:
            raise last_exc
        return False

    def _play_audio_mci(self, audio_path: Path, gen: int) -> bool:
        if not self._is_gen_active(gen):
            return False

        _stop_and_close_mci(self._mci_alias)
        abs_path = str(audio_path.resolve())

        open_cmd = f'open "{abs_path}" type mpegvideo alias {self._mci_alias}'
        err, _ = _mci_send(open_cmd)
        if err != 0:
            _LOGGER.error("Failed to open audio via MCI (error code %s)", err)
            return False

        play_err, _ = _mci_send(f"play {self._mci_alias}")
        if play_err != 0:
            _LOGGER.error("Failed to play audio via MCI (error code %s)", play_err)
            _stop_and_close_mci(self._mci_alias)
            return False

        # Wait for playback completion or interruption
        while self._is_gen_active(gen):
            _, mode = _mci_send(f"status {self._mci_alias} mode")
            if mode.strip().lower() in ("stopped", ""):
                break
            time.sleep(0.02)

        _stop_and_close_mci(self._mci_alias)
        return True

    def _speak_sapi(self, text: str, gen: int) -> None:
        if not self._sapi_engine:
            _LOGGER.error("SAPI engine not available for speech")
            return

        if not self._is_gen_active(gen):
            return

        try:
            self._sapi_engine.say(text)
            self._sapi_engine.startLoop(False)
            while self._is_gen_active(gen):
                self._sapi_engine.iterate()
                time.sleep(0.01)
                if not self._sapi_engine.isBusy():
                    break
        except Exception:
            _LOGGER.exception("SAPI speech error")
        finally:
            try:
                self._sapi_engine.stop()
            except Exception:
                pass
            try:
                self._sapi_engine.endLoop()
            except Exception:
                pass

    def _cleanup(self) -> None:
        _stop_and_close_mci(self._mci_alias)
        if self._sapi_engine:
            try:
                self._sapi_engine.stop()
            except Exception:
                pass


def _cleanup_file(file_path: Path) -> None:
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass
