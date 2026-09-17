from __future__ import annotations

import asyncio
import logging
import re
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
            return clean_ocr_text(lines)
            
        except Exception:
            LOGGER.exception("Error during Windows Native OCR async execution.")
            return None


def clean_ocr_text(lines: list[str]) -> str:
    """Clean and reassemble raw OCR lines into coherent, fluent speech-friendly text."""
    if not lines:
        return ""

    raw_text = "\n".join(lines).strip()
    if not raw_text:
        return ""

    # 1. Normalize line breaks
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Fix hyphenated word breaks at end of line: 'auto-\nmatic' -> 'automatic'
    text = re.sub(r"([a-zA-Z]+)-\s*\n\s*([a-zA-Z]+)", r"\1\2", text)

    # 3. For Chinese / CJK: remove spaces between CJK characters and punctuation.
    # Windows Media OCR inserts a space between every Chinese word/character by default,
    # causing TTS engines to read one character at a time unnaturally.
    cjk_char = r"[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff01-\uff5e]"
    prev = None
    while prev != text:
        prev = text
        text = re.sub(rf"({cjk_char})\s+({cjk_char})", r"\1\2", text)

    # 4. Merge broken paragraph lines intelligently:
    # If a line does not end with sentence-ending punctuation, merge it into the next line.
    raw_lines = text.split("\n")
    merged_lines: list[str] = []
    for line in raw_lines:
        line_str = line.strip()
        if not line_str:
            continue
        if merged_lines:
            prev_line = merged_lines[-1]
            # If prev_line ends with CJK non-punctuation and current starts with CJK, merge directly
            if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]$", prev_line) and re.search(r"^[\u4e00-\u9fff\u3400-\u4dbf]", line_str):
                merged_lines[-1] = prev_line + line_str
                continue
            # If both lines are English without sentence break, merge with a single space
            elif re.search(r"[a-zA-Z0-9,]$", prev_line) and re.search(r"^[a-zA-Z0-9]", line_str):
                merged_lines[-1] = prev_line + " " + line_str
                continue
        merged_lines.append(line_str)

    text = "\n".join(merged_lines)

    # 5. Fix isolated single English letters separated by spaces (OCR artifact from CJK engine): 't h i s' -> 'this'
    def _merge_single_letters(m: re.Match) -> str:
        return m.group(0).replace(" ", "")

    text = re.sub(r"\b(?:[a-zA-Z]\s+){2,}[a-zA-Z]\b", _merge_single_letters, text)

    return text.strip()


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)
