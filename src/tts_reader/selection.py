from __future__ import annotations

import ctypes
import importlib
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from ctypes import wintypes
from typing import Callable, Iterator

import win32api
import win32clipboard
import win32con


_LOGGER = logging.getLogger(__name__)
_USER32 = ctypes.windll.user32
_UIA_MODULE: object | None = None
_UIA_READY = False


@dataclass(frozen=True)
class ClipboardSnapshot:
    valid: bool
    had_content: bool
    formats: list[tuple[int, object]]
    text_backup: str | None


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def get_selected_text(copy_delay_ms: int, copy_retry_count: int = 2) -> tuple[str | None, str]:
    text = _get_selected_text_uia()
    if text:
        normalized = _normalize_text(text)
        if normalized:
            return normalized, "uia"
        _LOGGER.info("UI Automation returned empty/whitespace text; falling back to clipboard.")
    text, method = _get_selected_text_clipboard(
        copy_delay_ms=copy_delay_ms,
        copy_retry_count=copy_retry_count,
    )
    return (_normalize_text(text), method) if text else (None, method)


def _normalize_text(text: str | None) -> str | None:
    if not text:
        return None
    normalized = text.replace("\r\n", "\n").strip()
    return normalized if normalized else None


def _get_selected_text_uia() -> str | None:
    auto = _load_uiautomation()
    if auto is None:
        return None
    try:
        focused = auto.GetFocusedControl()
        if not focused:
            return None
        pattern = focused.GetTextPattern()
        if not pattern:
            return None
        selection = pattern.GetSelection()
        if not selection:
            return None
        chunks: list[str] = []
        for text_range in selection:
            piece = text_range.GetText(-1)
            if piece:
                chunks.append(piece)
        text = "".join(chunks)
        if text:
            _LOGGER.info("Selected text captured via UI Automation.")
        return text or None
    except Exception:
        _LOGGER.debug("UI Automation capture failed.", exc_info=True)
        return None


def _load_uiautomation() -> object | None:
    global _UIA_MODULE, _UIA_READY
    if _UIA_READY:
        return _UIA_MODULE
    try:
        _UIA_MODULE = importlib.import_module("uiautomation")
        _LOGGER.info("UI Automation module loaded.")
    except Exception:
        _UIA_MODULE = None
        _LOGGER.info("UI Automation module not available.")
    _UIA_READY = True
    return _UIA_MODULE


def _get_selected_text_clipboard(
    copy_delay_ms: int,
    copy_retry_count: int,
) -> tuple[str | None, str]:
    snapshot = _snapshot_clipboard()
    clipboard_seq = _USER32.GetClipboardSequenceNumber()
    copied_text: str | None = None
    used_method = "clipboard-timeout"
    try:
        wait_profiles = _build_wait_profiles(copy_delay_ms, copy_retry_count)
        total_attempts = len(wait_profiles)
        for attempt, (wm_wait_ms, ctrl_c_wait_ms, ctrl_insert_wait_ms) in enumerate(
            wait_profiles, start=1
        ):
            text, clipboard_seq = _attempt_copy(
                name="wm_copy",
                action=_send_wm_copy,
                previous_seq=clipboard_seq,
                wait_ms=wm_wait_ms,
            )
            if text:
                used_method = "wm_copy"
                copied_text = text
                return text, used_method

            _wait_for_modifier_keys_release()
            text, clipboard_seq = _attempt_copy(
                name="ctrl+c",
                action=_send_ctrl_c,
                previous_seq=clipboard_seq,
                wait_ms=ctrl_c_wait_ms,
            )
            if text:
                used_method = "ctrl+c"
                copied_text = text
                return text, used_method

            text, clipboard_seq = _attempt_copy(
                name="ctrl+insert",
                action=_send_ctrl_insert,
                previous_seq=clipboard_seq,
                wait_ms=ctrl_insert_wait_ms,
            )
            if text:
                used_method = "ctrl+insert"
                copied_text = text
                return text, used_method
            _LOGGER.info(
                "Clipboard capture attempt %s/%s did not get text.",
                attempt,
                total_attempts,
            )
            time.sleep(0.06)

        _LOGGER.warning("Clipboard capture timed out without selected text.")
        return None, used_method
    finally:
        _restore_clipboard(snapshot, fallback_text=copied_text)


def _build_wait_profiles(copy_delay_ms: int, copy_retry_count: int) -> list[tuple[int, int, int]]:
    full_delay = max(140, copy_delay_ms)
    quick_profile = (
        min(90, full_delay),
        min(140, full_delay),
        min(180, max(full_delay, 180)),
    )
    full_profile = (
        min(full_delay, 220),
        full_delay,
        max(full_delay, 260),
    )

    attempts = max(1, copy_retry_count)
    profiles: list[tuple[int, int, int]] = [quick_profile]
    if attempts >= 2:
        profiles.append(full_profile)
    for _ in range(2, attempts):
        profiles.append(full_profile)
    return profiles


