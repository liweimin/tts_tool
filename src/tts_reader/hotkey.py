from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable


_USER32 = ctypes.windll.user32
_KERNEL32 = ctypes.windll.kernel32
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_HOTKEY_ID = 1
_MOD_NOREPEAT = 0x4000
_TEST_HOTKEY_ID = 0x6FFF

_LOGGER = logging.getLogger(__name__)


class GlobalHotkeyListener:
    def __init__(self, modifiers: int, vk: int, on_trigger: Callable[[], None]) -> None:
        self._modifiers = modifiers
        self._vk = vk
        self._on_trigger = on_trigger
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._startup_error: Exception | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="hotkey-listener", daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=3.0)
        if self._startup_error:
            raise RuntimeError("Failed to start global hotkey listener") from self._startup_error

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread_id:
            _USER32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        self._thread_id = _KERNEL32.GetCurrentThreadId()
        registered = _USER32.RegisterHotKey(
            None, _HOTKEY_ID, self._modifiers | _MOD_NOREPEAT, self._vk
        )
        if not registered:
            registered = _USER32.RegisterHotKey(None, _HOTKEY_ID, self._modifiers, self._vk)
        if not registered:
            self._startup_error = OSError("RegisterHotKey failed, likely hotkey conflict")
            self._ready_event.set()
            return

        _LOGGER.info("Global hotkey registered.")
        self._ready_event.set()
        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            result = _USER32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0:
                break
            if result == -1:
                _LOGGER.exception("GetMessageW failed in hotkey loop.")
                break
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                try:
                    self._on_trigger()
                except Exception:
                    _LOGGER.exception("Unhandled error in hotkey callback.")

        _USER32.UnregisterHotKey(None, _HOTKEY_ID)
        _LOGGER.info("Global hotkey unregistered.")


def is_hotkey_available(modifiers: int, vk: int) -> bool:
    registered = _USER32.RegisterHotKey(None, _TEST_HOTKEY_ID, modifiers | _MOD_NOREPEAT, vk)
    if not registered:
        registered = _USER32.RegisterHotKey(None, _TEST_HOTKEY_ID, modifiers, vk)
    if not registered:
        return False
    _USER32.UnregisterHotKey(None, _TEST_HOTKEY_ID)
    return True
