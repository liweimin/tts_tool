from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import subprocess
import sys
import threading
import time

from .config import AppConfig, DEFAULT_CONFIG_PATH, hotkey_to_modifiers_and_vk, read_config, write_config
from .hotkey import GlobalHotkeyListener
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
        self._config = config
        self._config_path = config_path
        self._config_mtime = _get_file_mtime(config_path)

        modifiers, vk = hotkey_to_modifiers_and_vk(config)
        self._speaker = Speaker(rate=config.tts_rate, voice_contains=config.tts_voice_contains)
        self._hotkey = GlobalHotkeyListener(modifiers=modifiers, vk=vk, on_trigger=self._on_hotkey)
        self._log_file = log_file or (Path.home() / "AppData" / "Local" / "tts-reader" / "logs" / "app.log")
        self._state_lock = threading.RLock()
        self._tray = TrayIcon(
            on_replay=self._on_replay,
            on_settings=self._open_settings,
            on_logs=self._open_logs,
            on_exit=self.request_stop,
        )
        self._shutdown_event = threading.Event()
        self._last_text_lock = threading.Lock()
        self._last_text: str | None = None

    def start(self) -> None:
        LOGGER.info("Starting app.")
        self._speaker.start()
        self._hotkey.start()
        self._tray.start()
        LOGGER.info("App started. Use hotkey '%s' to read selected text.", self._config.hotkey)

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
        self._hotkey.stop()
        self._speaker.stop()
        LOGGER.info("App stopped.")

    def request_stop(self) -> None:
        self._shutdown_event.set()

    def _on_hotkey(self) -> None:
        with self._state_lock:
            config = self._config

        window_title = _active_window_title()
        LOGGER.info("Hotkey triggered on window: %s", window_title)

        started_at = time.perf_counter()
        text, method = get_selected_text(
            copy_delay_ms=config.copy_delay_ms,
            copy_retry_count=config.copy_retry_count,
        )
        capture_ms = int((time.perf_counter() - started_at) * 1000)
        if not text:
            LOGGER.warning(
                "No selected text captured (method=%s, window=%s, capture_ms=%s).",
                method,
                window_title,
                capture_ms,
            )
            if not config.skip_if_no_text:
                with self._state_lock:
                    speaker = self._speaker
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

        with self._last_text_lock:
            self._last_text = text
        with self._state_lock:
            speaker = self._speaker
        speaker.speak(text)

    def _on_replay(self) -> None:
        with self._last_text_lock:
            text = self._last_text
        if text:
            with self._state_lock:
                speaker = self._speaker
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
            old_config = self._config
            old_hotkey = self._hotkey
            old_speaker = self._speaker

            hotkey_changed = new_config.hotkey.strip().lower() != old_config.hotkey.strip().lower()
            speaker_changed = (
                new_config.tts_rate != old_config.tts_rate
                or new_config.tts_voice_contains != old_config.tts_voice_contains
            )

            new_hotkey: GlobalHotkeyListener | None = None

            try:
                if hotkey_changed:
                    modifiers, vk = hotkey_to_modifiers_and_vk(new_config)
                    new_hotkey = GlobalHotkeyListener(modifiers=modifiers, vk=vk, on_trigger=self._on_hotkey)
                    new_hotkey.start()
                if hotkey_changed and new_hotkey is not None:
                    old_hotkey.stop()
                    self._hotkey = new_hotkey
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
                if new_hotkey is not None:
                    new_hotkey.stop()
                return False, f"应用配置失败: {exc}"

        LOGGER.info("Config updated from %s: hotkey=%s", source, new_config.hotkey)
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
