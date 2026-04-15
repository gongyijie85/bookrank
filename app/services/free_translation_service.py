"""
免费翻译服务集合

包含多个免费翻译方案：
1. Google Translate (deep-translator) - 免费但可能不稳定
2. LibreTranslate 公共实例 - 免费但有请求限制
3. MyMemory - 免费但有每日限额
"""

import logging
import json
import time
import random
from typing import Optional, List
from datetime import datetime, timedelta

import requests

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
        
    def _get_client(self):
        """懒加载客户端"""
        if self._client is None:
            try:
                from deep_translator import GoogleTranslator
                self._client = GoogleTranslator
                logger.info("Google Translate 客户端初始化成功")
            except ImportError as e:
                logger.error(f"deep-translator 库未安装: {e}")
                return None
        return self._client
    
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        使用 Google Translate 翻译文本
        
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
        
        client_class = self._get_client()
        if not client_class:
            return None
        
        try:
            # 语言代码转换
            lang_map = {
                'zh': 'zh-CN',
                'en': 'en',
                'auto': 'auto'
            }
            source = lang_map.get(source_lang, source_lang)
            target = lang_map.get(target_lang, target_lang)
            
            translator = client_class(source=source, target=target)
            result = translator.translate(text)
            
            self._last_request_time = time.time()
            
            if result:
                logger.info(f"Google翻译成功: {text[:50]}... -> {result[:50]}...")
                return result
                
        except Exception as e:
            logger.warning(f"Google翻译失败: {e}")
        
        return None


class LibreTranslatePublicService:
    """
    LibreTranslate 公共免费实例
    
    可用的公共实例：
    - https://libretranslate.de
    - https://libretranslate.pussthecat.org
    - https://translate.argosopentech.com
    - https://libretranslate.eownerdead.de
    """
    
    # 公共实例列表
    INSTANCES = [
        'https://libretranslate.de',
        'https://libretranslate.pussthecat.org',
        'https://translate.argosopentech.com',
        'https://libretranslate.eownerdead.de',
    ]
    
    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._failed_instances = set()
        self._last_request_time = 0
        
    def _get_available_instance(self) -> Optional[str]:
        """获取可用的实例"""
        available = [i for i in self.INSTANCES if i not in self._failed_instances]
        if available:
            return random.choice(available)
        return None
    
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        使用 LibreTranslate 公共实例翻译
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 添加延迟
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        # 语言代码转换
        lang_map = {
            'zh': 'zh',
            'en': 'en',
            'auto': 'auto'
        }
        source = lang_map.get(source_lang, source_lang)
        target = lang_map.get(target_lang, target_lang)
        
        # 尝试各个实例
        for _ in range(len(self.INSTANCES)):
            instance = self._get_available_instance()
            if not instance:
                break
            
            try:
                url = f"{instance}/translate"
                payload = {
                    'q': text,
                    'source': source,
                    'target': target,
                    'format': 'text'
                }
                
                logger.debug(f"尝试 LibreTranslate 实例: {instance}")
                response = requests.post(url, json=payload, timeout=30)
                
                self._last_request_time = time.time()
                
                if response.status_code == 200:
                    result = response.json()
                    translated = result.get('translatedText')
                    if translated:
                        logger.info(f"LibreTranslate翻译成功 ({instance}): {text[:50]}... -> {translated[:50]}...")
                        return translated
                else:
                    logger.warning(f"LibreTranslate实例 {instance} 返回错误: {response.status_code}")
                    self._failed_instances.add(instance)
                    
            except requests.exceptions.Timeout:
                logger.warning(f"LibreTranslate实例 {instance} 超时")
                self._failed_instances.add(instance)
            except requests.exceptions.RequestException as e:
                logger.warning(f"LibreTranslate实例 {instance} 请求失败: {e}")
                self._failed_instances.add(instance)
            except Exception as e:
                logger.error(f"LibreTranslate未知错误: {e}")
        
        logger.error("所有LibreTranslate实例都不可用")
        return None


class FreeTranslationService:
    """
    免费翻译服务聚合
    
    按优先级尝试各种免费翻译方案：
    1. Google Translate (deep-translator)
    2. LibreTranslate 公共实例
    3. MyMemory (备用)
    """
    
    def __init__(self):
        self.google = GoogleTranslationService()
        self.libre = LibreTranslatePublicService()
        
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本，自动选择可用的免费API
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 首先尝试 Google Translate
        logger.info("尝试使用 Google Translate...")
        result = self.google.translate(text, source_lang, target_lang)
        if result:
            return result
        
        # Google 失败，尝试 LibreTranslate
        logger.info("Google 不可用，切换到 LibreTranslate...")
        result = self.libre.translate(text, source_lang, target_lang)
        if result:
            return result
        
        logger.error("所有免费翻译API都不可用")
        return None
    
    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh', progress_callback=None) -> List[str]:
        """
        批量翻译
        
        Args:
            texts: 文本列表
            source_lang: 源语言
            target_lang: 目标语言
            progress_callback: 进度回调函数 (current, total)
        
        Returns:
            翻译结果列表
        """
        results = []
        total = len(texts)
        
        for i, text in enumerate(texts):
            if progress_callback:
                progress_callback(i + 1, total)
            
            result = self.translate(text, source_lang, target_lang)
            results.append(result if result else text)
        
        return results
