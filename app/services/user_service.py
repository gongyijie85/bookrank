import logging
from datetime import UTC, datetime
from typing import Any

from ..models.database import db
from ..models.schemas import BookMetadata, SearchHistory, UserCategory, UserPreference, UserViewedBook

logger = logging.getLogger(__name__)


class UserService:
    """用户相关数据库操作服务"""

    def save_user_categories(self, session_id: str, category_ids: list[str]) -> None:
        """保存用户分类偏好"""
        try:
            preference = UserPreference.query.get(session_id)
            if not preference:
                preference = UserPreference(session_id=session_id)
                db.session.add(preference)

            UserCategory.query.filter_by(session_id=session_id).delete()

            for cat_id in category_ids:
                db.session.add(UserCategory(session_id=session_id, category_id=cat_id))

            db.session.commit()
        except Exception as e:
            logger.error(f'Failed to save user categories: {e}')
            db.session.rollback()

    def save_viewed_books(self, session_id: str, isbns: list[str]) -> None:
        """保存用户浏览记录（自动去重）"""
        try:
            for isbn in isbns:
                existing = UserViewedBook.query.filter_by(session_id=session_id, isbn=isbn).first()
                if not existing:
                    db.session.add(UserViewedBook(session_id=session_id, isbn=isbn))
            db.session.commit()
        except Exception as e:
            logger.error(f'Failed to save viewed books: {e}')
            db.session.rollback()

    def save_search_history(self, session_id: str, keyword: str, result_count: int) -> None:
        """保存搜索历史"""
        try:
            db.session.add(SearchHistory(session_id=session_id, keyword=keyword, result_count=result_count))
            db.session.commit()
        except Exception as e:
            logger.error(f'Failed to save search history: {e}')
            db.session.rollback()

    def get_preferences(self, session_id: str) -> dict[str, Any]:
        """获取用户偏好"""
        preference = db.session.get(UserPreference, session_id)
        if preference:
            return preference.to_dict()
        return {}

    def update_preferences(self, session_id: str, data: dict[str, Any]) -> None:
        """更新用户偏好"""
        try:
            preference = db.session.get(UserPreference, session_id)
            if not preference:
                preference = UserPreference(session_id=session_id)
                db.session.add(preference)

            view_mode = data.get('view_mode')
            if view_mode in ['grid', 'list']:
                preference.view_mode = view_mode

            db.session.commit()
        except Exception as e:
            logger.error(f'Failed to update preferences: {e}')
            db.session.rollback()

    def get_search_history(self, session_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """获取搜索历史"""
        history = (
            SearchHistory.query.filter_by(session_id=session_id)
            .order_by(SearchHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        return [h.to_dict() for h in history]

    def get_book_metadata(self, isbn: str) -> BookMetadata | None:
        """获取图书元数据（翻译缓存）"""
        try:
            return db.session.get(BookMetadata, isbn)
        except Exception as e:
            logger.error(f'获取图书元数据失败: {e}')
            return None

    def save_book_translation(self, isbn: str, title_zh: str | None = None, description_zh: str | None = None, details_zh: str | None = None) -> bool:
        """
        保存或更新图书翻译缓存

        Args:
            isbn: ISBN
            title_zh: 中文书名（可选）
            description_zh: 中文简介（可选）
            details_zh: 中文详情（可选）

        Returns:
            是否成功
        """
        try:
            meta = db.session.get(BookMetadata, isbn)
            if not meta:
                meta = BookMetadata(isbn=isbn, title=title_zh or isbn, author='Unknown Author')
                db.session.add(meta)

            if title_zh:
                meta.title_zh = title_zh
            if description_zh:
                meta.description_zh = description_zh
            if details_zh:
                meta.details_zh = details_zh

            meta.translated_at = datetime.now(UTC)
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f'保存翻译失败 ISBN {isbn}: {e}')
            db.session.rollback()
            return False
