from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Callable

from PIL import Image, ImageGrab

LOGGER = logging.getLogger(__name__)

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

        self._root = tk.Tk()
        self._root.attributes("-alpha", 0.3)
        self._root.attributes("-fullscreen", True)
        self._root.configure(cursor="cross")
        self._root.configure(bg="black")
        self._root.attributes("-topmost", True)
        
        # Bring completely to front
        self._root.lift()
        self._root.focus_force()

        self._canvas = tk.Canvas(self._root, highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        
        # Transparent background for canvas to show the black root via alpha
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
                self._start_x, self._start_y, self._start_x, self._start_y,
                outline="red", width=2, fill=""
            )

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self._canvas and self._rect_id:
            cur_x, cur_y = event.x_root, event.y_root
            self._canvas.coords(self._rect_id, self._start_x, self._start_y, cur_x, cur_y)

    def _on_mouse_up(self, event: tk.Event) -> None:
        end_x, end_y = event.x_root, event.y_root
        x1 = min(self._start_x, end_x)
        y1 = min(self._start_y, end_y)
        x2 = max(self._start_x, end_x)
        y2 = max(self._start_y, end_y)

        # Minimum selection size to prevent accidental clicks
        if (x2 - x1) < 10 or (y2 - y1) < 10:
            self._cancel()
            return
            
        region = (x1, y1, x2, y2)
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

    def _invoke_callback(self, image: Image.Image | None) -> None:
        # Play a sound to reduce perceived latency
        if image is not None:
            try:
                import ctypes
                ctypes.windll.user32.MessageBeep(0)
            except Exception:
                pass
        
        # Fire callback in a new thread so we don't block the UI thread's shutdown
        threading.Thread(target=self._on_capture, args=(image,), daemon=True).start()