def _attempt_copy(
    name: str,
    action: Callable[[], None],
    previous_seq: int,
    wait_ms: int,
) -> tuple[str | None, int]:
    try:
        action()
    except Exception:
        _LOGGER.debug("Copy action '%s' failed.", name, exc_info=True)
        return None, previous_seq
    text, seq = _wait_for_clipboard_text(previous_seq=previous_seq, wait_ms=wait_ms)
    if text:
        _LOGGER.info("Selected text captured via %s.", name)
    else:
        _LOGGER.info("Copy attempt '%s' produced no text.", name)
    return text, seq


def _wait_for_clipboard_text(previous_seq: int, wait_ms: int) -> tuple[str | None, int]:
    deadline = time.monotonic() + max(wait_ms, 120) / 1000.0
    seq = previous_seq
    seq_changed = False
    while time.monotonic() < deadline:
        current_seq = _USER32.GetClipboardSequenceNumber()
        if current_seq != seq:
            seq = current_seq
            seq_changed = True

        if seq_changed:
            text = _read_clipboard_text()
            if text is not None:
                return text, seq
        time.sleep(0.02)
    return None, seq


def _send_wm_copy() -> None:
    foreground = _USER32.GetForegroundWindow()
    if not foreground:
        return
    focus = _get_focus_window(foreground) or foreground
    _USER32.SendMessageW(int(focus), win32con.WM_COPY, 0, 0)


def _get_focus_window(foreground_hwnd: int) -> int | None:
    thread_id = _USER32.GetWindowThreadProcessId(int(foreground_hwnd), None)
    if not thread_id:
        return None
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    ok = _USER32.GetGUIThreadInfo(thread_id, ctypes.byref(info))
    if not ok:
        return None
    return int(info.hwndFocus) if info.hwndFocus else None


def _send_ctrl_c() -> None:
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("C"), 0, 0, 0)
    win32api.keybd_event(ord("C"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def _send_ctrl_insert() -> None:
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(win32con.VK_INSERT, 0, 0, 0)
    win32api.keybd_event(win32con.VK_INSERT, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def _wait_for_modifier_keys_release(timeout_ms: int = 120) -> None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        alt_down = _USER32.GetAsyncKeyState(win32con.VK_MENU) & 0x8000
        ctrl_down = _USER32.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000
        shift_down = _USER32.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000
        if not (alt_down or ctrl_down or shift_down):
            return
        time.sleep(0.01)


@contextmanager
def _open_clipboard() -> Iterator[None]:
    for _ in range(30):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception:
            time.sleep(0.01)
    else:
        raise RuntimeError("Could not open clipboard after retries.")
    try:
        yield
    finally:
        win32clipboard.CloseClipboard()


def _snapshot_clipboard() -> ClipboardSnapshot:
    formats: list[tuple[int, object]] = []
    text_backup: str | None = None
    try:
        with _open_clipboard():
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                try:
                    text_backup = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                except Exception:
                    text_backup = None
            current_format = 0
            while True:
                current_format = win32clipboard.EnumClipboardFormats(current_format)
                if current_format == 0:
                    break
                try:
                    formats.append(
                        (current_format, win32clipboard.GetClipboardData(current_format))
                    )
                except Exception:
                    continue
    except Exception:
        _LOGGER.debug("Failed to snapshot clipboard.", exc_info=True)
        return ClipboardSnapshot(valid=False, had_content=False, formats=[], text_backup=None)
    return ClipboardSnapshot(
        valid=True,
        had_content=bool(formats),
        formats=formats,
        text_backup=text_backup,
    )


def _restore_clipboard(snapshot: ClipboardSnapshot, fallback_text: str | None) -> None:
    if not snapshot.valid:
        return
    if not snapshot.had_content:
        return
    try:
        with _open_clipboard():
            win32clipboard.EmptyClipboard()
            restored_count = 0
            for fmt, data in snapshot.formats:
                try:
                    win32clipboard.SetClipboardData(fmt, data)
                    restored_count += 1
                except Exception:
                    continue
            if restored_count == 0:
                text_to_restore = snapshot.text_backup or fallback_text
                if text_to_restore is not None:
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text_to_restore)
    except Exception:
        _LOGGER.debug("Failed to restore clipboard snapshot.", exc_info=True)


def _read_clipboard_text() -> str | None:
    try:
        with _open_clipboard():
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                raw = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                if isinstance(raw, bytes):
                    return raw.decode(errors="ignore")
                return str(raw)
    except Exception:
        _LOGGER.debug("Failed to read clipboard text.", exc_info=True)
    return None
