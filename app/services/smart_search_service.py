"""
智能搜索服务

提供智能化的图书搜索功能:
1. 书名、作者、出版社的智能搜索
2. 搜索建议和自动补全
3. 搜索结果智能排序
"""

import logging
import re
from typing import Any

from sqlalchemy import func, or_

from ..models.new_book import NewBook
from ..models.schemas import AwardBook, SearchHistory, db
from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


class SmartSearchService:
    """智能搜索服务"""

    # 搜索建议缓存时间（秒）
    SUGGESTION_CACHE_TTL = 600

    # 搜索结果缓存时间（秒）
    SEARCH_CACHE_TTL = 300

    def __init__(self, categories: dict | None = None):
        """
        初始化智能搜索服务

        Args:
            categories: 分类字典
        """
        self._categories = categories or {}

    def search(
        self,
        keyword: str,
        search_type: str = 'all',
        year: int | None = None,
        award_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        智能搜索图书

        Args:
            keyword: 搜索关键词
            search_type: 搜索类型 (all/title/author/publisher)
            year: 筛选年份
            award_id: 筛选奖项ID
            limit: 返回结果数量
            offset: 结果偏移量

        Returns:
            搜索结果字典
        """
        try:
            keyword = self._sanitize_keyword(keyword)
            if not keyword:
                return self._empty_search_result()

            limit = min(max(1, limit), 100)
            offset = max(0, offset)

            award_query = AwardBook.query.filter(AwardBook.is_displayable.is_(True))  # type: ignore[attr-defined]
            award_query = self._apply_award_search_conditions(award_query, keyword, search_type)
            if year:
                award_query = award_query.filter(AwardBook.year == year)
            if award_id:
                award_query = award_query.filter(AwardBook.award_id == award_id)

            award_total = award_query.count()
            award_books = (
                award_query.order_by(AwardBook.year.desc(), AwardBook.rank.asc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            award_results = [self._format_book(b) for b in award_books]

            new_book_query = NewBook.query.filter(NewBook.is_displayable.is_(True))  # type: ignore[attr-defined]
            new_book_query = self._apply_new_book_search_conditions(new_book_query, keyword, search_type)
            new_book_total = new_book_query.count()
            new_book_books = (
                new_book_query.order_by(NewBook.publication_date.desc().nullslast())  # type: ignore[union-attr,attr-defined]
                .offset(offset)
                .limit(limit)
                .all()
            )
            new_book_results = [self._format_new_book(b) for b in new_book_books]

            all_results = award_results + new_book_results
            total = award_total + new_book_total

            suggestions = self._generate_suggestions(keyword, search_type)

            return {
                'results': all_results,
                'total': total,
                'keyword': keyword,
                'search_type': search_type,
                'suggestions': suggestions[:5],
                'pagination': {'limit': limit, 'offset': offset, 'has_more': offset + limit < total},
            }

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'搜索失败: {e}')
            return self._empty_search_result()

    def _sanitize_keyword(self, keyword: str) -> str:
        """
        清理和验证搜索关键词

        Args:
            keyword: 原始关键词

        Returns:
            清理后的关键词
        """
        if not keyword:
            return ''

        # 去除首尾空白
        keyword = keyword.strip()

        # 移除特殊字符（保留中英文、数字、空格、连字符）
        keyword = re.sub(r'[^\w\s\u4e00-\u9fff\-]', '', keyword)

        # 压缩多个空格为单个
        keyword = re.sub(r'\s+', ' ', keyword)

        return keyword[:100]  # 限制长度

    def _apply_award_search_conditions(self, query, keyword: str, search_type: str):
        escaped_keyword = keyword.replace('%', r'\%').replace('_', r'\_')
        conditions = []
        if search_type in ('all', 'title'):
            conditions.append(AwardBook.title.ilike(f'%{escaped_keyword}%'))
            conditions.append(AwardBook.title_zh.ilike(f'%{escaped_keyword}%'))
        if search_type in ('all', 'author'):
            conditions.append(AwardBook.author.ilike(f'%{escaped_keyword}%'))
        if search_type in ('all', 'publisher'):
            conditions.append(AwardBook.publisher.ilike(f'%{escaped_keyword}%'))
        return query.filter(or_(*conditions)) if conditions else query

    def _apply_new_book_search_conditions(self, query, keyword: str, search_type: str):
        escaped_keyword = keyword.replace('%', r'\%').replace('_', r'\_')
        conditions = []
        if search_type in ('all', 'title'):
            conditions.append(NewBook.title.ilike(f'%{escaped_keyword}%'))  # type: ignore[attr-defined]
            conditions.append(NewBook.title_zh.ilike(f'%{escaped_keyword}%'))  # type: ignore[union-attr,attr-defined]
        if search_type in ('all', 'author'):
            conditions.append(NewBook.author.ilike(f'%{escaped_keyword}%'))  # type: ignore[attr-defined]
        if search_type in ('all', 'publisher'):
            conditions.append(NewBook.isbn13.ilike(f'%{escaped_keyword}%'))  # type: ignore[union-attr,attr-defined]
        return query.filter(or_(*conditions)) if conditions else query

    def _format_book(self, book: AwardBook) -> dict:
        return {
            'id': book.id,
            'title': book.title,
            'title_zh': book.title_zh,
            'author': book.author,
            'publisher': book.publisher,
            'year': book.year,
            'category': book.category,
            'rank': book.rank,
            'cover_url': book.cover_original_url,
            'isbn13': book.isbn13,
            'source': 'award',
            'award': {'id': book.award_id, 'name': book.award.name if book.award else None} if book.award else None,
        }

    def _format_new_book(self, book: NewBook) -> dict:
        return {
            'id': book.id,
            'title': book.title,
            'title_zh': getattr(book, 'title_zh', None),
            'author': book.author,
            'publisher': book.publisher.name if book.publisher else None,
            'year': book.publication_date.year if book.publication_date else None,
            'category': book.category,
            'rank': None,
            'cover_url': book.cover_url,
            'isbn13': book.isbn13,
            'source': 'new_book',
            'award': None,
        }

    def _empty_search_result(self) -> dict:
        """返回空搜索结果"""
        return {
            'results': [],
            'total': 0,
            'keyword': '',
            'search_type': 'all',
            'suggestions': [],
            'pagination': {'limit': 20, 'offset': 0, 'has_more': False},
        }

    def _generate_suggestions(self, keyword: str, search_type: str) -> list[str]:
        """
        生成搜索建议

        基于搜索历史和热门搜索词生成建议

        Args:
            keyword: 当前搜索关键词
            search_type: 搜索类型

        Returns:
            搜索建议列表
        """
        suggestions = []

        try:
            # 从搜索历史中获取相关建议
            recent_searches = (
                SearchHistory.query.filter(SearchHistory.keyword.ilike(f'{keyword}%'))
                .order_by(SearchHistory.created_at.desc())
                .limit(5)
                .all()
            )

            # 去重并添加建议
            seen = set()
            for search in recent_searches:
                if search.keyword.lower() not in seen:
                    seen.add(search.keyword.lower())
                    suggestions.append(search.keyword)

            # 如果建议不足，从热门搜索补充
            if len(suggestions) < 5:
                popular = (
                    SearchHistory.query.with_entities(
                        SearchHistory.keyword, func.count(SearchHistory.id).label('count')
                    )
                    .group_by(SearchHistory.keyword)
                    .order_by(func.count(SearchHistory.id).desc())
                    .filter(SearchHistory.keyword.ilike(f'{keyword}%'))
                    .limit(5)
                    .all()
                )

                for kw, _count in popular:
                    if kw.lower() not in seen:
                        seen.add(kw.lower())
                        suggestions.append(kw)

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'生成搜索建议失败: {e}', level='warning')

        return suggestions[:5]

    # ==================== 搜索建议API ====================

    def get_suggestions(self, prefix: str, limit: int = 10) -> dict[str, Any]:
        """
        获取搜索建议（自动补全）

        根据用户输入的前缀返回可能的搜索词

        Args:
            prefix: 用户输入的前缀
            limit: 返回建议数量

        Returns:
            建议结果字典
        """
        try:
            # 验证输入
            prefix = self._sanitize_keyword(prefix)
            if not prefix or len(prefix) < 1:
                return {'suggestions': [], 'prefix': prefix}

            # 限制返回数量
            limit = min(max(1, limit), 20)

            suggestions = []

            # 1. 从书名中获取建议
            title_suggestions = (
                AwardBook.query.filter(
                    AwardBook.is_displayable,
                    or_(AwardBook.title.ilike(f'{prefix}%'), AwardBook.title_zh.ilike(f'{prefix}%')),
                )
                .with_entities(AwardBook.title)
                .distinct()
                .limit(limit)
                .all()
            )

            for (title,) in title_suggestions:
                suggestions.append({'text': title, 'type': 'title'})

            # 2. 从作者中获取建议
            if len(suggestions) < limit:
                author_suggestions = (
                    AwardBook.query.filter(AwardBook.is_displayable, AwardBook.author.ilike(f'{prefix}%'))
                    .with_entities(AwardBook.author)
                    .distinct()
                    .limit(limit)
                    .all()
                )

                for (author,) in author_suggestions:
                    if len(suggestions) >= limit:
                        break
                    suggestions.append({'text': author, 'type': 'author'})

            # 3. 从出版社中获取建议
            if len(suggestions) < limit:
                publisher_suggestions = (
                    AwardBook.query.filter(AwardBook.is_displayable, AwardBook.publisher.ilike(f'{prefix}%'))
                    .with_entities(AwardBook.publisher)
                    .distinct()
                    .limit(limit)
                    .all()
                )

                for (publisher,) in publisher_suggestions:
                    if len(suggestions) >= limit:
                        break
                    suggestions.append({'text': publisher, 'type': 'publisher'})

            # 去重（基于文本）
            seen = set()
            unique_suggestions = []
            for s in suggestions:
                text_lower = s['text'].lower()
                if text_lower not in seen:
                    seen.add(text_lower)
                    unique_suggestions.append(s)

            return {'suggestions': unique_suggestions[:limit], 'prefix': prefix}

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'获取搜索建议失败: {e}')
            return {'suggestions': [], 'prefix': prefix, 'error': str(e)}

    # ==================== 热门搜索 ====================

    def get_popular_searches(self, limit: int = 10) -> dict[str, Any]:
        """
        获取热门搜索词

        Args:
            limit: 返回数量

        Returns:
            热门搜索结果
        """
        try:
            # 限制返回数量
            limit = min(max(1, limit), 50)

            # 统计搜索词频率
            popular = (
                SearchHistory.query.with_entities(
                    SearchHistory.keyword,
                    func.count(SearchHistory.id).label('search_count'),
                    func.max(SearchHistory.created_at).label('last_search'),
                )
                .group_by(SearchHistory.keyword)
                .order_by(func.count(SearchHistory.id).desc(), func.max(SearchHistory.created_at).desc())
                .limit(limit)
                .all()
            )

            searches = [
                {'keyword': keyword, 'count': count, 'last_searched': last_search.isoformat() if last_search else None}
                for keyword, count, last_search in popular
            ]

            return {'popular_searches': searches, 'total': len(searches)}

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'获取热门搜索失败: {e}')
            return {'popular_searches': [], 'total': 0, 'error': str(e)}

    # ==================== 搜索历史管理 ====================

    def save_search_history(self, session_id: str, keyword: str, result_count: int = 0) -> bool:
        """
        保存搜索历史

        Args:
            session_id: 会话ID
            keyword: 搜索关键词
            result_count: 结果数量

        Returns:
            是否保存成功
        """
        try:
            keyword = self._sanitize_keyword(keyword)
            if not keyword:
                return False

            # 使用 merge 避免重复
            history = SearchHistory(session_id=session_id, keyword=keyword, result_count=result_count)
            db.session.merge(history)
            db.session.commit()

            logger.debug(f'搜索历史已保存: {keyword}')
            return True

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'保存搜索历史失败: {e}')
            db.session.rollback()
            return False

    def get_search_history(self, session_id: str, limit: int = 10) -> list[str]:
        """
        获取用户的搜索历史

        Args:
            session_id: 会话ID
            limit: 返回数量

        Returns:
            搜索历史关键词列表
        """
        try:
            limit = min(max(1, limit), 50)

            history = (
                SearchHistory.query.filter_by(session_id=session_id)
                .order_by(SearchHistory.created_at.desc())
                .limit(limit)
                .all()
            )

            # 去重并返回
            seen = set()
            keywords = []
            for h in history:
                if h.keyword.lower() not in seen:
                    seen.add(h.keyword.lower())
                    keywords.append(h.keyword)

            return keywords

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'获取搜索历史失败: {e}')
            return []

    def clear_search_history(self, session_id: str) -> bool:
        """
        清除用户的搜索历史

        Args:
            session_id: 会话ID

        Returns:
            是否清除成功
        """
        try:
            SearchHistory.query.filter_by(session_id=session_id).delete()
            db.session.commit()
            return True

        except Exception as e:
            log_error(ErrorCategory.API_CALL, f'清除搜索历史失败: {e}')
            db.session.rollback()
            return False
