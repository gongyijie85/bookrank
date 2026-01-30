"""
翻译服务模块

使用LibreTranslate API进行免费翻译
支持多实例轮询和翻译缓存
"""

import logging
import time
import hashlib
import json
import os
from typing import Optional, List
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)


class TranslationCache:
    """翻译缓存类（使用文件缓存）"""
    
    def __init__(self, cache_file='translation_cache.json'):
        self.cache_file = cache_file
        self.cache = self._load_cache()
    
    def _load_cache(self):
        """加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")
        return {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def get(self, text_hash):
        """获取缓存"""
        entry = self.cache.get(text_hash)
        if entry:
            entry['use_count'] = entry.get('use_count', 0) + 1
            self._save_cache()
            return entry.get('translated_text')
        return None
    
    def set(self, text_hash, original_text, translated_text, source_lang, target_lang):
        """设置缓存"""
        self.cache[text_hash] = {
            'original_text': original_text,
            'translated_text': translated_text,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'created_at': datetime.now().isoformat(),
            'use_count': 1
        }
        self._save_cache()
    
    def get_stats(self):
        """获取统计"""
        total_entries = len(self.cache)
        total_uses = sum(entry.get('use_count', 0) for entry in self.cache.values())
        return {
            'total_entries': total_entries,
            'total_uses': total_uses,
            'avg_uses_per_entry': round(total_uses / total_entries, 2) if total_entries > 0 else 0
        }


class LibreTranslateService:
    """
    LibreTranslate翻译服务
    
    特点：
    - 完全免费，无需注册
    - 支持多个公共实例轮询
    - 内置翻译缓存
    - 自动错误处理和重试
    """
    
    # 可用的公共API实例
    API_URLS = [
        'https://libretranslate.de/translate',
        'https://libretranslate.com/translate',
        'https://translate.argosopentech.com/translate',
        'https://libretranslate.pussthecat.org/translate'
    ]
    
    def __init__(self, delay: float = 0.5, max_retries: int = 3):
        """
        初始化翻译服务
        
        Args:
            delay: 请求间隔（秒）
            max_retries: 最大重试次数
        """
        self.delay = delay
        self.max_retries = max_retries
        self.current_api_index = 0
        self.cache = TranslationCache()
        
    def _get_text_hash(self, text: str, source_lang: str, target_lang: str) -> str:
        """生成文本哈希用于缓存"""
        content = f"{text}:{source_lang}:{target_lang}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _get_from_cache(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """从缓存获取翻译"""
        try:
            text_hash = self._get_text_hash(text, source_lang, target_lang)
            cached = self.cache.get(text_hash)
            if cached:
                logger.debug(f"缓存命中: {text[:50]}...")
                return cached
        except Exception as e:
            logger.error(f"读取缓存失败: {e}")
        
        return None
    
    def _save_to_cache(self, original: str, translated: str, 
                       source_lang: str, target_lang: str):
        """保存翻译到缓存"""
        try:
            text_hash = self._get_text_hash(original, source_lang, target_lang)
            self.cache.set(text_hash, original, translated, source_lang, target_lang)
            logger.debug(f"缓存已保存: {original[:50]}...")
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh', use_cache: bool = True) -> Optional[str]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            use_cache: 是否使用缓存
        
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 限制文本长度（LibreTranslate建议单次不超过1000字符）
        if len(text) > 1000:
            logger.warning(f"文本过长({len(text)}字符)，将截断翻译")
            text = text[:1000]
        
        # 检查缓存
        if use_cache:
            cached = self._get_from_cache(text, source_lang, target_lang)
            if cached:
                return cached
        
        # 添加延迟
        time.sleep(self.delay)
        
        # 尝试所有API实例
        for attempt in range(self.max_retries):
            for i in range(len(self.API_URLS)):
                url = self.API_URLS[(self.current_api_index + i) % len(self.API_URLS)]
                
                try:
                    data = {
                        'q': text,
                        'source': source_lang,
                        'target': target_lang,
                        'format': 'text'
                    }
                    
                    response = requests.post(url, data=data, timeout=30)
                    
                    if response.status_code == 200:
                        result = response.json()
                        translated = result.get('translatedText')
                        
                        if translated:
                            # 保存到缓存
                            if use_cache:
                                self._save_to_cache(text, translated, source_lang, target_lang)
                            
                            logger.info(f"翻译成功: {text[:50]}... -> {translated[:50]}...")
                            return translated
                    else:
                        logger.warning(f"API返回错误 {response.status_code}: {url}")
                        
                except requests.exceptions.Timeout:
                    logger.warning(f"请求超时: {url}")
                except requests.exceptions.RequestException as e:
                    logger.warning(f"请求失败: {url}, 错误: {e}")
                except Exception as e:
                    logger.error(f"未知错误: {url}, 错误: {e}")
            
            # 重试前等待
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        
        logger.error(f"所有API实例都失败，返回原文")
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
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return self.cache.get_stats()
    
    def clear_cache(self, days: int = 30):
        """
        清理过期缓存
        
        Args:
            days: 清理多少天前的缓存
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            keys_to_remove = []
            
            for key, entry in self.cache.cache.items():
                created_at = entry.get('created_at')
                if created_at:
                    try:
                        entry_date = datetime.fromisoformat(created_at)
                        if entry_date < cutoff_date:
                            keys_to_remove.append(key)
                    except:
                        pass
            
            for key in keys_to_remove:
                del self.cache.cache[key]
            
            self.cache._save_cache()
            logger.info(f"清理了 {len(keys_to_remove)} 条过期缓存")
            return len(keys_to_remove)
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return 0


# 全局翻译服务实例
translation_service = LibreTranslateService()


def translate_book_info(book_data: dict, target_lang: str = 'zh') -> dict:
    """
    翻译图书信息
    
    Args:
        book_data: 图书数据字典
        target_lang: 目标语言
    
    Returns:
        添加翻译字段的图书数据
    """
    service = LibreTranslateService()
    
    # 需要翻译的字段
    fields_to_translate = ['description', 'details']
    
    for field in fields_to_translate:
        original = book_data.get(field, '')
        if original and original not in ['No summary available.', 'No detailed description available.']:
            translated = service.translate(original, target_lang=target_lang)
            if translated:
                book_data[f'{field}_zh'] = translated
    
    return book_data