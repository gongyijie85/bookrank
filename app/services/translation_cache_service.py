"""
翻译缓存服务 - 提供高效的翻译内容缓存和复用
"""

import hashlib
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..models.database import db
from ..models.schemas import TranslationCache
from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


class TranslationCacheService:
    """翻译缓存服务类"""

    CACHE_VERSION = 3  # 递增此值可使旧缓存失效（v3: 切换 Hunyuan-MT-7B 实测，作废旧 GLM 缓存，避免命中旧结果）

    def __init__(self):
        self.default_model = os.environ.get('TRANSLATION_MODEL') or 'glm-4.7-flash'

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
        target_lang: str = 'zh',
        model_name: str | None = None,
    ) -> TranslationCache | None:
        """
        从缓存中获取翻译结果

        Args:
            source_text: 源文本
            source_lang: 源语言
            target_lang: 目标语言
            model_name: 期望的模型名；指定后不会复用其他模型的缓存

        Returns:
            TranslationCache对象或None
        """
        if not source_text or not source_text.strip():
            return None

        source_hash = self._compute_source_hash(source_text)

        # 查找缓存
        cache = TranslationCache.query.filter_by(
            source_hash=source_hash, source_lang=source_lang, target_lang=target_lang
        ).first()

        if cache:
            if model_name is not None and cache.model_name != model_name:
                logger.info(f'缓存模型不匹配({cache.model_name!r} != {model_name!r})，视为未命中')
                return None

            # 版本检查：版本不匹配的缓存视为无效
            if hasattr(cache, 'model_version') and cache.model_version:
                try:
                    cached_version = int(cache.model_version)
                    if cached_version < self.CACHE_VERSION:
                        logger.info(f'缓存版本过期(v{cached_version} < v{self.CACHE_VERSION})，删除')
                        try:
                            db.session.delete(cache)
                            db.session.commit()
                        except Exception as e:
                            log_error(ErrorCategory.TRANSLATION, f'删除过期缓存失败(版本检查): {e}', level='warning')
                            db.session.rollback()
                        return None
                except (ValueError, TypeError):
                    pass
            else:
                # 无版本号的旧缓存，视为过期
                logger.info('缓存无版本号，视为过期')
                try:
                    db.session.delete(cache)
                    db.session.commit()
                except Exception as e:
                    log_error(ErrorCategory.TRANSLATION, f'删除过期缓存失败(无版本号): {e}', level='warning')
                    db.session.rollback()
                return None

            logger.debug(f'缓存命中: {source_lang}->{target_lang}, 已使用{cache.usage_count}次')
            return cache

        logger.debug(f'缓存未命中: {source_lang}->{target_lang}')
        return None

    def set(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str = 'en',
        target_lang: str = 'zh',
        model_name: str | None = None,
        model_version: str | None = None,
        quality_score: float | None = None,
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
            raise ValueError('源文本和翻译结果不能为空')

        source_hash = self._compute_source_hash(source_text)

        # 检查是否已存在
        existing = TranslationCache.query.filter_by(
            source_hash=source_hash, source_lang=source_lang, target_lang=target_lang
        ).first()

        if existing:
            # 更新现有缓存
            existing.translated_text = translated_text
            existing.model_name = model_name or self.default_model
            existing.model_version = model_version
            existing.quality_score = quality_score
            existing.last_used_at = datetime.now(UTC)
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
                last_used_at=datetime.now(UTC),
            )
            db.session.add(existing)

        try:
            db.session.commit()
            logger.info(f'翻译缓存已保存: {source_lang}->{target_lang}')
            return existing
        except IntegrityError:
            db.session.rollback()
            existing = TranslationCache.query.filter_by(
                source_hash=source_hash, source_lang=source_lang, target_lang=target_lang
            ).first()
            if existing:
                existing.translated_text = translated_text
                existing.model_name = model_name or self.default_model
                existing.model_version = model_version
                existing.quality_score = quality_score
                existing.last_used_at = datetime.now(UTC)
                existing.usage_count += 1
                db.session.commit()
                logger.info(f'翻译缓存已更新(并发冲突): {source_lang}->{target_lang}')
                return existing
            raise
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'保存翻译缓存失败: {e}')
            db.session.rollback()
            raise

    def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        total_count = TranslationCache.query.count()

        # 按语言统计
        en_to_zh = TranslationCache.query.filter_by(source_lang='en', target_lang='zh').count()

        zh_to_en = TranslationCache.query.filter_by(source_lang='zh', target_lang='en').count()

        # 最近24小时新增
        yesterday = datetime.now(UTC) - timedelta(days=1)
        recent_count = TranslationCache.query.filter(TranslationCache.created_at >= yesterday).count()

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
            'model_name': self.default_model,
        }

    def get_recent(
        self, limit: int = 50, source_lang: str | None = None, target_lang: str | None = None
    ) -> list[TranslationCache]:
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

        return query.order_by(TranslationCache.last_used_at.desc()).limit(limit).all()

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
            logger.info(f'缓存数量({total_count})未超过限制({max_items})，无需清理')
            return 0

        # 保留的记录：
        # 1. 最近30天有使用记录的
        # 2. 使用次数超过10次的
        # 3. 最近7天创建的
        keep_date = datetime.now(UTC) - timedelta(days=keep_recent_days)

        records_to_keep = (
            db.session.query(TranslationCache.id)
            .filter(
                db.or_(
                    TranslationCache.last_used_at >= keep_date,
                    TranslationCache.usage_count >= 10,
                    TranslationCache.created_at >= keep_date,
                )
            )
            .scalar_subquery()
        )

        # 删除不在保留范围内的记录
        deleted = TranslationCache.query.filter(~TranslationCache.id.in_(records_to_keep)).delete(
            synchronize_session=False
        )

        try:
            db.session.commit()
            logger.info(f'自动清理完成，删除了 {deleted} 条缓存记录')
            return deleted
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'自动清理缓存失败: {e}')
            db.session.rollback()
            raise

    def delete(
        self, cache_id: int | None = None, older_than_days: int | None = None, min_usage: int | None = None
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
                cutoff_date = datetime.now(UTC) - timedelta(days=older_than_days)
                query = query.filter(TranslationCache.created_at < cutoff_date)

            if min_usage is not None:
                query = query.filter(TranslationCache.usage_count < min_usage)

        deleted_count = query.delete()
        try:
            db.session.commit()
            logger.info(f'已删除 {deleted_count} 条翻译缓存')
            return deleted_count
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'删除翻译缓存失败: {e}')
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
            logger.warning(f'已清空所有翻译缓存（{count}条）')
            return count
        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'清空翻译缓存失败: {e}')
            db.session.rollback()
            raise


# 全局缓存服务实例
_translation_cache_service: TranslationCacheService | None = None


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
