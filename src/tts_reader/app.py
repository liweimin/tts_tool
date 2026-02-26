from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import subprocess
import sys
import threading
import time

from .config import AppConfig, DEFAULT_CONFIG_PATH, parse_hotkey, read_config, validate_config, write_config
from .hotkey import GlobalHotkeyListener
from .screen_ocr import ScreenOcrReader
from .selection import get_selected_text
from .speaker import Speaker
from .tray import TrayIcon


LOGGER = logging.getLogger(__name__)
_USER32 = ctypes.windll.user32


class ReaderApp:
    def __init__(
        self,
        config: AppConfig,
        log_file: Path | None = None,
        config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
        validate_config(config)
        self._config = config
        self._config_path = config_path
        self._config_mtime = _get_file_mtime(config_path)

        text_modifiers, text_vk = parse_hotkey(config.hotkey)
        screenshot_modifiers, screenshot_vk = parse_hotkey(config.screenshot_hotkey)
        self._speaker = Speaker(rate=config.tts_rate, voice_contains=config.tts_voice_contains)
        self._screen_ocr = ScreenOcrReader()
        self._text_hotkey = GlobalHotkeyListener(
            modifiers=text_modifiers,
            vk=text_vk,
            on_trigger=self._on_hotkey,
        )
        self._screenshot_hotkey = GlobalHotkeyListener(
            modifiers=screenshot_modifiers,
            vk=screenshot_vk,
            on_trigger=self._on_screenshot_hotkey,
        )
        self._log_file = log_file or (Path.home() / "AppData" / "Local" / "tts-reader" / "logs" / "app.log")
        self._state_lock = threading.RLock()
        self._tray = TrayIcon(
            on_replay=self._on_replay,
            on_read_screenshot=self._on_screenshot_hotkey,
            on_settings=self._open_settings,
            on_logs=self._open_logs,
            on_exit=self.request_stop,
        )
        self._shutdown_event = threading.Event()
        self._last_text_lock = threading.Lock()
        self._last_text: str | None = None
        self._request_lock = threading.Lock()
        self._request_seq = 0

    def start(self) -> None:
        LOGGER.info("Starting app.")
        self._speaker.start()
        self._screen_ocr.warmup_async()
        self._text_hotkey.start()
        self._screenshot_hotkey.start()
        self._tray.start()
        LOGGER.info(
            "App started. Use '%s' for selected text, '%s' for screenshot OCR.",
            self._config.hotkey,
            self._config.screenshot_hotkey,
        )

        next_config_check = time.monotonic() + 0.5
        while not self._shutdown_event.is_set():
            if time.monotonic() >= next_config_check:
                self._reload_config_if_needed()
                next_config_check = time.monotonic() + 0.5
            time.sleep(0.12)

        self.stop()

    def stop(self) -> None:
        LOGGER.info("Stopping app.")
        self._tray.stop()
        self._text_hotkey.stop()
        self._screenshot_hotkey.stop()
        self._speaker.stop()
        LOGGER.info("App stopped.")

    def request_stop(self) -> None:
        self._shutdown_event.set()

    def _on_hotkey(self) -> None:
        with self._state_lock:
            config = self._config
            speaker = self._speaker
        request_id = self._next_request_id()
        speaker.interrupt()

        window_title = _active_window_title()
        LOGGER.info("Hotkey triggered on window: %s (request_id=%s)", window_title, request_id)

        started_at = time.perf_counter()
        text, method = get_selected_text(
            copy_delay_ms=config.copy_delay_ms,
            copy_retry_count=config.copy_retry_count,
        )
        capture_ms = int((time.perf_counter() - started_at) * 1000)
        if not self._is_latest_request(request_id):
            LOGGER.info("Discarding stale text request id=%s.", request_id)
            return
        if not text:
            LOGGER.warning(
                "No selected text captured (method=%s, window=%s, capture_ms=%s, request_id=%s).",
                method,
                window_title,
                capture_ms,
                request_id,
            )
            if not config.skip_if_no_text:
                speaker.speak("未获取到选中文本")
            return

        if len(text) > config.max_chars:
            text = text[: config.max_chars]
            LOGGER.info("Text truncated to %s chars by max_chars setting.", config.max_chars)

        LOGGER.info(
            "Captured selected text: %s chars via %s (window=%s, capture_ms=%s).",
            len(text),
            method,
            window_title,
            capture_ms,
        )
        if not self._is_latest_request(request_id):
            LOGGER.info("Discarding stale text request id=%s before speak.", request_id)
            return

        with self._last_text_lock:
            self._last_text = text
        speaker.speak(text)

    def _on_screenshot_hotkey(self) -> None:
        with self._state_lock:
            config = self._config
            speaker = self._speaker
        request_id = self._next_request_id()
        speaker.interrupt()

        window_title = _active_window_title()
        LOGGER.info(
            "Screenshot hotkey triggered on window: %s (request_id=%s)",
            window_title,
            request_id,
        )

        result = self._screen_ocr.capture_and_read(
            abort_if=lambda: not self._is_latest_request(request_id),
        )
        if not self._is_latest_request(request_id):
            LOGGER.info("Discarding stale screenshot request id=%s.", request_id)
            return
        if result.method == "screenclip-aborted":
            LOGGER.info("Screenshot request aborted (window=%s, request_id=%s).", window_title, request_id)
            return
        if result.method == "screenclip-cancelled":
            LOGGER.info("Screenshot capture cancelled by user (window=%s).", window_title)
            return

        if not result.text:
            LOGGER.warning(
                "No text recognized from screenshot (method=%s, window=%s, capture_ms=%s, ocr_ms=%s, pixels=%s).",
                result.method,
                window_title,
                result.capture_ms,
                result.ocr_ms,
                result.image_pixels,
            )
            if not config.skip_if_no_text:
                speaker.speak("截图未识别到文本")
            return

        text = result.text
        if len(text) > config.max_chars:
            text = text[: config.max_chars]
            LOGGER.info("Screenshot text truncated to %s chars by max_chars setting.", config.max_chars)

        LOGGER.info(
            "Captured screenshot text: %s chars via %s (window=%s, capture_ms=%s, ocr_ms=%s, pixels=%s).",
            len(text),
            result.method,
            window_title,
            result.capture_ms,
            result.ocr_ms,
            result.image_pixels,
        )
        if not self._is_latest_request(request_id):
            LOGGER.info("Discarding stale screenshot request id=%s before speak.", request_id)
            return
        with self._last_text_lock:
            self._last_text = text
        speaker.speak(text)

    def _on_replay(self) -> None:
        with self._last_text_lock:
            text = self._last_text
        if text:
            with self._state_lock:
                speaker = self._speaker
            self._next_request_id()
            speaker.interrupt()
            speaker.speak(text)

    def get_config(self) -> AppConfig:
        with self._state_lock:
            return self._config

    def apply_config(self, new_config: AppConfig) -> tuple[bool, str]:
        return self._apply_config_internal(
            new_config=new_config,
            persist=True,
            source="control_panel",
        )

    def _apply_config_internal(
        self,
        new_config: AppConfig,
        persist: bool,
        source: str,
    ) -> tuple[bool, str]:
        with self._state_lock:
            try:
                validate_config(new_config)
            except Exception as exc:
                return False, f"配置校验失败: {exc}"

            old_config = self._config
            old_text_hotkey = self._text_hotkey
            old_screenshot_hotkey = self._screenshot_hotkey
            old_speaker = self._speaker

            text_hotkey_changed = new_config.hotkey.strip().lower() != old_config.hotkey.strip().lower()
            screenshot_hotkey_changed = (
                new_config.screenshot_hotkey.strip().lower()
                != old_config.screenshot_hotkey.strip().lower()
            )
            speaker_changed = (
                new_config.tts_rate != old_config.tts_rate
                or new_config.tts_voice_contains != old_config.tts_voice_contains
            )

            started_listeners: list[GlobalHotkeyListener] = []

            try:
                if text_hotkey_changed:
                    old_text_hotkey.stop()
                if screenshot_hotkey_changed:
                    old_screenshot_hotkey.stop()

                new_text_hotkey = old_text_hotkey
                if text_hotkey_changed:
                    text_modifiers, text_vk = parse_hotkey(new_config.hotkey)
                    new_text_hotkey = GlobalHotkeyListener(
                        modifiers=text_modifiers,
                        vk=text_vk,
                        on_trigger=self._on_hotkey,
                    )
                    new_text_hotkey.start()
                    started_listeners.append(new_text_hotkey)

                new_screenshot_hotkey = old_screenshot_hotkey
                if screenshot_hotkey_changed:
                    screenshot_modifiers, screenshot_vk = parse_hotkey(new_config.screenshot_hotkey)
                    new_screenshot_hotkey = GlobalHotkeyListener(
                        modifiers=screenshot_modifiers,
                        vk=screenshot_vk,
                        on_trigger=self._on_screenshot_hotkey,
                    )
                    new_screenshot_hotkey.start()
                    started_listeners.append(new_screenshot_hotkey)

                self._text_hotkey = new_text_hotkey
                self._screenshot_hotkey = new_screenshot_hotkey
                if speaker_changed:
                    old_speaker.update_settings(
                        rate=new_config.tts_rate,
                        voice_contains=new_config.tts_voice_contains,
                    )
                self._config = new_config
                if persist:
                    write_config(new_config, self._config_path)
                    self._config_mtime = _get_file_mtime(self._config_path)
            except Exception as exc:
                for listener in started_listeners:
                    listener.stop()
                if text_hotkey_changed:
                    try:
                        old_text_hotkey.start()
                        self._text_hotkey = old_text_hotkey
                    except Exception:
                        LOGGER.exception("Failed to restore previous text hotkey listener.")
                if screenshot_hotkey_changed:
                    try:
                        old_screenshot_hotkey.start()
                        self._screenshot_hotkey = old_screenshot_hotkey
                    except Exception:
                        LOGGER.exception("Failed to restore previous screenshot hotkey listener.")
                return False, f"应用配置失败: {exc}"

        LOGGER.info(
            "Config updated from %s: hotkey=%s screenshot_hotkey=%s",
            source,
            new_config.hotkey,
            new_config.screenshot_hotkey,
        )
        return True, "配置已保存并生效。"

    def _reload_config_if_needed(self) -> None:
        latest_mtime = _get_file_mtime(self._config_path)
        if latest_mtime is None or latest_mtime == self._config_mtime:
            return
        self._config_mtime = latest_mtime
        try:
            config = read_config(self._config_path)
        except Exception:
            LOGGER.exception("Failed to reload config file.")
            return
        if config == self.get_config():
            return
        ok, message = self._apply_config_internal(config, persist=False, source="config_file")
        if ok:
            LOGGER.info(message)
        else:
            LOGGER.warning(message)

    def _open_settings(self) -> None:
        self._launch_control_panel("settings")

    def _open_logs(self) -> None:
        self._launch_control_panel("logs")

    def _launch_control_panel(self, tab: str) -> None:
        cmd = _build_control_panel_command(
            tab=tab,
            config_path=self._config_path,
            log_path=self._log_file,
        )
        try:
            subprocess.Popen(cmd)
        except Exception:
            LOGGER.exception("Failed to launch control panel window.")

    def _next_request_id(self) -> int:
        with self._request_lock:
            self._request_seq += 1
            return self._request_seq

    def _is_latest_request(self, request_id: int) -> bool:
        with self._request_lock:
            return request_id == self._request_seq


def _build_control_panel_command(tab: str, config_path: Path, log_path: Path) -> list[str]:
    normalized_tab = "logs" if tab == "logs" else "settings"
    if getattr(sys, "frozen", False):
        return [
            sys.executable,
            "--control-panel",
            "--tab",
            normalized_tab,
            "--config-path",
            str(config_path),
            "--log-path",
            str(log_path),
        ]

    src_main = Path(__file__).resolve().parents[1] / "main.py"
    return [
        sys.executable,
        str(src_main),
        "--control-panel",
        "--tab",
        normalized_tab,
        "--config-path",
        str(config_path),
        "--log-path",
        str(log_path),
    ]


def _active_window_title() -> str:
    hwnd = _USER32.GetForegroundWindow()
    if not hwnd:
        return "<unknown>"
    buffer = ctypes.create_unicode_buffer(512)
    _USER32.GetWindowTextW(hwnd, buffer, 512)
    title = buffer.value.strip()
    return title or "<untitled>"


def _get_file_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except Exception:
        return None
