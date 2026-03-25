from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from PIL import Image

import winrt.windows.graphics.imaging as imaging
import winrt.windows.media.ocr as ocr
import winrt.windows.storage.streams as streams

from .overlay import ScreenshotOverlay

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenOcrResult:
    text: str | None
    method: str
    capture_ms: int
    ocr_ms: int = 0
    image_pixels: int = 0


@dataclass(frozen=True)
class ScreenCaptureResult:
    image: Image.Image | None
    method: str
    capture_ms: int
    image_pixels: int = 0


class ScreenOcrReader:
    def __init__(self) -> None:
        self._engine: ocr.OcrEngine | None = None
        self._engine_lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def capture_and_read(
        self,
        abort_if: Callable[[], bool] | None = None,
    ) -> ScreenOcrResult:
        capture_result = self.capture_image(abort_if=abort_if)
        if capture_result.method in {"overlay-aborted", "overlay-cancelled"}:
            return ScreenOcrResult(
                text=None,
                method=capture_result.method,
                capture_ms=capture_result.capture_ms,
            )
        if not capture_result.image:
            return ScreenOcrResult(
                text=None,
                method="overlay-empty",
                capture_ms=capture_result.capture_ms,
            )

        ocr_start = time.perf_counter()
        text = self._recognize_text_sync(capture_result.image)
        ocr_ms = _elapsed_ms(ocr_start)
        pixels = capture_result.image_pixels

        if text:
            return ScreenOcrResult(
                text=text,
                method="overlay-windows-ocr",
                capture_ms=capture_result.capture_ms,
                ocr_ms=ocr_ms,
                image_pixels=pixels,
            )

        return ScreenOcrResult(
            text=None,
            method="overlay-windows-ocr-empty",
            capture_ms=capture_result.capture_ms,
            ocr_ms=ocr_ms,
            image_pixels=pixels,
        )

    def capture_image(
        self,
        abort_if: Callable[[], bool] | None = None,
    ) -> ScreenCaptureResult:
        started_at = time.perf_counter()

        if abort_if and abort_if():
            return ScreenCaptureResult(image=None, method="overlay-aborted", capture_ms=_elapsed_ms(started_at))

        event = threading.Event()
        captured_image: Image.Image | None = None

        def _on_capture(img: Image.Image | None) -> None:
            nonlocal captured_image
            captured_image = img
            event.set()

        overlay = ScreenshotOverlay(on_capture=_on_capture)
        overlay.start()

        while not event.is_set():
            if abort_if and abort_if():
                pass
            time.sleep(0.05)

        capture_ms = _elapsed_ms(started_at)
        if captured_image is None:
            return ScreenCaptureResult(image=None, method="overlay-cancelled", capture_ms=capture_ms)
        if abort_if and abort_if():
            return ScreenCaptureResult(image=None, method="overlay-aborted", capture_ms=capture_ms)

        return ScreenCaptureResult(
            image=captured_image,
            method="overlay-captured",
            capture_ms=capture_ms,
            image_pixels=captured_image.width * captured_image.height,
        )

    def warmup_async(self) -> None:
        # Windows OCR initializes extremely quickly on language profiles, no heavy warmup needed
        with self._engine_lock:
            if not self._engine:
                try:
                    self._engine = ocr.OcrEngine.try_create_from_user_profile_languages()
                    LOGGER.info("Windows Native OCR engine intialized.")
                except Exception:
                    LOGGER.exception("Failed to init Windows OCR.")

    def _recognize_text_sync(self, image: Image.Image) -> str | None:
        future = asyncio.run_coroutine_threadsafe(self._recognize_text_async(image), self._loop)
        try:
            return future.result(timeout=5.0)
        except Exception:
            LOGGER.exception("Failed to run Windows OCR future.")
            return None

    async def _recognize_text_async(self, image: Image.Image) -> str | None:
        try:
            with self._engine_lock:
                if not self._engine:
                    self._engine = ocr.OcrEngine.try_create_from_user_profile_languages()
                if not self._engine:
                    LOGGER.error("Windows OCR engine could not be created from user profile.")
                    return None
            
            # Convert PIL Image to BGRA8 bytes
            image = image.convert("RGBA")
            b, g, r, a = image.split()
            bgra_image = Image.merge("RGBA", (b, g, r, a))
            
            # Create SoftwareBitmap
            software_bitmap = imaging.SoftwareBitmap(
                imaging.BitmapPixelFormat.BGRA8,
                image.width,
                image.height,
                imaging.BitmapAlphaMode.PREMULTIPLIED
            )
            
            buf = bgra_image.tobytes()
            data_writer = streams.DataWriter()
            data_writer.write_bytes(buf)
            buffer = data_writer.detach_buffer()
            software_bitmap.copy_from_buffer(buffer)
            
            # Run OCR
            result = await self._engine.recognize_async(software_bitmap)
            
            if not result or not result.lines:
                return None
                
            lines = [line.text for line in result.lines]
            return "\n".join(lines).strip()
            
        except Exception:
            LOGGER.exception("Error during Windows Native OCR async execution.")
            return None


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)
