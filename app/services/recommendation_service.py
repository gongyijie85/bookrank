"""
AI 推荐服务

提供基于用户行为的智能图书推荐功能:
1. 基于用户浏览历史的推荐
2. 基于用户收藏的推荐
3. 基于奖项相似度的推荐
"""

import logging
from typing import Any
from collections import Counter

from sqlalchemy import func

from ..models.schemas import (
    UserPreference, UserCategory, UserViewedBook,
    AwardBook, BookMetadata, Book, db
)

logger = logging.getLogger(__name__)


class RecommendationService:
    """AI 图书推荐服务"""

    # 推荐结果缓存时间（秒）
    CACHE_TTL = 300

    def __init__(self, categories: dict | None = None):
        """
        初始化推荐服务

        Args:
            categories: 分类字典，key为分类ID，value为分类名称
        """
        self._categories = categories or {}

    def get_personalized_recommendations(
        self,
        session_id: str,
        limit: int = 10
    ) -> dict[str, Any]:
        """
        获取个性化推荐

        基于用户浏览历史和收藏偏好，推荐相关图书

        Args:
            session_id: 会话ID
            limit: 返回结果数量限制

        Returns:
            包含推荐结果和推荐理由的字典
        """
        try:
            # 获取用户浏览历史
            viewed_books = self._get_viewed_books(session_id)
            if not viewed_books:
                # 无浏览历史，返回热门推荐
                return self._get_popular_recommendations(limit)

            # 分析用户兴趣偏好
            interests = self._analyze_user_interests(session_id, viewed_books)

            # 基于兴趣推荐
            recommendations = self._recommend_by_interests(interests, limit)

            # 如果推荐结果不足，补充热门图书
            if len(recommendations) < limit:
                popular = self._get_popular_recommendations(limit - len(recommendations))
                recommendations.extend(popular)

            return {
                'recommendations': recommendations,
                'reason': self._generate_recommendation_reason(interests),
                'based_on': 'personalized'
            }

        except Exception as e:
            logger.error(f"获取个性化推荐失败: {e}", exc_info=True)
            return self._get_popular_recommendations(limit)

    def _get_viewed_books(self, session_id: str) -> list[UserViewedBook]:
        """获取用户浏览的图书"""
        return UserViewedBook.query.filter_by(
            session_id=session_id
        ).order_by(
            UserViewedBook.viewed_at.desc()
        ).limit(20).all()

    def _analyze_user_interests(
        self,
        session_id: str,
        viewed_books: list[UserViewedBook]
    ) -> dict[str, Any]:
        """
        分析用户兴趣

        分析用户浏览的图书，提取关键词、作者、分类等特征

        Args:
            session_id: 会话ID
            viewed_books: 用户浏览的图书列表

        Returns:
            用户兴趣特征字典
        """
        interests = {
            'keywords': [],
            'authors': [],
            'publishers': [],
            'categories': []
        }

        # 获取用户关注的分类
        user_categories = UserCategory.query.filter_by(
            session_id=session_id
        ).all()
        interests['categories'] = [uc.category_id for uc in user_categories]

        # 从浏览历史中提取特征
        isbns = [vb.isbn for vb in viewed_books]

        # 从 BookMetadata 和 AwardBook 中获取更多信息
        metadata_books = BookMetadata.query.filter(
            BookMetadata.isbn.in_(isbns)
        ).all() if isbns else []

        award_books = AwardBook.query.filter(
            AwardBook.isbn13.in_(isbns)
        ).all() if isbns else []

        # 提取关键词（从标题和描述中）
        for book in metadata_books:
            if book.title:
                # 提取书名中的关键词
                words = self._extract_keywords(book.title)
                interests['keywords'].extend(words)
            if book.author:
                interests['authors'].append(book.author)

        for book in award_books:
            if book.title:
                words = self._extract_keywords(book.title)
                interests['keywords'].extend(words)
            if book.author:
                interests['authors'].append(book.author)

        # 统计最常见的关键词和作者
        interests['keywords'] = [
            k for k, v in Counter(interests['keywords']).most_common(5)
        ]
        interests['authors'] = [
            a for a, v in Counter(interests['authors']).most_common(3)
        ]

        return interests

    def _extract_keywords(self, text: str) -> list[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本

        Returns:
            关键词列表
        """
        if not text:
            return []

        # 简单分词：按空格和标点分割
        import re
        words = re.findall(r'\b\w{2,}\b', text.lower())

        # 过滤停用词
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
                      'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        words = [w for w in words if w not in stop_words and len(w) > 2]

        return words

    def _recommend_by_interests(
        self,
        interests: dict[str, Any],
        limit: int
    ) -> list[dict]:
        """
        基于用户兴趣推荐图书

        Args:
            interests: 用户兴趣特征
            limit: 返回数量限制

        Returns:
            推荐图书列表
        """
        recommendations = []

        # 从获奖图书中推荐
        if interests.get('authors') or interests.get('keywords'):
            query = AwardBook.query.filter_by(is_displayable=True)

            # 构建搜索条件
            conditions = []
            for author in interests.get('authors', [])[:2]:
                conditions.append(AwardBook.author.ilike(f'%{author}%'))

            for keyword in interests.get('keywords', [])[:3]:
                conditions.append(AwardBook.title.ilike(f'%{keyword}%'))

            if conditions:
                query = query.filter(db.or_(*conditions))

            # 按年份和排名排序
            books = query.order_by(
                AwardBook.year.desc(),
                AwardBook.rank.asc()
            ).limit(limit).all()

            # 去重并添加到推荐列表
            seen_isbns = set()
            for book in books:
                if book.isbn13 and book.isbn13 not in seen_isbns:
                    seen_isbns.add(book.isbn13)
                    recommendations.append(self._format_award_book(book))

        return recommendations

    def _format_award_book(self, book: AwardBook) -> dict:
        """格式化获奖图书为推荐格式"""
        return {
            'id': book.id,
            'type': 'award_book',
            'title': book.title,
            'title_zh': book.title_zh,
            'author': book.author,
            'publisher': book.publisher,
            'year': book.year,
            'category': book.category,
            'rank': book.rank,
            'cover_url': book.cover_original_url,
            'isbn13': book.isbn13,
            'reason': f"{book.year}年{book.category or '获奖作品'}"
        }

    def _generate_recommendation_reason(self, interests: dict[str, Any]) -> str:
        """生成推荐理由"""
        reasons = []

        if interests.get('authors'):
            authors = ', '.join(interests['authors'][:2])
            reasons.append(f"因为您关注了作者 {authors}")

        if interests.get('categories'):
            cat_names = [
                self._categories.get(c, c) for c in interests['categories'][:2]
            ]
            if cat_names:
                reasons.append(f"基于您对 {', '.join(cat_names)} 类图书的兴趣")

        if not reasons:
            return "根据热门获奖图书推荐"

        return '，'.join(reasons) + '，为您推荐以下图书'

    def _get_popular_recommendations(self, limit: int) -> dict[str, Any]:
        """
        获取热门推荐（无个性化数据时的降级方案）

        Args:
            limit: 返回数量限制

        Returns:
            推荐结果字典
        """
        # 获取最近几年的热门获奖图书
        books = AwardBook.query.filter_by(
            is_displayable=True
        ).order_by(
            AwardBook.year.desc(),
            AwardBook.rank.asc()
        ).limit(limit).all()

        recommendations = [self._format_award_book(book) for book in books]

        return {
            'recommendations': recommendations,
            'reason': '热门获奖图书推荐',
            'based_on': 'popular'
        }

    # ==================== 基于奖项相似度的推荐 ====================

    def get_similarity_recommendations(
        self,
        book_id: int | None = None,
        isbn: str | None = None,
        award_id: int | None = None,
        category: str | None = None,
        limit: int = 10
    ) -> dict[str, Any]:
        """
        基于奖项相似度推荐

        根据给定的图书或奖项信息，推荐相似的获奖图书

        Args:
            book_id: 基准图书ID
            isbn: 基准图书ISBN
            award_id: 奖项ID
            category: 图书分类
            limit: 返回数量限制

        Returns:
            推荐结果字典
        """
        try:
            # 确定基准图书
            target_book = None
            if book_id:
                target_book = AwardBook.query.get(book_id)
            elif isbn:
                target_book = AwardBook.query.filter_by(isbn13=isbn).first()

            if target_book:
                return self._recommend_similar_books(target_book, limit)

            # 基于奖项推荐
            if award_id:
                return self._recommend_by_award(award_id, category, limit)

            # 基于分类推荐
            if category:
                return self._recommend_by_category(category, limit)

            # 默认返回热门推荐
            return self._get_popular_recommendations(limit)

        except Exception as e:
            logger.error(f"获取相似推荐失败: {e}", exc_info=True)
            return self._get_popular_recommendations(limit)

    def _recommend_similar_books(
        self,
        target_book: AwardBook,
        limit: int
    ) -> dict[str, Any]:
        """推荐与目标图书相似的书籍"""
        # 构建相似度查询条件
        conditions = []

        # 同一奖项
        conditions.append(AwardBook.award_id == target_book.award_id)

        # 同一分类
        if target_book.category:
            conditions.append(AwardBook.category == target_book.category)

        # 同一时期（±2年）
        if target_book.year:
            conditions.append(
                AwardBook.year.between(target_book.year - 2, target_book.year + 2)
            )

        # 排除目标图书本身
        query = AwardBook.query.filter(
            AwardBook.id != target_book.id,
            AwardBook.is_displayable == True,
            db.or_(*conditions)
        )

        books = query.order_by(
            AwardBook.year.desc(),
            AwardBook.rank.asc()
        ).limit(limit).all()

        recommendations = [self._format_award_book(book) for book in books]

        return {
            'recommendations': recommendations,
            'reason': f'与《{target_book.title}》相似的获奖图书',
            'based_on': 'similarity',
            'reference_book': {
                'id': target_book.id,
                'title': target_book.title,
                'author': target_book.author
            }
        }

    def _recommend_by_award(
        self,
        award_id: int,
        category: str | None,
        limit: int
    ) -> dict[str, Any]:
        """基于特定奖项推荐"""
        query = AwardBook.query.filter_by(
            award_id=award_id,
            is_displayable=True
        )

        if category:
            query = query.filter_by(category=category)

        books = query.order_by(
            AwardBook.year.desc(),
            AwardBook.rank.asc()
        ).limit(limit).all()

        recommendations = [self._format_award_book(book) for book in books]

        return {
            'recommendations': recommendations,
            'reason': '同奖项其他年份获奖图书',
            'based_on': 'award_similarity'
        }

    def _recommend_by_category(
        self,
        category: str,
        limit: int
    ) -> dict[str, Any]:
        """基于分类推荐"""
        books = AwardBook.query.filter_by(
            category=category,
            is_displayable=True
        ).order_by(
            AwardBook.year.desc(),
            AwardBook.rank.asc()
        ).limit(limit).all()

        recommendations = [self._format_award_book(book) for book in books]

        return {
            'recommendations': recommendations,
            'reason': f'{category}分类的获奖图书',
            'based_on': 'category'
        }

    # ==================== 智能推荐（综合） ====================

    def get_smart_recommendations(
        self,
        session_id: str | None = None,
        limit: int = 10
    ) -> dict[str, Any]:
        """
        获取智能推荐（综合多种策略）

        优先使用个性化推荐，如果数据不足则使用热门推荐

        Args:
            session_id: 会话ID（可选，用于个性化推荐）
            limit: 返回数量限制

        Returns:
            智能推荐结果
        """
        # 限制返回数量范围
        limit = min(max(1, limit), 50)

        # 尝试个性化推荐
        if session_id:
            personalized = self.get_personalized_recommendations(
                session_id, limit
            )
            if personalized.get('recommendations'):
                personalized['strategy'] = 'hybrid'
                return personalized

        # 降级到热门推荐
        popular = self._get_popular_recommendations(limit)
        popular['strategy'] = 'popular_fallback'
        return popular
