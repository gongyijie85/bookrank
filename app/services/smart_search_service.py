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
from collections import Counter

from sqlalchemy import func, or_, and_

from ..models.schemas import AwardBook, BookMetadata, SearchHistory, db

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
        offset: int = 0
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
            # 验证和清理关键词
            keyword = self._sanitize_keyword(keyword)
            if not keyword:
                return self._empty_search_result()

            # 限制搜索范围
            limit = min(max(1, limit), 100)
            offset = max(0, offset)

            # 构建查询
            query = AwardBook.query.filter(AwardBook.is_displayable == True)

            # 应用搜索条件
            query = self._apply_search_conditions(query, keyword, search_type)

            # 应用筛选条件
            if year:
                query = query.filter(AwardBook.year == year)
            if award_id:
                query = query.filter(AwardBook.award_id == award_id)

            # 获取总数
            total = query.count()

            # 获取分页结果
            books = query.order_by(
                AwardBook.year.desc(),
                AwardBook.rank.asc()
            ).offset(offset).limit(limit).all()

            # 格式化结果
            results = [self._format_book(book) for book in books]

            # 生成搜索建议（用于相关搜索）
            suggestions = self._generate_suggestions(keyword, search_type)

            return {
                'results': results,
                'total': total,
                'keyword': keyword,
                'search_type': search_type,
                'suggestions': suggestions[:5],
                'pagination': {
                    'limit': limit,
                    'offset': offset,
                    'has_more': offset + limit < total
                }
            }

        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
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

    def _apply_search_conditions(
        self,
        query,
        keyword: str,
        search_type: str
    ):
        """
        应用搜索条件到查询

        Args:
            query:对象
            keyword: 搜索关键词 SQLAlchemy 查询
            search_type: 搜索类型

        Returns:
            过滤后的查询对象
        """
        # 转义特殊SQL字符
        escaped_keyword = keyword.replace('%', r'\%').replace('_', r'\_')

        # 构建搜索条件
        conditions = []

        if search_type == 'all' or search_type == 'title':
            # 书名搜索 - 支持模糊匹配和分词匹配
            conditions.append(
                AwardBook.title.ilike(f'%{escaped_keyword}%')
            )
            #  also search in Chinese title
            conditions.append(
                AwardBook.title_zh.ilike(f'%{escaped_keyword}%')
            )

        if search_type == 'all' or search_type == 'author':
            # 作者搜索
            conditions.append(
                AwardBook.author.ilike(f'%{escaped_keyword}%')
            )

        if search_type == 'all' or search_type == 'publisher':
            # 出版社搜索
            conditions.append(
                AwardBook.publisher.ilike(f'%{escaped_keyword}%')
            )

        if not conditions:
            return query

        return query.filter(or_(*conditions))

    def _format_book(self, book: AwardBook) -> dict:
        """格式化图书为搜索结果格式"""
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
            'award': {
                'id': book.award_id,
                'name': book.award.name if book.award else None
            } if book.award else None
        }

    def _empty_search_result(self) -> dict:
        """返回空搜索结果"""
        return {
            'results': [],
            'total': 0,
            'keyword': '',
            'search_type': 'all',
            'suggestions': [],
            'pagination': {
                'limit': 20,
                'offset': 0,
                'has_more': False
            }
        }

    def _generate_suggestions(
        self,
        keyword: str,
        search_type: str
    ) -> list[str]:
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
            recent_searches = SearchHistory.query.filter(
                SearchHistory.keyword.ilike(f'{keyword}%')
            ).order_by(
                SearchHistory.created_at.desc()
            ).limit(5).all()

            # 去重并添加建议
            seen = set()
            for search in recent_searches:
                if search.keyword.lower() not in seen:
                    seen.add(search.keyword.lower())
                    suggestions.append(search.keyword)

            # 如果建议不足，从热门搜索补充
            if len(suggestions) < 5:
                popular = SearchHistory.query.with_entities(
                    SearchHistory.keyword,
                    func.count(SearchHistory.id).label('count')
                ).group_by(
                    SearchHistory.keyword
                ).order_by(
                    func.count(SearchHistory.id).desc()
                ).filter(
                    SearchHistory.keyword.ilike(f'{keyword}%')
                ).limit(5).all()

                for kw, count in popular:
                    if kw.lower() not in seen:
                        seen.add(kw.lower())
                        suggestions.append(kw)

        except Exception as e:
            logger.debug(f"生成搜索建议失败: {e}")

        return suggestions[:5]

    # ==================== 搜索建议API ====================

    def get_suggestions(
        self,
        prefix: str,
        limit: int = 10
    ) -> dict[str, Any]:
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
                return {
                    'suggestions': [],
                    'prefix': prefix
                }

            # 限制返回数量
            limit = min(max(1, limit), 20)

            suggestions = []

            # 1. 从书名中获取建议
            title_suggestions = AwardBook.query.filter(
                AwardBook.is_displayable == True,
                or_(
                    AwardBook.title.ilike(f'{prefix}%'),
                    AwardBook.title_zh.ilike(f'{prefix}%')
                )
            ).with_entities(
                AwardBook.title
            ).distinct().limit(limit).all()

            for (title,) in title_suggestions:
                suggestions.append({
                    'text': title,
                    'type': 'title'
                })

            # 2. 从作者中获取建议
            if len(suggestions) < limit:
                author_suggestions = AwardBook.query.filter(
                    AwardBook.is_displayable == True,
                    AwardBook.author.ilike(f'{prefix}%')
                ).with_entities(
                    AwardBook.author
                ).distinct().limit(limit).all()

                for (author,) in author_suggestions:
                    if len(suggestions) >= limit:
                        break
                    suggestions.append({
                        'text': author,
                        'type': 'author'
                    })

            # 3. 从出版社中获取建议
            if len(suggestions) < limit:
                publisher_suggestions = AwardBook.query.filter(
                    AwardBook.is_displayable == True,
                    AwardBook.publisher.ilike(f'{prefix}%')
                ).with_entities(
                    AwardBook.publisher
                ).distinct().limit(limit).all()

                for (publisher,) in publisher_suggestions:
                    if len(suggestions) >= limit:
                        break
                    suggestions.append({
                        'text': publisher,
                        'type': 'publisher'
                    })

            # 去重（基于文本）
            seen = set()
            unique_suggestions = []
            for s in suggestions:
                text_lower = s['text'].lower()
                if text_lower not in seen:
                    seen.add(text_lower)
                    unique_suggestions.append(s)

            return {
                'suggestions': unique_suggestions[:limit],
                'prefix': prefix
            }

        except Exception as e:
            logger.error(f"获取搜索建议失败: {e}", exc_info=True)
            return {
                'suggestions': [],
                'prefix': prefix,
                'error': str(e)
            }

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
            popular = SearchHistory.query.with_entities(
                SearchHistory.keyword,
                func.count(SearchHistory.id).label('search_count'),
                func.max(SearchHistory.created_at).label('last_search')
            ).group_by(
                SearchHistory.keyword
            ).order_by(
                func.count(SearchHistory.id).desc(),
                func.max(SearchHistory.created_at).desc()
            ).limit(limit).all()

            searches = [
                {
                    'keyword': keyword,
                    'count': count,
                    'last_searched': last_search.isoformat() if last_search else None
                }
                for keyword, count, last_search in popular
            ]

            return {
                'popular_searches': searches,
                'total': len(searches)
            }

        except Exception as e:
            logger.error(f"获取热门搜索失败: {e}", exc_info=True)
            return {
                'popular_searches': [],
                'total': 0,
                'error': str(e)
            }

    # ==================== 搜索历史管理 ====================

    def save_search_history(
        self,
        session_id: str,
        keyword: str,
        result_count: int = 0
    ) -> bool:
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
            history = SearchHistory(
                session_id=session_id,
                keyword=keyword,
                result_count=result_count
            )
            db.session.merge(history)
            db.session.commit()

            logger.debug(f"搜索历史已保存: {keyword}")
            return True

        except Exception as e:
            logger.error(f"保存搜索历史失败: {e}")
            db.session.rollback()
            return False

    def get_search_history(
        self,
        session_id: str,
        limit: int = 10
    ) -> list[str]:
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

            history = SearchHistory.query.filter_by(
                session_id=session_id
            ).order_by(
                SearchHistory.created_at.desc()
            ).limit(limit).all()

            # 去重并返回
            seen = set()
            keywords = []
            for h in history:
                if h.keyword.lower() not in seen:
                    seen.add(h.keyword.lower())
                    keywords.append(h.keyword)

            return keywords

        except Exception as e:
            logger.error(f"获取搜索历史失败: {e}")
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
            logger.error(f"清除搜索历史失败: {e}")
            db.session.rollback()
            return False
