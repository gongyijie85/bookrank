"""
新书速递服务

提供爬虫管理、数据同步、翻译等核心功能：
- 管理多个出版社爬虫
- 同步新书数据到数据库
- 自动翻译书名和简介
- 缓存封面图片
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..models.database import db
from ..models.new_book import NewBook, Publisher
from .cache_service import CacheService
from .translation_service import TranslationService

logger = logging.getLogger(__name__)


# 爬虫类映射
CRAWLER_MAP: dict[str, type] = {}


def _init_crawler_map():
    """初始化爬虫映射（延迟导入避免循环依赖）"""
    global CRAWLER_MAP
    if CRAWLER_MAP:
        return

    # API数据源爬虫
    try:
        from .publisher_crawler.open_library import OpenLibraryCrawler
        CRAWLER_MAP['OpenLibraryCrawler'] = OpenLibraryCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 OpenLibraryCrawler")

    try:
        from .publisher_crawler.google_books import GoogleBooksCrawler
        CRAWLER_MAP['GoogleBooksCrawler'] = GoogleBooksCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 GoogleBooksCrawler")

    # 出版社爬虫
    try:
        from .publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler
        CRAWLER_MAP['PenguinRandomHouseCrawler'] = PenguinRandomHouseCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 PenguinRandomHouseCrawler")

    try:
        from .publisher_crawler.simon_schuster import SimonSchusterCrawler
        CRAWLER_MAP['SimonSchusterCrawler'] = SimonSchusterCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 SimonSchusterCrawler")

    try:
        from .publisher_crawler.hachette import HachetteCrawler
        CRAWLER_MAP['HachetteCrawler'] = HachetteCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 HachetteCrawler")

    try:
        from .publisher_crawler.harpercollins import HarperCollinsCrawler
        CRAWLER_MAP['HarperCollinsCrawler'] = HarperCollinsCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 HarperCollinsCrawler")

    try:
        from .publisher_crawler.macmillan import MacmillanCrawler
        CRAWLER_MAP['MacmillanCrawler'] = MacmillanCrawler
    except ImportError:
        logger.warning("⚠️ 无法导入 MacmillanCrawler")


class NewBookService:
    """
    新书速递服务

    管理出版社爬虫、数据同步和翻译。
    """

    # 默认出版社配置
    DEFAULT_PUBLISHERS = [
        {
            'name': 'Google Books',
            'name_en': 'Google Books',
            'website': 'https://books.google.com',
            'crawler_class': 'GoogleBooksCrawler',
        },
        {
            'name': 'Open Library',
            'name_en': 'Open Library',
            'website': 'https://openlibrary.org',
            'crawler_class': 'OpenLibraryCrawler',
        },
        {
            'name': '企鹅兰登',
            'name_en': 'Penguin Random House',
            'website': 'https://www.penguinrandomhouse.com',
            'crawler_class': 'PenguinRandomHouseCrawler',
        },
        {
            'name': '西蒙舒斯特',
            'name_en': 'Simon & Schuster',
            'website': 'https://www.simonandschuster.com',
            'crawler_class': 'SimonSchusterCrawler',
        },
        {
            'name': '阿歇特',
            'name_en': 'Hachette',
            'website': 'https://www.hachettebookgroup.com',
            'crawler_class': 'HachetteCrawler',
        },
        {
            'name': '哈珀柯林斯',
            'name_en': 'HarperCollins',
            'website': 'https://www.harpercollins.com',
            'crawler_class': 'HarperCollinsCrawler',
        },
        {
            'name': '麦克米伦',
            'name_en': 'Macmillan',
            'website': 'https://us.macmillan.com',
            'crawler_class': 'MacmillanCrawler',
        },
    ]

    def __init__(
        self,
        cache_service: CacheService | None = None,
        translation_service: TranslationService | None = None
    ):
        """
        初始化服务

        Args:
            cache_service: 缓存服务（可选）
            translation_service: 翻译服务（可选）
        """
        self._cache = cache_service
        self._translator = translation_service
        _init_crawler_map()

    # ==================== 出版社管理 ====================

    def init_publishers(self) -> int:
        """
        初始化默认出版社数据

        Returns:
            创建的出版社数量
        """
        count = 0

        for pub_data in self.DEFAULT_PUBLISHERS:
            # 检查是否已存在
            existing = Publisher.query.filter_by(name_en=pub_data['name_en']).first()
            if existing:
                logger.info(f"📖 出版社已存在: {pub_data['name_en']}")
                continue

            publisher = Publisher(
                name=pub_data['name'],
                name_en=pub_data['name_en'],
                website=pub_data['website'],
                crawler_class=pub_data['crawler_class'],
                is_active=True,
            )

            db.session.add(publisher)
            count += 1
            logger.info(f"✅ 创建出版社: {pub_data['name_en']}")

        if count > 0:
            db.session.commit()
            logger.info(f"✅ 成功创建 {count} 个出版社")
        else:
            logger.info("📖 所有出版社已存在，无需创建")

        return count

    def get_publishers(self, active_only: bool = True) -> list[Publisher]:
        """
        获取出版社列表

        Args:
            active_only: 是否只返回启用的出版社

        Returns:
            出版社列表
        """
        query = Publisher.query

        if active_only:
            query = query.filter_by(is_active=True)

        return query.order_by(Publisher.name_en).all()

    def get_publisher(self, publisher_id: int) -> Publisher | None:
        """
        获取单个出版社

        Args:
            publisher_id: 出版社ID

        Returns:
            出版社对象或None
        """
        return Publisher.query.get(publisher_id)

    def update_publisher_status(self, publisher_id: int, is_active: bool) -> bool:
        """
        更新出版社状态

        Args:
            publisher_id: 出版社ID
            is_active: 是否启用

        Returns:
            是否成功
        """
        publisher = self.get_publisher(publisher_id)
        if not publisher:
            return False

        publisher.is_active = is_active
        db.session.commit()
        logger.info(f"✅ 更新出版社状态: {publisher.name_en} -> {'启用' if is_active else '禁用'}")
        return True

    # ==================== 爬虫管理 ====================

    def get_crawler(self, crawler_class: str):
        """
        获取爬虫实例

        Args:
            crawler_class: 爬虫类名

        Returns:
            爬虫实例或None
        """
        crawler_cls = CRAWLER_MAP.get(crawler_class)
        if not crawler_cls:
            logger.error(f"❌ 未找到爬虫类: {crawler_class}")
            return None

        # Google Books 爬虫需要 API key
        if crawler_class == 'GoogleBooksCrawler':
            from flask import current_app
            api_key = current_app.config.get('GOOGLE_API_KEY') if current_app else None
            if api_key:
                from .publisher_crawler.base_crawler import CrawlerConfig
                config = CrawlerConfig(api_key=api_key)
                return crawler_cls(config)

        return crawler_cls()

    def sync_publisher_books(
        self,
        publisher_id: int,
        category: str | None = None,
        max_books: int = 50,
        translate: bool = True
    ) -> dict[str, Any]:
        """
        同步指定出版社的新书数据

        Args:
            publisher_id: 出版社ID
            category: 分类筛选
            max_books: 最大同步数量
            translate: 是否翻译

        Returns:
            同步结果统计
        """
        publisher = self.get_publisher(publisher_id)
        if not publisher:
            return {'success': False, 'error': '出版社不存在'}

        if not publisher.is_active:
            return {'success': False, 'error': '出版社已禁用'}

        crawler = self.get_crawler(publisher.crawler_class)
        if not crawler:
            return {'success': False, 'error': '爬虫不可用'}

        result = {
            'success': True,
            'publisher': publisher.name_en,
            'total': 0,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }

        try:
            logger.info(f"🔍 开始同步 {publisher.name_en} 新书...")

            with crawler:
                for book_info in crawler.get_new_books(category=category, max_books=max_books):
                    result['total'] += 1

                    try:
                        # 保存或更新书籍
                        save_result = self._save_book(publisher, book_info, translate)

                        if save_result == 'added':
                            result['added'] += 1
                        elif save_result == 'updated':
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1

                    except Exception as e:
                        logger.error(f"❌ 保存书籍失败: {book_info.title} - {e}")
                        result['errors'] += 1

            # 更新同步时间
            publisher.last_sync_at = datetime.now(timezone.utc)
            publisher.sync_count += 1
            db.session.commit()

            logger.info(
                f"✅ 同步完成: {publisher.name_en} - "
                f"总计 {result['total']}, 新增 {result['added']}, "
                f"更新 {result['updated']}, 跳过 {result['skipped']}"
            )

        except Exception as e:
            logger.error(f"❌ 同步失败: {e}")
            result['success'] = False
            result['error'] = str(e)

        return result

    def sync_all_publishers(
        self,
        category: str | None = None,
        max_books_per_publisher: int = 30,
        translate: bool = True
    ) -> list[dict[str, Any]]:
        """
        同步所有启用出版社的新书数据

        Args:
            category: 分类筛选
            max_books_per_publisher: 每个出版社最大同步数量
            translate: 是否翻译

        Returns:
            各出版社同步结果列表
        """
        results = []
        publishers = self.get_publishers(active_only=True)

        logger.info(f"🔍 开始同步 {len(publishers)} 个出版社...")

        for publisher in publishers:
            result = self.sync_publisher_books(
                publisher.id,
                category=category,
                max_books=max_books_per_publisher,
                translate=translate
            )
            results.append(result)

        # 汇总统计
        total_added = sum(r.get('added', 0) for r in results)
        total_updated = sum(r.get('updated', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)

        logger.info(
            f"✅ 全部同步完成: 新增 {total_added}, 更新 {total_updated}, 错误 {total_errors}"
        )

        return results

    # ==================== 书籍管理 ====================

    def _save_book(
        self,
        publisher: Publisher,
        book_info,
        translate: bool = True
    ) -> str:
        """
        保存书籍到数据库

        Args:
            publisher: 出版社对象
            book_info: 书籍信息
            translate: 是否翻译

        Returns:
            操作结果: 'added', 'updated', 'skipped'
        """
        # 检查是否已存在（通过ISBN或标题+作者）
        existing = None

        if book_info.isbn13:
            existing = NewBook.query.filter_by(
                publisher_id=publisher.id,
                isbn13=book_info.isbn13
            ).first()

        if not existing and book_info.isbn10:
            existing = NewBook.query.filter_by(
                publisher_id=publisher.id,
                isbn10=book_info.isbn10
            ).first()

        if not existing:
            # 通过标题和作者匹配
            existing = NewBook.query.filter_by(
                publisher_id=publisher.id,
                title=book_info.title,
                author=book_info.author
            ).first()

        if existing:
            # 更新现有记录
            updated = self._update_book_fields(existing, book_info)
            if updated:
                return 'updated'
            return 'skipped'

        # 创建新记录
        new_book = NewBook(
            publisher_id=publisher.id,
            title=book_info.title,
            author=book_info.author,
            isbn13=book_info.isbn13,
            isbn10=book_info.isbn10,
            description=book_info.description,
            cover_url=book_info.cover_url,
            category=book_info.category,
            publication_date=book_info.publication_date,
            price=book_info.price,
            page_count=book_info.page_count,
            language=book_info.language,
            source_url=book_info.source_url,
        )

        # 设置购买链接
        if book_info.buy_links:
            new_book.set_buy_links(book_info.buy_links)

        # 翻译
        if translate and self._translator:
            self._translate_book(new_book)

        db.session.add(new_book)
        db.session.commit()

        return 'added'

    def _update_book_fields(self, book: NewBook, book_info) -> bool:
        """
        更新书籍字段

        Args:
            book: 书籍对象
            book_info: 新的书籍信息

        Returns:
            是否有更新
        """
        updated = False

        # 更新可能变化的字段
        if book_info.description and book_info.description != book.description:
            book.description = book_info.description
            updated = True

        if book_info.cover_url and book_info.cover_url != book.cover_url:
            book.cover_url = book_info.cover_url
            updated = True

        if book_info.price and book_info.price != book.price:
            book.price = book_info.price
            updated = True

        if book_info.buy_links:
            book.set_buy_links(book_info.buy_links)
            updated = True

        if updated:
            book.updated_at = datetime.now(timezone.utc)
            db.session.commit()

        return updated

    def _translate_book(self, book: NewBook) -> None:
        """
        翻译书籍信息

        Args:
            book: 书籍对象
        """
        if not self._translator:
            return

        try:
            # 翻译书名
            if book.title and not book.title_zh:
                book.title_zh = self._translator.translate(book.title, 'en', 'zh')

            # 翻译简介
            if book.description and not book.description_zh:
                book.description_zh = self._translator.translate(
                    book.description[:1000],  # 限制长度
                    'en',
                    'zh'
                )

        except Exception as e:
            logger.warning(f"⚠️ 翻译失败: {book.title} - {e}")

    # ==================== 查询接口 ====================

    def get_new_books(
        self,
        publisher_id: int | None = None,
        category: str | None = None,
        days: int = 30,
        page: int = 1,
        per_page: int = 20
    ) -> tuple[list[NewBook], int]:
        """
        获取新书列表

        Args:
            publisher_id: 出版社ID筛选
            category: 分类筛选
            days: 最近天数
            page: 页码
            per_page: 每页数量

        Returns:
            (书籍列表, 总数)
        """
        from datetime import timedelta

        query = NewBook.query.filter(NewBook.is_displayable == True)

        # 时间筛选
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(NewBook.created_at >= cutoff_date)

        # 出版社筛选
        if publisher_id:
            query = query.filter(NewBook.publisher_id == publisher_id)

        # 分类筛选
        if category:
            query = query.filter(NewBook.category == category)

        # 排序
        query = query.order_by(NewBook.publication_date.desc().nullslast(), NewBook.created_at.desc())

        # 分页
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total

    def get_book(self, book_id: int) -> NewBook | None:
        """
        获取单本书籍详情

        Args:
            book_id: 书籍ID

        Returns:
            书籍对象或None
        """
        return NewBook.query.get(book_id)

    def search_books(
        self,
        keyword: str,
        page: int = 1,
        per_page: int = 20
    ) -> tuple[list[NewBook], int]:
        """
        搜索书籍

        Args:
            keyword: 搜索关键词
            page: 页码
            per_page: 每页数量

        Returns:
            (书籍列表, 总数)
        """
        search_pattern = f"%{keyword}%"

        query = NewBook.query.filter(
            db.or_(
                NewBook.title.ilike(search_pattern),
                NewBook.title_zh.ilike(search_pattern),
                NewBook.author.ilike(search_pattern),
                NewBook.isbn13 == keyword,
                NewBook.isbn10 == keyword,
            )
        ).filter(NewBook.is_displayable == True)

        query = query.order_by(NewBook.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total

    def get_categories(self) -> list[dict[str, str]]:
        """
        获取所有分类

        Returns:
            分类列表
        """
        from sqlalchemy import func

        results = db.session.query(
            NewBook.category,
            func.count(NewBook.id).label('count')
        ).filter(
            NewBook.category.isnot(None),
            NewBook.is_displayable == True
        ).group_by(
            NewBook.category
        ).order_by(
            func.count(NewBook.id).desc()
        ).all()

        return [
            {'name': r.category, 'count': r.count}
            for r in results
        ]

    # ==================== 统计接口 ====================

    def get_statistics(self) -> dict[str, Any]:
        """
        获取统计数据

        Returns:
            统计信息字典
        """
        from sqlalchemy import func

        # 总体统计
        total_books = NewBook.query.count()
        total_publishers = Publisher.query.count()
        active_publishers = Publisher.query.filter_by(is_active=True).count()

        # 最近7天新增
        from datetime import timedelta
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_books = NewBook.query.filter(NewBook.created_at >= week_ago).count()

        # 分类统计
        category_stats = db.session.query(
            NewBook.category,
            func.count(NewBook.id).label('count')
        ).filter(
            NewBook.category.isnot(None)
        ).group_by(
            NewBook.category
        ).order_by(
            func.count(NewBook.id).desc()
        ).limit(10).all()

        return {
            'total_books': total_books,
            'total_publishers': total_publishers,
            'active_publishers': active_publishers,
            'recent_books_7d': recent_books,
            'top_categories': [
                {'category': c.category, 'count': c.count}
                for c in category_stats
            ],
        }
