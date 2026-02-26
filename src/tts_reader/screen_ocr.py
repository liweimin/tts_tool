from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
import subprocess
import threading
import time
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageGrab, ImageOps
import win32con


LOGGER = logging.getLogger(__name__)
_USER32 = ctypes.windll.user32
_SHELL32 = ctypes.windll.shell32


@dataclass(frozen=True)
class ScreenOcrResult:
    text: str | None
    method: str
    capture_ms: int
    ocr_ms: int = 0
    image_pixels: int = 0


class ScreenOcrReader:
    def __init__(
        self,
        timeout_ms: int = 12000,
        min_score: float = 0.35,
        max_side_len: int = 1420,
        det_limit_side_len: int = 800,
        rec_batch_num: int = 1,
    ) -> None:
        self._timeout_ms = timeout_ms
        self._min_score = min_score
        self._max_side_len = max(900, max_side_len)
        self._det_limit_side_len = max(640, det_limit_side_len)
        self._rec_batch_num = max(1, rec_batch_num)

        self._engine_lock = threading.Lock()
        self._ocr_call_lock = threading.Lock()
        self._engine: Any | None = None

        self._warmup_started = False
        self._warmup_lock = threading.Lock()

    def capture_and_read(
        self,
        abort_if: Callable[[], bool] | None = None,
    ) -> ScreenOcrResult:
        started_at = time.perf_counter()
        if abort_if and abort_if():
            return ScreenOcrResult(
                text=None,
                method="screenclip-aborted",
                capture_ms=_elapsed_ms(started_at),
            )

        previous_clipboard_seq = _USER32.GetClipboardSequenceNumber()
        _wait_for_modifier_keys_release()

        try:
            _launch_screenclip()
        except Exception:
            LOGGER.exception("Failed to launch screen clipping UI.")
            return ScreenOcrResult(
                text=None,
                method="screenclip-launch-failed",
                capture_ms=_elapsed_ms(started_at),
            )

        image, wait_status = _wait_for_new_clipboard_image(
            previous_seq=previous_clipboard_seq,
            timeout_ms=self._timeout_ms,
            abort_if=abort_if,
        )
        if wait_status == "aborted":
            return ScreenOcrResult(
                text=None,
                method="screenclip-aborted",
                capture_ms=_elapsed_ms(started_at),
            )
        if image is None:
            return ScreenOcrResult(
                text=None,
                method="screenclip-cancelled",
                capture_ms=_elapsed_ms(started_at),
            )
        if abort_if and abort_if():
            return ScreenOcrResult(
                text=None,
                method="screenclip-aborted",
                capture_ms=_elapsed_ms(started_at),
            )

        text, ocr_ms, image_pixels, pass_name = self._recognize_text(
            image=image,
            abort_if=abort_if,
        )
        if pass_name == "aborted":
            return ScreenOcrResult(
                text=None,
                method="screenclip-aborted",
                capture_ms=_elapsed_ms(started_at),
                ocr_ms=ocr_ms,
                image_pixels=image_pixels,
            )
        if text:
            return ScreenOcrResult(
                text=text,
                method=f"screenclip-ocr-{pass_name}",
                capture_ms=_elapsed_ms(started_at),
                ocr_ms=ocr_ms,
                image_pixels=image_pixels,
            )
        return ScreenOcrResult(
            text=None,
            method=f"screenclip-ocr-empty-{pass_name}",
            capture_ms=_elapsed_ms(started_at),
            ocr_ms=ocr_ms,
            image_pixels=image_pixels,
        )

    def warmup_async(self) -> None:
        with self._warmup_lock:
            if self._warmup_started:
                return
            self._warmup_started = True
        threading.Thread(target=self._warmup, name="ocr-warmup", daemon=True).start()

    def _warmup(self) -> None:
        started_at = time.perf_counter()
        engine = self._get_engine()
        if engine is None:
            return
        warmup_image = np.full((80, 360), 255, dtype=np.uint8)
        try:
            self._run_engine(engine, warmup_image)
        except Exception:
            LOGGER.debug("RapidOCR warmup run failed.", exc_info=True)
        LOGGER.info("RapidOCR warmup finished in %sms.", _elapsed_ms(started_at))

    def _recognize_text(
        self,
        image: Image.Image,
        abort_if: Callable[[], bool] | None,
    ) -> tuple[str | None, int, int, str]:
        engine = self._get_engine()
        if engine is None:
            return None, 0, 0, "engine"

        gray = ImageOps.grayscale(image.convert("RGB"))
        primary = _prepare_image_for_ocr(gray=gray, max_side_len=self._max_side_len)
        primary_pixels = int(primary.shape[0] * primary.shape[1])
        primary_result, primary_ms = self._run_engine(engine=engine, image_array=primary)
        primary_text = _extract_text(primary_result, min_score=self._min_score)
        if abort_if and abort_if():
            return None, primary_ms, primary_pixels, "aborted"
        if primary_text:
            return primary_text, primary_ms, primary_pixels, "primary"

        # Fallback only when primary got empty text.
        fallback = _prepare_image_for_ocr(gray=gray, max_side_len=1560)
        fallback_pixels = int(fallback.shape[0] * fallback.shape[1])
        fallback_result, fallback_ms = self._run_engine(engine=engine, image_array=fallback)
        total_ms = primary_ms + fallback_ms
        if abort_if and abort_if():
            return None, total_ms, fallback_pixels, "aborted"
        fallback_text = _extract_text(fallback_result, min_score=self._min_score)
        if fallback_text:
            return fallback_text, total_ms, fallback_pixels, "fallback"
        return None, total_ms, fallback_pixels, "fallback"

    def _run_engine(self, engine: Any, image_array: np.ndarray) -> tuple[list[list[Any]] | None, int]:
        started_at = time.perf_counter()
        with self._ocr_call_lock:
            result, _elapsed = engine(image_array)
        return result, _elapsed_ms(started_at)

    def _get_engine(self) -> Any | None:
        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            try:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR(
                    use_cls=False,
                    max_side_len=self._max_side_len,
                    det_limit_type="max",
                    det_limit_side_len=self._det_limit_side_len,
                    rec_batch_num=self._rec_batch_num,
                )
                LOGGER.info("RapidOCR engine initialized.")
            except Exception:
                LOGGER.exception("Failed to initialize RapidOCR engine.")
                self._engine = None
            return self._engine


