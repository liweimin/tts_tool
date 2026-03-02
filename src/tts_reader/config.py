from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import win32con


DEFAULT_CONFIG_PATH = Path("config.json")


_MODIFIER_MAP = {
    "alt": win32con.MOD_ALT,
    "ctrl": win32con.MOD_CONTROL,
    "shift": win32con.MOD_SHIFT,
    "win": win32con.MOD_WIN,
}

_VK_MAP = {
    **{chr(letter).lower(): ord(chr(letter)) for letter in range(ord("A"), ord("Z") + 1)},
    **{str(num): ord(str(num)) for num in range(10)},
    "f1": win32con.VK_F1,
    "f2": win32con.VK_F2,
    "f3": win32con.VK_F3,
    "f4": win32con.VK_F4,
    "f5": win32con.VK_F5,
    "f6": win32con.VK_F6,
    "f7": win32con.VK_F7,
    "f8": win32con.VK_F8,
    "f9": win32con.VK_F9,
    "f10": win32con.VK_F10,
    "f11": win32con.VK_F11,
    "f12": win32con.VK_F12,
}


@dataclass(frozen=True)
class AppConfig:
    hotkey: str = "alt+q"
    screenshot_hotkey: str = "alt+r"
    copy_delay_ms: int = 260
    copy_retry_count: int = 2
    max_chars: int = 4000
    tts_rate: int = 180
    tts_voice_contains: str = ""
    skip_if_no_text: bool = False
    enable_auto_translation: bool = True


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


def read_config(config_path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not config_path.exists():
        config = AppConfig()
        validate_config(config)
        return config

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    data: dict[str, Any] = {}
    for field_name in AppConfig.__dataclass_fields__.keys():
        if field_name in raw:
            data[field_name] = raw[field_name]
    config = AppConfig(**data)
    validate_config(config)
    return config


def write_default_config_if_missing(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    if config_path.exists():
        return
    config_path.write_text(
        json.dumps(AppConfig().__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_config(config: AppConfig, config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    config_path.write_text(
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
    if config.hotkey.strip().lower() == config.screenshot_hotkey.strip().lower():
        raise ValueError("Text hotkey and screenshot hotkey cannot be the same.")
