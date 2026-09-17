from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import winreg

_LOGGER = logging.getLogger(__name__)

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VAL_NAME = "TTSReader"


def get_target_command() -> str:
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}"'

    python_exe = Path(sys.executable).resolve()
    pythonw_exe = python_exe.with_name("pythonw.exe")
    runner = pythonw_exe if pythonw_exe.exists() else python_exe
    main_py = (Path(__file__).parent.parent / "main.py").resolve()
    return f'"{runner}" "{main_py}"'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, REG_VAL_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        _LOGGER.warning("Failed to query autostart registry key.", exc_info=True)
        return False


def set_autostart(enable: bool) -> bool:
    try:
        if enable:
            target = get_target_command()
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
                winreg.SetValueEx(key, REG_VAL_NAME, 0, winreg.REG_SZ, target)
            _LOGGER.info("Autostart enabled in registry: %s", target)
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, REG_VAL_NAME)
                    _LOGGER.info("Autostart disabled in registry.")
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        _LOGGER.exception("Failed to update autostart registry key (enable=%s).", enable)
        return False


def sync_autostart(desired_state: bool) -> None:
    current = is_autostart_enabled()
    if current != desired_state:
        set_autostart(desired_state)
