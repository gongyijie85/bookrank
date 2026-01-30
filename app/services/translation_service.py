"""
翻译服务 - 简化版，只使用 Google Translate
"""

import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TranslationService:
    """
    翻译服务 - 使用 Google Translate (通过 deep-translator)
    """
    
    def __init__(self, delay: float = 0.3):
        self.delay = delay
        self._last_request_time = 0
        
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 添加延迟避免请求过快
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        try:
            from deep_translator import GoogleTranslator
            
            # 语言代码转换
            lang_map = {
                'zh': 'zh-CN',
                'en': 'en',
                'auto': 'auto'
            }
            source = lang_map.get(source_lang, source_lang)
            target = lang_map.get(target_lang, target_lang)
            
            translator = GoogleTranslator(source=source, target=target)
            result = translator.translate(text)
            
            self._last_request_time = time.time()
            
            if result:
                logger.info(f"翻译成功: {text[:50]}... -> {result[:50]}...")
                return result
                
        except Exception as e:
            logger.warning(f"翻译失败: {e}")
        
        return None
    
    def translate_book_info(self, book_data: Dict[str, Any], 
                           target_lang: str = 'zh') -> Dict[str, Any]:
        """
        翻译图书信息
        
        Args:
            book_data: 图书数据字典
            target_lang: 目标语言
            
        Returns:
            包含翻译字段的图书数据
        """
        result = book_data.copy()
        
        # 翻译描述
        if book_data.get('description'):
            translated_desc = self.translate(book_data['description'], target_lang=target_lang)
            if translated_desc:
                result['description_zh'] = translated_desc
        
        # 翻译详细信息
        if book_data.get('details'):
            translated_details = self.translate(book_data['details'], target_lang=target_lang)
            if translated_details:
                result['details_zh'] = translated_details
        
        return result


# 全局翻译服务实例
translation_service = TranslationService()


def translate_book_info(book_data: Dict[str, Any], target_lang: str = 'zh') -> Dict[str, Any]:
    """翻译图书信息的便捷函数"""
    return translation_service.translate_book_info(book_data, target_lang)
