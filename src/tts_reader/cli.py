from __future__ import annotations

import argparse
import logging
import msvcrt
import os
from pathlib import Path
import signal

from .app import ReaderApp
from .config import DEFAULT_CONFIG_PATH, read_config, write_default_config_if_missing
from .control_panel import run_control_panel
from .logging_setup import setup_logging

_INSTANCE_LOCK_FILE = None


def main() -> int:
    args = _parse_args()
    if args.control_panel:
        config_path = Path(args.config_path) if args.config_path else DEFAULT_CONFIG_PATH
        log_path = Path(args.log_path) if args.log_path else setup_logging()
        return run_control_panel(config_path=config_path, log_path=log_path, tab=args.tab)

    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Logging to %s", log_file)

    if not _acquire_instance_lock():
        logger.error("Another instance is already running. Exit this instance.")
        return 2

    write_default_config_if_missing()
    config = read_config()
    logger.info(
        "Loaded config: hotkey=%s max_chars=%s copy_delay_ms=%s copy_retry_count=%s",
        config.hotkey,
        config.max_chars,
        config.copy_delay_ms,
        config.copy_retry_count,
    )
    hotkey_lower = config.hotkey.lower()
    if hotkey_lower.startswith("alt+") and "ctrl+" not in hotkey_lower:
        logger.info(
            "Current hotkey '%s' is active. If conflicts happen, change it in Settings.",
            config.hotkey,
        )
    app = ReaderApp(config=config, log_file=log_file)

    def _signal_handler(_signum: int, _frame: object) -> None:
        app.request_stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        app.start()
    except Exception:
        logger.exception("Fatal error.")
        return 1
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--control-panel", action="store_true")
    parser.add_argument("--tab", choices=["settings", "logs"], default="settings")
    parser.add_argument("--config-path")
    parser.add_argument("--log-path")
    return parser.parse_args()


def _acquire_instance_lock() -> bool:
    global _INSTANCE_LOCK_FILE
    local_app_data = os.getenv("LOCALAPPDATA")
    base_dir = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    lock_dir = base_dir / "tts-reader"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "instance.lock"
    if not lock_path.exists():
        lock_path.write_text("0", encoding="utf-8")

    lock_file = lock_path.open("r+", encoding="utf-8")
    lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        return False
    _INSTANCE_LOCK_FILE = lock_file
    return True
