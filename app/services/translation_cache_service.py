"""
翻译缓存服务 - 提供高效的翻译内容缓存和复用
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import or_, func

from ..models.database import db
from ..models.schemas import TranslationCache

logger = logging.getLogger(__name__)


class TranslationCacheService:
    """翻译缓存服务类"""
    
    def __init__(self):
        self.default_model = 'glm-4-flash'
    
    @staticmethod
    def _compute_source_hash(text: str) -> str:
        """
        计算源文本的SHA-256哈希值
        
        Args:
            text: 源文本
            
        Returns:
            哈希值字符串（前64个字符）
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def get(
        self,
        source_text: str,
        source_lang: str = 'en',
        target_lang: str = 'zh'
    ) -> Optional[TranslationCache]:
        """
        从缓存中获取翻译结果
        
        Args:
            source_text: 源文本
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            TranslationCache对象或None
        """
        if not source_text or not source_text.strip():
            return None
        
        source_hash = self._compute_source_hash(source_text)
        
        # 查找缓存
        cache = TranslationCache.query.filter_by(
            source_hash=source_hash,
            source_lang=source_lang,
            target_lang=target_lang
        ).first()
        
        if cache:
            # 更新使用记录
            cache.usage_count += 1
            cache.last_used_at = datetime.now(timezone.utc)
            try:
                db.session.commit()
            except Exception as e:
                logger.error(f"更新缓存使用记录失败: {e}")
                db.session.rollback()
            
            logger.debug(f"缓存命中: {source_lang}->{target_lang}, 已使用{cache.usage_count}次")
            return cache
        
        logger.debug(f"缓存未命中: {source_lang}->{target_lang}")
        return None
    
    def set(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str = 'en',
        target_lang: str = 'zh',
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        quality_score: Optional[float] = None
    ) -> TranslationCache:
        """
        保存翻译结果到缓存
        
        Args:
            source_text: 源文本
            translated_text: 翻译结果
            source_lang: 源语言
            target_lang: 目标语言
            model_name: 使用的模型名称
            model_version: 模型版本
            quality_score: 翻译质量评分 (0-1)
            
        Returns:
            TranslationCache对象
        """
        if not source_text or not translated_text:
            raise ValueError("源文本和翻译结果不能为空")
        
        source_hash = self._compute_source_hash(source_text)
        
        # 检查是否已存在
        existing = TranslationCache.query.filter_by(
            source_hash=source_hash,
            source_lang=source_lang,
            target_lang=target_lang
        ).first()
        
        if existing:
            # 更新现有缓存
            existing.translated_text = translated_text
            existing.model_name = model_name or self.default_model
            existing.model_version = model_version
            existing.quality_score = quality_score
            existing.last_used_at = datetime.now(timezone.utc)
            existing.usage_count += 1
        else:
            # 创建新缓存
            existing = TranslationCache(
                source_hash=source_hash,
                source_text=source_text,
                source_lang=source_lang,
                target_lang=target_lang,
                translated_text=translated_text,
                model_name=model_name or self.default_model,
                model_version=model_version,
                quality_score=quality_score,
                usage_count=1,
                last_used_at=datetime.now(timezone.utc)
            )
            db.session.add(existing)
        
        try:
            db.session.commit()
            logger.info(f"翻译缓存已保存: {source_lang}->{target_lang}")
            return existing
        except Exception as e:
            logger.error(f"保存翻译缓存失败: {e}")
            db.session.rollback()
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        total_count = TranslationCache.query.count()
        
        # 按语言统计
        en_to_zh = TranslationCache.query.filter_by(
            source_lang='en', target_lang='zh'
        ).count()
        
        zh_to_en = TranslationCache.query.filter_by(
            source_lang='zh', target_lang='en'
        ).count()
        
        # 最近24小时新增
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_count = TranslationCache.query.filter(
            TranslationCache.created_at >= yesterday
        ).count()
        
        # 总使用次数
        total_usage = db.session.query(func.sum(TranslationCache.usage_count)).scalar() or 0
        
        # 缓存命中率（估算）
        avg_usage = total_usage / total_count if total_count > 0 else 0
        
        return {
            'total_count': total_count,
            'en_to_zh_count': en_to_zh,
            'zh_to_en_count': zh_to_en,
            'recent_24h_count': recent_count,
            'total_usage_count': total_usage,
            'avg_usage_per_item': round(avg_usage, 2),
            'model_name': self.default_model
        }
    
    def get_recent(
        self,
        limit: int = 50,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None
    ) -> List[TranslationCache]:
        """
        获取最近的缓存记录
        
        Args:
            limit: 返回数量限制
            source_lang: 源语言筛选
            target_lang: 目标语言筛选
            
        Returns:
            TranslationCache查询结果列表
        """
        query = TranslationCache.query
        
        if source_lang:
            query = query.filter_by(source_lang=source_lang)
        
        if target_lang:
            query = query.filter_by(target_lang=target_lang)
        
        return query.order_by(
            TranslationCache.last_used_at.desc()
        ).limit(limit).all()
    
    def search(
        self,
        keyword: str,
        limit: int = 50,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None
    ) -> List[TranslationCache]:
        """
        搜索缓存记录
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            source_lang: 源语言筛选
            target_lang: 目标语言筛选
            
        Returns:
            匹配的缓存记录列表
        """
        query = TranslationCache.query.filter(
            or_(
                TranslationCache.source_text.ilike(f'%{keyword}%'),
                TranslationCache.translated_text.ilike(f'%{keyword}%')
            )
        )
        
        if source_lang:
            query = query.filter_by(source_lang=source_lang)
        
        if target_lang:
            query = query.filter_by(target_lang=target_lang)
        
        return query.order_by(
            TranslationCache.usage_count.desc()
        ).limit(limit).all()
    
    def get_least_used(
        self,
        limit: int = 100,
        older_than_days: Optional[int] = None
    ) -> List[TranslationCache]:
        """
        获取最少使用的缓存记录（用于清理）
        
        Args:
            limit: 返回数量限制
            older_than_days: 筛选N天前的记录
            
        Returns:
            最少使用的缓存记录列表
        """
        query = TranslationCache.query
        
        if older_than_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
            query = query.filter(TranslationCache.last_used_at < cutoff_date)
        
        return query.order_by(
            TranslationCache.usage_count.asc()
        ).limit(limit).all()
    
    def auto_cleanup(self, max_items: int = 10000, keep_recent_days: int = 30) -> int:
        """
        自动清理缓存，保留热门内容
        
        策略：
        1. 保留最近使用的记录
        2. 保留使用次数多的记录
        3. 删除长期未使用的冷门记录
        
        Args:
            max_items: 最大保留缓存数量
            keep_recent_days: 保留N天内有使用记录的缓存
            
        Returns:
            删除的记录数
        """
        total_count = TranslationCache.query.count()
        
        if total_count <= max_items:
            logger.info(f"缓存数量({total_count})未超过限制({max_items})，无需清理")
            return 0
        
        # 保留的记录：
        # 1. 最近30天有使用记录的
        # 2. 使用次数超过10次的
        # 3. 最近7天创建的
        keep_date = datetime.now(timezone.utc) - timedelta(days=keep_recent_days)
        
        records_to_keep = db.session.query(TranslationCache.id).filter(
            db.or_(
                TranslationCache.last_used_at >= keep_date,
                TranslationCache.usage_count >= 10,
                TranslationCache.created_at >= keep_date
            )
        ).subquery()
        
        # 删除不在保留范围内的记录
        deleted = TranslationCache.query.filter(
            ~TranslationCache.id.in_(records_to_keep)
        ).delete(synchronize_session=False)
        
        try:
            db.session.commit()
            logger.info(f"自动清理完成，删除了 {deleted} 条缓存记录")
            return deleted
        except Exception as e:
            logger.error(f"自动清理缓存失败: {e}")
            db.session.rollback()
            raise
    
    def delete(
        self,
        cache_id: Optional[int] = None,
        older_than_days: Optional[int] = None,
        min_usage: Optional[int] = None
    ) -> int:
        """
        删除缓存记录
        
        Args:
            cache_id: 特定缓存ID
            older_than_days: 删除N天前的记录
            min_usage: 删除使用次数少于此值的记录
            
        Returns:
            删除的记录数
        """
        query = TranslationCache.query
        
        if cache_id:
            query = query.filter_by(id=cache_id)
        else:
            if older_than_days:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
                query = query.filter(TranslationCache.created_at < cutoff_date)
            
            if min_usage is not None:
                query = query.filter(TranslationCache.usage_count < min_usage)
        
        deleted_count = query.delete()
        try:
            db.session.commit()
            logger.info(f"已删除 {deleted_count} 条翻译缓存")
            return deleted_count
        except Exception as e:
            logger.error(f"删除翻译缓存失败: {e}")
            db.session.rollback()
            raise
    
    def clear_all(self) -> int:
        """
        清空所有缓存
        
        Returns:
            删除的记录数
        """
        count = TranslationCache.query.delete()
        try:
            db.session.commit()
            logger.warning(f"已清空所有翻译缓存（{count}条）")
            return count
        except Exception as e:
            logger.error(f"清空翻译缓存失败: {e}")
            db.session.rollback()
            raise
    
    def export_cache(self, format: str = 'json') -> Dict[str, Any]:
        """
        导出缓存数据
        
        Args:
            format: 导出格式 ('json' 或 'csv')
            
        Returns:
            导出数据
        """
        caches = TranslationCache.query.order_by(
            TranslationCache.usage_count.desc()
        ).limit(1000).all()
        
        if format == 'json':
            return {
                'total': len(caches),
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'data': [c.to_dict() for c in caches]
            }
        else:
            # CSV 格式
            lines = ['source_text,translated_text,source_lang,target_lang,usage_count']
            for c in caches:
                lines.append(f'"{c.source_text}","{c.translated_text}",{c.source_lang},{c.target_lang},{c.usage_count}')
            return {'total': len(caches), 'csv': '\n'.join(lines)}


# 全局缓存服务实例
_translation_cache_service: Optional[TranslationCacheService] = None


def get_translation_cache_service() -> TranslationCacheService:
    """
    获取翻译缓存服务单例
    
    Returns:
        TranslationCacheService实例
    """
    global _translation_cache_service
    if _translation_cache_service is None:
        _translation_cache_service = TranslationCacheService()
    return _translation_cache_service
