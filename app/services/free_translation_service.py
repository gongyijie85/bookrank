"""
免费翻译服务集合

包含免费翻译方案：
1. Google Translate (deep-translator) - 免费但可能不稳定
"""

import logging
import time
from typing import Optional, List

logger = logging.getLogger(__name__)


class GoogleTranslationService:
    """
    Google Translate 免费翻译服务
    使用 deep-translator 库（免费但可能不稳定）
    """
    
    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self._client = None
        self._last_request_time = 0
        self._deep_translator_warned = False

    def _get_client(self):
        """懒加载客户端"""
        if self._client is None:
            try:
                from deep_translator import GoogleTranslator
                self._client = GoogleTranslator
                logger.info("Google Translate 客户端初始化成功")
            except ImportError as e:
                if not self._deep_translator_warned:
                    logger.debug(f"deep-translator 库未安装，Google 免费翻译不可用: {e}")
                    self._deep_translator_warned = True
                return None
        return self._client
    
    def translate(self, text: str, source_lang: str = 'en',
                  target_lang: str = 'zh') -> Optional[str]:
        if not text or not text.strip():
            return text

        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)

        client_class = self._get_client()
        if not client_class:
            return None

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                lang_map = {'zh': 'zh-CN', 'en': 'en', 'auto': 'auto'}
                source = lang_map.get(source_lang, source_lang)
                target = lang_map.get(target_lang, target_lang)

                translator = client_class(source=source, target=target)
                result = translator.translate(text)

                self._last_request_time = time.time()

                if result:
                    logger.info(f"Google翻译成功: {text[:50]}... -> {result[:50]}...")
                    return result

            except Exception as e:
                if attempt < max_retries:
                    logger.debug(f"Google翻译失败(第{attempt + 1}次)，重试中: {e}")
                    time.sleep(1.0 * (attempt + 1))
                else:
                    logger.warning(f"Google翻译失败(重试耗尽): {e}")

        return None


class FreeTranslationService:
    """免费翻译服务聚合（基于 Google Translate deep-translator）"""
    
    def __init__(self):
        self.google = GoogleTranslationService()
        
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        if not text or not text.strip():
            return text
        
        logger.debug("尝试使用 Google Translate...")
        result = self.google.translate(text, source_lang, target_lang)
        if result:
            return result

        logger.debug("免费翻译API不可用")
        return None
    
    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh',
                       progress_callback=None,
                       max_workers: int = 3) -> List[str]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(texts)
        results = [None] * total

        def _translate_item(item):
            idx, txt = item
            result = self.translate(txt, source_lang, target_lang)
            return idx, result if result else txt

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(_translate_item, (i, text)): i
                for i, text in enumerate(texts)
            }

            completed = 0
            for future in as_completed(future_to_item):
                idx, result = future.result()
                results[idx] = result
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        return results
