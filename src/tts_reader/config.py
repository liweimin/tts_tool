from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any

try:
    import win32con
    _MOD_ALT = win32con.MOD_ALT
    _MOD_CONTROL = win32con.MOD_CONTROL
    _MOD_SHIFT = win32con.MOD_SHIFT
    _MOD_WIN = win32con.MOD_WIN
    _VK_F_MAP = {f"f{i}": getattr(win32con, f"VK_F{i}") for i in range(1, 13)}
except ImportError:
    _MOD_ALT = 0x0001
    _MOD_CONTROL = 0x0002
    _MOD_SHIFT = 0x0004
    _MOD_WIN = 0x0008
    _VK_F_MAP = {f"f{i}": 0x6F + i for i in range(1, 13)}


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_default_config_path() -> Path:
    app_dir = get_app_dir()
    app_config = app_dir / "config.json"
    if app_config.exists():
        return app_config.resolve()

    # Prefer app_dir (portable mode) if it is writable
    try:
        test_file = app_dir / f".perm_test_{os.getpid()}"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return app_config.resolve()
    except (OSError, PermissionError):
        pass

    # Fallback to %LOCALAPPDATA%\tts-reader\config.json
    local_app_data = os.getenv("LOCALAPPDATA")
    base_dir = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    app_data_dir = base_dir / "tts-reader"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return (app_data_dir / "config.json").resolve()


DEFAULT_CONFIG_PATH = get_default_config_path()


_MODIFIER_MAP = {
    "alt": _MOD_ALT,
    "ctrl": _MOD_CONTROL,
    "shift": _MOD_SHIFT,
    "win": _MOD_WIN,
}

_VK_MAP = {
    **{chr(letter).lower(): ord(chr(letter)) for letter in range(ord("A"), ord("Z") + 1)},
    **{str(num): ord(str(num)) for num in range(10)},
    **_VK_F_MAP,
}


def _default_screenshot_save_dir() -> str:
    user_profile = os.getenv("USERPROFILE")
    base = Path(user_profile) if user_profile else Path.home()
    return str(base / "Desktop")


@dataclass(frozen=True)
class AppConfig:
    hotkey: str = "alt+q"
    screenshot_hotkey: str = "alt+r"
    save_screenshot_hotkey: str = "alt+e"
    screenshot_save_dir: str = field(default_factory=_default_screenshot_save_dir)
    copy_delay_ms: int = 260
    copy_retry_count: int = 2
    max_chars: int = 4000
    tts_rate: int = 180
    tts_voice_contains: str = ""
    skip_if_no_text: bool = False
    enable_auto_translation: bool = True
    tts_engine: str = "edge"
    edge_voice: str = "zh-CN-XiaoxiaoNeural"
    autostart: bool = True


def _parse_hotkey(hotkey: str) -> tuple[int, int]:
    parts = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
    if len(parts) < 2:
        raise ValueError(f"Invalid hotkey '{hotkey}'. Example: alt+q")

    modifiers = 0
    for part in parts[:-1]:
        if part not in _MODIFIER_MAP:
            raise ValueError(f"Unknown hotkey modifier '{part}' in '{hotkey}'")
        modifiers |= _MODIFIER_MAP[part]

    key_name = parts[-1]
    if key_name not in _VK_MAP:
        raise ValueError(f"Unknown hotkey key '{key_name}' in '{hotkey}'")
    return modifiers, _VK_MAP[key_name]


def read_config(config_path: Path | None = None) -> AppConfig:
    resolved_path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    if not resolved_path.exists():
        config = AppConfig()
        validate_config(config)
        return config

    raw = json.loads(resolved_path.read_text(encoding="utf-8"))
    data: dict[str, Any] = {}
    for field_name in AppConfig.__dataclass_fields__.keys():
        if field_name in raw:
            data[field_name] = raw[field_name]
    config = AppConfig(**data)
    validate_config(config)
    return config


def write_default_config_if_missing(config_path: Path | None = None) -> None:
    resolved_path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    if resolved_path.exists():
        return
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(AppConfig().__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_config(config: AppConfig, config_path: Path | None = None) -> None:
    resolved_path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(config.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    return _parse_hotkey(hotkey)


def hotkey_to_modifiers_and_vk(config: AppConfig) -> tuple[int, int]:
    return _parse_hotkey(config.hotkey)


def validate_config(config: AppConfig) -> None:
    _parse_hotkey(config.hotkey)
    _parse_hotkey(config.screenshot_hotkey)
    _parse_hotkey(config.save_screenshot_hotkey)

    hotkeys = {
        "text": config.hotkey.strip().lower(),
        "screenshot_ocr": config.screenshot_hotkey.strip().lower(),
        "save_screenshot": config.save_screenshot_hotkey.strip().lower(),
    }
    if len(set(hotkeys.values())) != len(hotkeys):
        raise ValueError("Text/OCR/save screenshot hotkeys must all be different.")

    save_dir = config.screenshot_save_dir.strip()
    if not save_dir:
        raise ValueError("Screenshot save directory cannot be empty.")
    save_path = Path(save_dir).expanduser()
    if save_path.exists() and not save_path.is_dir():
        raise ValueError("Screenshot save directory must be a folder path.")

    if config.tts_engine not in ("edge", "sapi5"):
        raise ValueError(f"Invalid tts_engine '{config.tts_engine}'. Must be 'edge' or 'sapi5'.")
