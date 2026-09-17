from __future__ import annotations

from pathlib import Path
import sys
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
        image = _get_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("朗读选中文本 (Alt+Q)", lambda _icon, _item: self._on_replay()),
            pystray.MenuItem("截图 OCR 朗读 (Alt+R)", lambda _icon, _item: self._on_read_screenshot()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("系统设置", lambda _icon, _item: self._on_settings(), default=True),
            pystray.MenuItem("运行日志", lambda _icon, _item: self._on_logs()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda _icon, _item: self._on_exit()),
        )
        self._icon = pystray.Icon("tts-reader", image, "TTS Reader (双击打开设置)", menu)
        self._icon.run()


def _get_icon_image() -> Image.Image:
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "icon.png")
    candidates.append(Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png")
    candidates.append(Path("assets") / "icon.png")

    for p in candidates:
        if p.exists():
            try:
                return Image.open(p)
            except Exception:
                pass
    return _build_icon_image()


def _build_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, size - 4, size - 4), radius=14, fill=(33, 115, 243))
    # Speaker cone and waves
    draw.polygon([(16, 24), (16, 40), (28, 40), (40, 48), (40, 16), (28, 24)], fill=(255, 255, 255))
    draw.arc([36, 20, 52, 44], start=-50, end=50, fill=(255, 255, 255), width=3)
    return image
