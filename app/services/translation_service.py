"""
翻译服务模块

使用LibreTranslate API进行免费翻译
支持多实例轮询和翻译缓存
"""

import logging
import time
import hashlib
from typing import Optional, List
from datetime import datetime, timedelta

import requests

from ..models.database import db

logger = logging.getLogger(__name__)


class TranslationCache(db.Model):
    """翻译缓存表"""
    __tablename__ = 'translation_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    text_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    original_text = db.Column(db.Text, nullable=False)
    translated_text = db.Column(db.Text, nullable=False)
    source_lang = db.Column(db.String(10), default='en')
    target_lang = db.Column(db.String(10), default='zh')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    use_count = db.Column(db.Integer, default=1)  # 使用次数统计
    
    def to_dict(self):
        return {
            'id': self.id,
            'original_text': self.original_text,
            'translated_text': self.translated_text,
            'source_lang': self.source_lang,
            'target_lang': self.target_lang,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'use_count': self.use_count
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
        
    def _get_text_hash(self, text: str, source_lang: str, target_lang: str) -> str:
        """生成文本哈希用于缓存"""
        content = f"{text}:{source_lang}:{target_lang}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _get_from_cache(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """从缓存获取翻译"""
        try:
            text_hash = self._get_text_hash(text, source_lang, target_lang)
            cache_entry = TranslationCache.query.filter_by(
                text_hash=text_hash
            ).first()
            
            if cache_entry:
                # 更新使用次数
                cache_entry.use_count += 1
                db.session.commit()
                logger.debug(f"缓存命中: {text[:50]}...")
                return cache_entry.translated_text
                
        except Exception as e:
            logger.error(f"读取缓存失败: {e}")
        
        return None
    
    def _save_to_cache(self, original: str, translated: str, 
                       source_lang: str, target_lang: str):
        """保存翻译到缓存"""
        try:
            text_hash = self._get_text_hash(original, source_lang, target_lang)
            
            # 检查是否已存在
            existing = TranslationCache.query.filter_by(text_hash=text_hash).first()
            if existing:
                existing.translated_text = translated
                existing.updated_at = datetime.utcnow()
            else:
                cache_entry = TranslationCache(
                    text_hash=text_hash,
                    original_text=original,
                    translated_text=translated,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
                db.session.add(cache_entry)
            
            db.session.commit()
            logger.debug(f"缓存已保存: {original[:50]}...")
            
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            db.session.rollback()
    
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
        try:
            total_entries = TranslationCache.query.count()
            total_uses = db.session.query(db.func.sum(TranslationCache.use_count)).scalar() or 0
            
            return {
                'total_entries': total_entries,
                'total_uses': int(total_uses),
                'avg_uses_per_entry': round(total_uses / total_entries, 2) if total_entries > 0 else 0
            }
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {'total_entries': 0, 'total_uses': 0, 'avg_uses_per_entry': 0}
    
    def clear_cache(self, days: int = 30):
        """
        清理过期缓存
        
        Args:
            days: 清理多少天前的缓存
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            deleted = TranslationCache.query.filter(
                TranslationCache.updated_at < cutoff_date
            ).delete()
            db.session.commit()
            logger.info(f"清理了 {deleted} 条过期缓存")
            return deleted
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            db.session.rollback()
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