def _launch_screenclip() -> None:
    result = _SHELL32.ShellExecuteW(
        None,
        "open",
        "ms-screenclip:",
        None,
        None,
        1,
    )
    if int(result) > 32:
        return
    subprocess.Popen(
        ["explorer.exe", "ms-screenclip:"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_new_clipboard_image(
    previous_seq: int,
    timeout_ms: int,
    abort_if: Callable[[], bool] | None,
) -> tuple[Image.Image | None, str]:
    deadline = time.monotonic() + timeout_ms / 1000.0
    seen_seq = previous_seq
    while time.monotonic() < deadline:
        if abort_if and abort_if():
            return None, "aborted"
        current_seq = _USER32.GetClipboardSequenceNumber()
        if current_seq != seen_seq:
            seen_seq = current_seq
            clip_obj = ImageGrab.grabclipboard()
            if isinstance(clip_obj, Image.Image):
                LOGGER.info("Screenshot image captured from clipboard.")
                return clip_obj, "ok"
        time.sleep(0.016)
    LOGGER.info("Screen clipping timed out or cancelled by user.")
    return None, "cancelled"


def _prepare_image_for_ocr(gray: Image.Image, max_side_len: int) -> np.ndarray:
    image = _resize_limit_max_side(gray, max_side_len=max_side_len)
    short_side = min(image.size[0], image.size[1])
    if short_side < 140:
        image = image.resize(
            (
                max(1, int(image.size[0] * 1.2)),
                max(1, int(image.size[1] * 1.2)),
            ),
            resample=Image.Resampling.BICUBIC,
        )
    return np.array(image)


def _resize_limit_max_side(image: Image.Image, max_side_len: int) -> Image.Image:
    width, height = image.size
    longest_side = max(width, height)
    if longest_side <= max_side_len:
        return image
    scale = max_side_len / float(longest_side)
    return image.resize(
        (
            max(1, int(width * scale)),
            max(1, int(height * scale)),
        ),
        resample=Image.Resampling.BILINEAR,
    )


def _extract_text(ocr_result: list[list[Any]] | None, min_score: float) -> str | None:
    if not ocr_result:
        return None
    texts: list[str] = []
    for item in ocr_result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text = str(item[1]).strip()
        if not text:
            continue
        score = 1.0
        if len(item) >= 3:
            try:
                score = float(item[2])
            except Exception:
                score = 1.0
        if score >= min_score:
            texts.append(text)
    merged = "\n".join(texts).strip()
    return merged or None


def _wait_for_modifier_keys_release(timeout_ms: int = 80) -> None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        alt_down = _USER32.GetAsyncKeyState(win32con.VK_MENU) & 0x8000
        ctrl_down = _USER32.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000
        shift_down = _USER32.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000
        if not (alt_down or ctrl_down or shift_down):
            return
        time.sleep(0.008)


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)
