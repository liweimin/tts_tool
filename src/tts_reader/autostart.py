from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import winreg

_LOGGER = logging.getLogger(__name__)

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VAL_NAME = "TTSReader"
STARTUP_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
SHORTCUT_NAME = "TTSReader.lnk"


def get_target_command() -> str:
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}"'

    python_exe = Path(sys.executable).resolve()
    pythonw_exe = python_exe.with_name("pythonw.exe")
    runner = pythonw_exe if pythonw_exe.exists() else python_exe
    main_py = (Path(__file__).parent.parent / "main.py").resolve()
    return f'"{runner}" "{main_py}"'


def _normalize_cmd(cmd: str | None) -> str:
    if not cmd:
        return ""
    clean = cmd.strip()
    if clean.startswith('"') and clean.endswith('"') and len(clean) >= 2:
        clean = clean[1:-1]
    return os.path.normcase(os.path.normpath(clean))


def get_registered_registry_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_VAL_NAME)
            return str(val)
    except (FileNotFoundError, OSError):
        return None
    except Exception:
        _LOGGER.warning("Failed to query autostart registry key.", exc_info=True)
        return None


def get_startup_shortcut_path() -> Path:
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / SHORTCUT_NAME


def is_autostart_enabled() -> bool:
    target_norm = _normalize_cmd(get_target_command())

    # 1. Check registry Run
    reg_cmd = get_registered_registry_command()
    if reg_cmd and _normalize_cmd(reg_cmd) == target_norm:
        return True

    # 2. Check Startup folder shortcut
    shortcut = get_startup_shortcut_path()
    if shortcut.exists():
        return True

    return False


def _create_startup_shortcut(shortcut_path: Path) -> bool:
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            target_exe = Path(sys.executable).resolve()
            target_args = ""
            work_dir = target_exe.parent
        else:
            python_exe = Path(sys.executable).resolve()
            pythonw_exe = python_exe.with_name("pythonw.exe")
            target_exe = pythonw_exe if pythonw_exe.exists() else python_exe
            main_py = (Path(__file__).parent.parent / "main.py").resolve()
            target_args = f'"{main_py}"'
            work_dir = main_py.parent

        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_path}'); "
            f"$s.TargetPath = '{target_exe}'; "
            f"$s.Arguments = '{target_args}'; "
            f"$s.WorkingDirectory = '{work_dir}'; "
            f"$s.Save()"
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            creationflags=creation_flags,
            capture_output=True,
            timeout=5,
        )
        return res.returncode == 0 and shortcut_path.exists()
    except Exception:
        _LOGGER.exception("Failed to create autostart shortcut in Startup folder.")
        return False


def set_autostart(enable: bool) -> bool:
    success = False
    target = get_target_command()
    shortcut_path = get_startup_shortcut_path()

    if enable:
        # Try writing to HKCU Run key
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
                winreg.SetValueEx(key, REG_VAL_NAME, 0, winreg.REG_SZ, target)
            _LOGGER.info("Autostart enabled in registry: %s", target)
            success = True
        except Exception:
            _LOGGER.warning("Failed to update autostart registry key.", exc_info=True)

        # Clear any disabled status in StartupApproved\Run (Windows 11)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, REG_VAL_NAME)
                except FileNotFoundError:
                    pass
        except Exception:
            pass

        # If registry write failed (e.g. enterprise GPO restriction), fallback to Startup folder shortcut
        if not success:
            _LOGGER.info("Registry write failed. Attempting fallback: creating shortcut in Startup folder...")
            if _create_startup_shortcut(shortcut_path):
                _LOGGER.info("Autostart shortcut created in Startup folder: %s", shortcut_path)
                success = True
            else:
                _LOGGER.error("Failed to create autostart shortcut in Startup folder.")
        else:
            # If registry succeeded, remove any leftover shortcut in Startup folder to prevent double launching
            if shortcut_path.exists():
                try:
                    shortcut_path.unlink()
                except Exception:
                    pass
    else:
        # Disable: remove from registry Run
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, REG_VAL_NAME)
                    _LOGGER.info("Autostart disabled in registry.")
                    success = True
                except FileNotFoundError:
                    success = True
        except Exception:
            _LOGGER.warning("Failed to delete autostart registry key.", exc_info=True)

        # Remove from StartupApproved
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, REG_VAL_NAME)
                except FileNotFoundError:
                    pass
        except Exception:
            pass

        # Remove shortcut from Startup folder
        if shortcut_path.exists():
            try:
                shortcut_path.unlink()
                _LOGGER.info("Removed autostart shortcut: %s", shortcut_path)
                success = True
            except Exception:
                _LOGGER.warning("Failed to remove autostart shortcut.", exc_info=True)

    return success


def sync_autostart(desired_state: bool) -> None:
    current = is_autostart_enabled()
    if current != desired_state:
        set_autostart(desired_state)
    elif desired_state:
        # Even if enabled is True, ensure the registered command matches the current exe path
        reg_cmd = get_registered_registry_command()
        target = get_target_command()
        if reg_cmd and _normalize_cmd(reg_cmd) != _normalize_cmd(target):
            _LOGGER.info("Autostart registered path out of date (%s vs %s). Updating...", reg_cmd, target)
            set_autostart(True)
