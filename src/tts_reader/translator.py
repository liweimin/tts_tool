from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

LOGGER = logging.getLogger(__name__)


def is_mostly_english(text: str) -> bool:
    """
    判断文本是否为主体待翻译的英文内容（纯英文或以英文为主的混合段落）。
    若为主体中文（包括夹杂技术术语、产品名如 Tabbit Browser、Agent 等的中文文章），
    返回 False，直接由 TTS 引擎进行高质量中英自然混读，避免误翻译篡改中文。
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

    # 2. 截图中极少量 OCR 噪点汉字（例如边缘包含 1~4 个零星汉字）
    if chinese_chars <= 4 and english_chars >= 10:
        return True

    # 3. 英文为主体的大段混合文本（如英文正文邮件夹带署名）：
    # 限制汉字不超过 15 个，英文占据显著优势（例如英文总数达到 40 且占比 >= 75%），
    # 并包含连贯英文短语/句式。若汉字超过 15 个，说明已具有完整中文语境，坚决不进行整篇翻译。
    if chinese_chars <= 15 and english_chars >= 40:
        has_english_phrase = bool(re.search(r"\b[a-zA-Z]{2,}(?:\s+[a-zA-Z]+)+\b", text))
        ratio = english_chars / (chinese_chars + english_chars)
        if has_english_phrase and ratio >= 0.75:
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
        # 始终使用 sl=auto 让 Google 自动精准检测源语言。
        # 严禁在含中文时硬编码 sl=en，否则会导致 Google 模型在英文解码下将中文汉字幻觉乱翻（例如将“评测”翻成“体育”）。
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
