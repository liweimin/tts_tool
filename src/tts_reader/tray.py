from __future__ import annotations

import threading
from typing import Callable

from PIL import Image, ImageDraw
import pystray


class TrayIcon:
    def __init__(
        self,
        on_replay: Callable[[], None],
        on_read_screenshot: Callable[[], None],
        on_settings: Callable[[], None],
        on_logs: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self._on_replay = on_replay
        self._on_read_screenshot = on_read_screenshot
        self._on_settings = on_settings
        self._on_logs = on_logs
        self._on_exit = on_exit
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="tray-icon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        image = _build_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Read Again", lambda _icon, _item: self._on_replay()),
            pystray.MenuItem("Screenshot OCR", lambda _icon, _item: self._on_read_screenshot()),
            pystray.MenuItem("Settings", lambda _icon, _item: self._on_settings()),
            pystray.MenuItem("Logs", lambda _icon, _item: self._on_logs()),
            pystray.MenuItem("Exit", lambda _icon, _item: self._on_exit()),
        )
        self._icon = pystray.Icon("tts-reader", image, "TTS Reader", menu)
        self._icon.run()


def _build_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGB", (size, size), (26, 35, 45))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size - 8, size - 8), radius=12, fill=(56, 140, 240))
    draw.polygon([(24, 24), (24, 40), (38, 32)], fill=(255, 255, 255))
    draw.rectangle((40, 25, 44, 39), fill=(255, 255, 255))
    draw.rectangle((46, 22, 50, 42), fill=(255, 255, 255))
    return image
