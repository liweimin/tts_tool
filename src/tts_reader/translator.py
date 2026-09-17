from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

LOGGER = logging.getLogger(__name__)


def is_mostly_english(text: str) -> bool:
    """
    判断文本是否主要为英文。
    容忍 OCR 识别背景产生的个别噪点中文字符。
    """
    if not text:
        return False
    stripped = "".join(text.split())
    if not stripped:
        return False

    english_chars = len(re.findall(r"[a-zA-Z]", text))
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))

    # 必须至少包含 3 个英文字母
    if english_chars < 3:
        return False

    # 若完全没有中文字符，则确定为英文
    if chinese_chars == 0:
        return True

    # 容忍截图中少量噪点（如 OCR 产生的 1~4 个误识别汉字）
    if chinese_chars <= 4 and english_chars >= 15:
        return True

    # 英文字符占比超过 75%
    if english_chars / (chinese_chars + english_chars) >= 0.75:
        return True

    return False


def translate_to_chinese(text: str, timeout: float = 5.0) -> str | None:
    """
    使用双通道免 Key 翻译接口将英文翻译为中文。
    通道 1: Google Translate API (POST 提交，支持长段落)
    通道 2: MyMemory Translation API (自动备用容灾)
    """
    if not text or not text.strip():
        return None

    # 通道 1: Google Translate
    res = _translate_google(text, timeout=timeout)
    if res:
        return res

    # 通道 2: MyMemory 备用通道
    res = _translate_mymemory(text, timeout=timeout)
    if res:
        return res

    return None


def _translate_google(text: str, timeout: float = 5.0) -> str | None:
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        data = urllib.parse.urlencode({
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if result and isinstance(result, list) and len(result) > 0:
                parts = [part[0] for part in result[0] if part and part[0]]
                translated = "".join(parts).strip()
                if translated:
                    LOGGER.info("Google Translate success (%d chars -> %d chars)", len(text), len(translated))
                    return translated
    except Exception as exc:
        LOGGER.warning("Google translation failed (%s): %s", type(exc).__name__, exc)
    return None


def _translate_mymemory(text: str, timeout: float = 5.0) -> str | None:
    try:
        query_text = text[:800]
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(query_text)}&langpair=en|zh-CN"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if result.get("responseStatus") == 200:
                translated = result.get("responseData", {}).get("translatedText", "").strip()
                if translated and not translated.startswith("MYMEMORY WARNING"):
                    LOGGER.info("MyMemory Translate fallback success (%d chars -> %d chars)", len(text), len(translated))
                    return translated
    except Exception as exc:
        LOGGER.warning("MyMemory translation failed (%s): %s", type(exc).__name__, exc)
    return None
