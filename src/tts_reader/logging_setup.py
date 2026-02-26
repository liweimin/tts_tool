from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path | None = None) -> Path:
    if log_dir is None:
        local_app_data = os.getenv("LOCALAPPDATA")
        base_dir = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        log_dir = base_dir / "tts-reader" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    _trim_old_log_backups(log_file, keep_backups=1)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    return log_file


def _trim_old_log_backups(log_file: Path, keep_backups: int) -> None:
    # Keep only app.log and the newest N rotated files (app.log.1, ...).
    backup_paths: list[Path] = []
    for candidate in log_file.parent.glob(f"{log_file.name}.*"):
        suffix = candidate.name.replace(f"{log_file.name}.", "")
        if suffix.isdigit():
            backup_paths.append(candidate)
    backup_paths.sort(key=lambda p: int(p.name.split(".")[-1]))
    to_remove = backup_paths[keep_backups:]
    for path in to_remove:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
