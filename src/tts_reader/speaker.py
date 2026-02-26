from __future__ import annotations

import logging
import threading
import time

import pyttsx3
import pythoncom


_LOGGER = logging.getLogger(__name__)


class Speaker:
    def __init__(self, rate: int, voice_contains: str = "") -> None:
        self._rate = rate
        self._voice_contains = voice_contains.strip().lower()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._request_event = threading.Event()
        self._state_lock = threading.Lock()
        self._pending_text: str | None = None
        self._pending_rate: int | None = None
        self._pending_voice_contains: str | None = None
        self._is_speaking = False
        self._default_voice_id: str | None = None
        self._startup_error: Exception | None = None

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
            self._pending_text = text
        self._request_event.set()
        _LOGGER.info("Speech request received: %s chars.", len(text))

    def stop(self) -> None:
        self._stop_event.set()
        self._request_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def update_settings(self, rate: int, voice_contains: str) -> None:
        with self._state_lock:
            self._pending_rate = rate
            self._pending_voice_contains = voice_contains.strip().lower()
        self._request_event.set()
        _LOGGER.info("Speaker settings update requested: rate=%s voice_contains=%s", rate, voice_contains)

    def _run(self) -> None:
        pythoncom.CoInitialize()
        try:
            engine = pyttsx3.init()
            self._default_voice_id = str(engine.getProperty("voice"))
            engine.setProperty("rate", self._rate)
            engine.connect("started-utterance", self._on_started_utterance)
            engine.connect("finished-utterance", self._on_finished_utterance)
            self._apply_voice_preference(engine, self._voice_contains)
            selected_voice = engine.getProperty("voice")
            _LOGGER.info("TTS engine initialized. rate=%s voice=%s", self._rate, selected_voice)
        except Exception as exc:
            self._startup_error = exc
            self._ready_event.set()
            pythoncom.CoUninitialize()
            return

        self._ready_event.set()
        _LOGGER.info("Speaker started.")

        try:
            engine.startLoop(False)
            while not self._stop_event.is_set():
                self._apply_pending_settings(engine)
                self._consume_pending_request(engine)
                engine.iterate()
                time.sleep(0.01)
        except Exception:
            _LOGGER.exception("Speaker loop failed.")
        finally:
            try:
                engine.stop()
            except Exception:
                pass
            try:
                engine.endLoop()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        _LOGGER.info("Speaker stopped.")

    def _consume_pending_request(self, engine: pyttsx3.Engine) -> None:
        if not self._request_event.is_set():
            return
        self._request_event.clear()
        with self._state_lock:
            text = self._pending_text
            self._pending_text = None
        if not text:
            return
        try:
            if self._is_speaking:
                _LOGGER.info("Interrupting current speech for a newer selection.")
                engine.stop()
                # Let SAPI dispatch stop events before enqueuing next utterance.
                for _ in range(3):
                    engine.iterate()
                    time.sleep(0.005)
            engine.say(text)
        except Exception:
            _LOGGER.exception("Failed to enqueue speech request.")

    def _apply_pending_settings(self, engine: pyttsx3.Engine) -> None:
        with self._state_lock:
            pending_rate = self._pending_rate
            pending_voice = self._pending_voice_contains
            self._pending_rate = None
            self._pending_voice_contains = None

        if pending_rate is None and pending_voice is None:
            return
        try:
            if pending_rate is not None:
                self._rate = pending_rate
                engine.setProperty("rate", pending_rate)
            if pending_voice is not None:
                self._voice_contains = pending_voice
                self._apply_voice_preference(engine, pending_voice)
            _LOGGER.info(
                "Speaker settings applied: rate=%s voice=%s",
                engine.getProperty("rate"),
                engine.getProperty("voice"),
            )
        except Exception:
            _LOGGER.exception("Failed to apply speaker settings.")

    def _apply_voice_preference(self, engine: pyttsx3.Engine, voice_contains: str) -> None:
        if voice_contains:
            for voice in engine.getProperty("voices"):
                content = f"{voice.id} {voice.name}".lower()
                if voice_contains in content:
                    engine.setProperty("voice", voice.id)
                    return
        elif self._default_voice_id:
            engine.setProperty("voice", self._default_voice_id)

    def _on_started_utterance(self, name: str | None = None) -> None:
        self._is_speaking = True
        _LOGGER.info("Speech playback started.")

    def _on_finished_utterance(self, name: str | None = None, completed: bool = True) -> None:
        self._is_speaking = False
        if completed:
            _LOGGER.info("Speech playback completed.")
        else:
            _LOGGER.info("Speech playback interrupted.")
