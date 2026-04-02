from __future__ import annotations

import ctypes
import logging
import threading
import tkinter as tk
from typing import Callable

from PIL import Image, ImageGrab

LOGGER = logging.getLogger(__name__)
_USER32 = ctypes.windll.user32
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

class ScreenshotOverlay:
    def __init__(self, on_capture: Callable[[Image.Image | None], None]) -> None:
        self._on_capture = on_capture
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._full_image: Image.Image | None = None
        self._start_x = 0
        self._start_y = 0
        self._rect_id: int | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._virtual_left = 0
        self._virtual_top = 0
        self._virtual_width = 0
        self._virtual_height = 0
        self._scale_x = 1.0
        self._scale_y = 1.0

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            self._full_image = ImageGrab.grab(all_screens=True)
        except Exception:
            LOGGER.exception("Failed to grab full screen image.")
            self._invoke_callback(None)
            return

        self._virtual_left, self._virtual_top, self._virtual_width, self._virtual_height = (
            _get_virtual_screen_bounds()
        )
        if self._virtual_width <= 0 or self._virtual_height <= 0:
            self._virtual_left = 0
            self._virtual_top = 0
            self._virtual_width = self._full_image.width
            self._virtual_height = self._full_image.height

        self._scale_x = self._full_image.width / max(self._virtual_width, 1)
        self._scale_y = self._full_image.height / max(self._virtual_height, 1)
        LOGGER.info(
            "Screenshot overlay initialized: logical_bounds=(%s,%s,%s,%s) image_size=(%s,%s) scale=(%.3f, %.3f)",
            self._virtual_left,
            self._virtual_top,
            self._virtual_width,
            self._virtual_height,
            self._full_image.width,
            self._full_image.height,
            self._scale_x,
            self._scale_y,
        )

        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-alpha", 0.3)
        self._root.configure(cursor="cross")
        self._root.configure(bg="black")
        self._root.attributes("-topmost", True)
        self._root.geometry(
            f"{self._virtual_width}x{self._virtual_height}"
            f"{self._virtual_left:+d}{self._virtual_top:+d}"
        )

        self._root.lift()
        self._root.focus_force()

        self._canvas = tk.Canvas(self._root, highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.configure(bg="black")

        self._root.bind("<ButtonPress-1>", self._on_mouse_down)
        self._root.bind("<B1-Motion>", self._on_mouse_drag)
        self._root.bind("<ButtonRelease-1>", self._on_mouse_up)
        self._root.bind("<Escape>", lambda e: self._cancel())

        self._root.mainloop()

    def _on_mouse_down(self, event: tk.Event) -> None:
        self._start_x = event.x_root
        self._start_y = event.y_root
        if self._canvas:
            self._rect_id = self._canvas.create_rectangle(
                *self._to_canvas_point(self._start_x, self._start_y),
                *self._to_canvas_point(self._start_x, self._start_y),
                outline="red", width=2, fill=""
            )

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self._canvas and self._rect_id:
            cur_x, cur_y = event.x_root, event.y_root
            start_canvas_x, start_canvas_y = self._to_canvas_point(self._start_x, self._start_y)
            cur_canvas_x, cur_canvas_y = self._to_canvas_point(cur_x, cur_y)
            self._canvas.coords(
                self._rect_id,
                start_canvas_x,
                start_canvas_y,
                cur_canvas_x,
                cur_canvas_y,
            )

    def _on_mouse_up(self, event: tk.Event) -> None:
        end_x, end_y = event.x_root, event.y_root
        logical_x1 = min(self._start_x, end_x)
        logical_y1 = min(self._start_y, end_y)
        logical_x2 = max(self._start_x, end_x)
        logical_y2 = max(self._start_y, end_y)

        if (logical_x2 - logical_x1) < 10 or (logical_y2 - logical_y1) < 10:
            self._cancel()
            return

        x1, y1 = self._to_capture_point(logical_x1, logical_y1)
        x2, y2 = self._to_capture_point(logical_x2, logical_y2)
        region = (
            max(0, min(x1, self._full_image.width)),
            max(0, min(y1, self._full_image.height)),
            max(0, min(x2, self._full_image.width)),
            max(0, min(y2, self._full_image.height)),
        )
        try:
            if self._full_image:
                cropped = self._full_image.crop(region)
                self._invoke_callback(cropped)
            else:
                self._invoke_callback(None)
        except Exception:
            LOGGER.exception("Failed to crop image.")
            self._invoke_callback(None)
        finally:
            self._close_window()

    def _cancel(self) -> None:
        self._invoke_callback(None)
        self._close_window()

    def _close_window(self) -> None:
        if self._root:
            self._root.quit()
        self._full_image = None

    def _to_canvas_point(self, x_root: int, y_root: int) -> tuple[int, int]:
        return x_root - self._virtual_left, y_root - self._virtual_top

    def _to_capture_point(self, x_root: int, y_root: int) -> tuple[int, int]:
        logical_x = x_root - self._virtual_left
        logical_y = y_root - self._virtual_top
        return round(logical_x * self._scale_x), round(logical_y * self._scale_y)

    def _invoke_callback(self, image: Image.Image | None) -> None:
        if image is not None:
            try:
                ctypes.windll.user32.MessageBeep(0)
            except Exception:
                pass

        threading.Thread(target=self._on_capture, args=(image,), daemon=True).start()


def _get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    return (
        _USER32.GetSystemMetrics(_SM_XVIRTUALSCREEN),
        _USER32.GetSystemMetrics(_SM_YVIRTUALSCREEN),
        _USER32.GetSystemMetrics(_SM_CXVIRTUALSCREEN),
        _USER32.GetSystemMetrics(_SM_CYVIRTUALSCREEN),
    )
