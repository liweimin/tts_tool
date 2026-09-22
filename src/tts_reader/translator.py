from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

LOGGER = logging.getLogger(__name__)


def is_mostly_english(text: str) -> bool:
    """
    判断文本是否包含待翻译的英文内容（兼容纯英文与中英混合段落）。
    若为纯中文或仅含零星孤立单词/代号，返回 False 以保持 0 延迟本地直接朗读。
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

    # 1. 纯英文（完全无中文字符）
    if chinese_chars == 0:
        return True

    # 2. 截图中少量 OCR 噪点汉字
    if chinese_chars <= 4 and english_chars >= 10:
        return True

    # 3. 包含连贯的英文句式/短语（至少 2 个连续英文单词，如 'The weather is nice', 'Please let me know'）
    has_english_phrase = bool(re.search(r"\b[a-zA-Z]{2,}(?:\s+[a-zA-Z]+)+\b", text))
    if has_english_phrase and english_chars >= 8:
        return True

    # 4. 英文字符占显著优势（例如 60% 以上且英文总数达到 15）
    if english_chars / (chinese_chars + english_chars) >= 0.6 and english_chars >= 15:
        return True

    return False


def translate_to_chinese(text: str, timeout: float = 5.0) -> str | None:
    """
    使用双通道免 Key 翻译接口将英文翻译为中文。
    通道 1: Google Translate API (POST 提交，支持长段落与中英混合文本)
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
        # 若文本中包含中文字符，将 sl 明确指定为 en，避免 Google auto 检测误判整篇为 zh-CN 导致英文不翻译；
        # 若为纯外文（无中文），使用 auto 自动兼容各种源语言。
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))
        sl = "en" if has_chinese else "auto"

        data = urllib.parse.urlencode({
            "client": "gtx",
            "sl": sl,
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
