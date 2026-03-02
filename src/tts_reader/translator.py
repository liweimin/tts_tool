import logging
import re
import urllib.request
import urllib.parse
import json

LOGGER = logging.getLogger(__name__)

def is_mostly_english(text: str) -> bool:
    """
    判断文本是否主要为英文。
    如果包含太多中文字符，则不认为主体是英文。
    """
    if not text:
        return False
        
    # 去除空白字符后的实际内容长度
    stripped_text = "".join(text.split())
    if not stripped_text:
        return False
        
    # 匹配所有的常用中文字符范围 \u4e00-\u9fa5
    chinese_chars = re.findall(r'[\u4e00-\u9fa5]', text)
    
    # 假设如果中文字符占比超过总长度的 5% 或者 有超过 2 个中文字符，就不当做纯英文段落
    # 这里的阈值可以根据实际使用体验微调
    chinese_ratio = len(chinese_chars) / len(stripped_text)
    
    if len(chinese_chars) > 2 or chinese_ratio > 0.05:
        return False
        
    # 还需要确保文本里确实有英文字母，而不是全数字或标点
    has_english_letters = bool(re.search(r'[a-zA-Z]', text))
    return has_english_letters


def translate_to_chinese(text: str, timeout: float = 3.0) -> str | None:
    """
    使用免费接口尝试把英文翻译成中文。
    出错或超时时返回 None。
    """
    if not text or not text.strip():
        return None
        
    # 使用 Google Translate 的免费公开接口 (客户端端点)
    # 虽然有时候会有频控，但在划词翻译的低频场景下通常足够稳定且不需要 Key。
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=" + urllib.parse.quote(text)
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            # Google Translate API 返回的格式形如：
            # [[[翻译结果片段1, 原文片段1, ...], [翻译结果片段2, ...]], ...]
            if result and isinstance(result, list) and len(result) > 0:
                translated_parts = [part[0] for part in result[0] if part[0]]
                translated_text = "".join(translated_parts)
                LOGGER.info("Successfully translated text to Chinese (%d chars -> %d chars)", len(text), len(translated_text))
                return translated_text
                
    except Exception as exc:
        LOGGER.warning("Translation failed: %s", exc)
        return None
        
    return None
