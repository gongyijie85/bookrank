"""
新书速递服务

提供爬虫管理、数据同步、翻译等核心功能：
- 管理多个出版社爬虫
- 同步新书数据到数据库
- 自动翻译书名和简介
- 缓存封面图片
"""

import gc
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

from ..models.database import db
from ..models.new_book import NewBook, Publisher
from .book_language_pack import BookLanguagePack
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class NewBookService:
    """
    新书速递服务

    管理出版社爬虫、数据同步和翻译。
    """

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
            'crawler_class': 'SimonSchusterGoogleCrawler',
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

    STATIC_DATA_FILES = {
        'google_books_books.json': 'Google Books',
        'open_library_books.json': 'Open Library',
        'penguin_random_house_books.json': 'Penguin Random House',
        'simon_schuster_books.json': 'Simon & Schuster',
        'hachette_books.json': 'Hachette',
        'harpercollins_books.json': 'HarperCollins',
        'macmillan_books.json': 'Macmillan',
    }

    _instance: 'NewBookService | None' = None

    def __new__(cls, *args: Any, **kwargs: Any) -> 'NewBookService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(
        self,
        cache_service: CacheService | None = None,
        translation_service: Any | None = None,
        language_pack_path: str | Path | None = None,
    ):
        if hasattr(self, '_initialized') and self._initialized:
            if cache_service and not self._cache:
                self._cache = cache_service
            if translation_service and not self._translator:
                self._translator = translation_service
            if language_pack_path:
                self._language_pack = BookLanguagePack(language_pack_path)
            elif not hasattr(self, '_language_pack'):
                self._language_pack = BookLanguagePack(self._resolve_language_pack_path())
            elif getattr(self._language_pack, '_pack_path', None) is None:
                resolved_pack_path = self._resolve_language_pack_path()
                if resolved_pack_path:
                    self._language_pack = BookLanguagePack(resolved_pack_path)
            return
        self._cache = cache_service
        self._translator = translation_service
        self._language_pack = BookLanguagePack(language_pack_path or self._resolve_language_pack_path())
        self._initialized = True

    @staticmethod
    def _resolve_language_pack_path() -> Path | None:
        if has_app_context() and current_app.static_folder:
            return Path(current_app.static_folder) / 'data' / 'book_language_pack.zh.json'
        return None

    # ==================== 分类校验 ====================

    # 合法的分类列表（中英文）
    VALID_CATEGORIES = {
        '小说',
        '非虚构',
        '悬疑',
        '言情',
        '惊悚',
        '科幻',
        '奇幻',
        '传记',
        '历史',
        '儿童读物',
        '青少年',
        '商业',
        '自助',
        'Fiction',
        'Nonfiction',
        'Mystery',
        'Romance',
        'Thriller',
        'Science Fiction',
        'Fantasy',
        'Biography',
        'History',
        'Children',
        'Young Adult',
        'Business',
        'Self-Help',
    }

    @staticmethod
    def _sanitize_category(category: str | None) -> str | None:
        """
        清洗分类数据，过滤掉无效的营销文案

        Args:
            category: 原始分类字符串

        Returns:
            清洗后的分类，无效则返回 None
        """
        if not category:
            return None

        category = category.strip()

        # 长度检查：分类通常不超过20个字符
        if len(category) > 30:
            return None

        # 包含营销关键词的过滤
        marketing_keywords = [
            'learn more',
            'read more',
            'see what',
            'take the quiz',
            'join our',
            'browse all',
            'how to',
            'on the rise',
            'you need to',
            'you love',
            'audiobook',
            'events',
            'new releases',
            'new stories',
            'lists, essays',
        ]
        category_lower = category.lower()
        for keyword in marketing_keywords:
            if keyword in category_lower:
                return None

        # 包含特殊字符的过滤（>、<、!、http等）
        if re.search(r'[>!<]|http[s]?://', category):
            return None

        # 包含引号的过滤
        if '"' in category or '"' in category or '"' in category:
            return None

        return category

    # ==================== 出版社管理 ====================

    # 旧爬虫 -> 新爬虫的迁移映射
    # v1.6.0: HTML 爬虫 -> Google Books 搜索爬虫
    # v1.7.0: Google Books 搜索爬虫 -> 官网直接爬虫（如有）
    _CRAWLER_MIGRATION = {
        'SimonSchusterCrawler': 'SimonSchusterGoogleCrawler',
        'HachetteCrawler': 'HachetteCrawler',  # 自身已是最新
        'HarperCollinsCrawler': 'HarperCollinsCrawler',
        'MacmillanCrawler': 'MacmillanCrawler',
        'HachetteGoogleCrawler': 'HachetteCrawler',
        'HarperCollinsGoogleCrawler': 'HarperCollinsCrawler',
        'MacmillanGoogleCrawler': 'MacmillanCrawler',
    }

    def init_publishers(self) -> int:
        """
        初始化默认出版社数据

        同时将已失效的 HTML 爬虫迁移到 Google Books 搜索爬虫。

        Returns:
            创建的出版社数量
        """
        count = 0

        for pub_data in self.DEFAULT_PUBLISHERS:
            # 检查是否已存在
            existing = Publisher.query.filter_by(name_en=pub_data['name_en']).first()
            if existing:
                # 迁移：如果使用旧爬虫，更新为新爬虫
                if existing.crawler_class in self._CRAWLER_MIGRATION:
                    old_class = existing.crawler_class
                    new_class = self._CRAWLER_MIGRATION[old_class]
                    existing.crawler_class = new_class
                    logger.info(f'出版社爬虫迁移: {pub_data["name_en"]} {old_class} -> {new_class}')
                else:
                    logger.info(f'出版社已存在: {pub_data["name_en"]}')
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
            logger.info(f'创建出版社: {pub_data["name_en"]}')

        if count > 0:
            db.session.commit()
            logger.info(f'成功创建 {count} 个出版社')
        else:
            logger.info('所有出版社已存在，无需创建')

        return count

    def ensure_static_data_seeded(self) -> dict[str, Any] | None:
        """Seed bundled new-book data when the database has no displayable books."""
        existing_books = NewBook.query.filter(NewBook.is_displayable.is_(True)).count()
        if existing_books > 0:
            return None
        return self.seed_from_static_data()

    def seed_from_static_data(self, static_data_dir: str | Path | None = None) -> dict[str, Any]:
        """Import bundled static new-book JSON files into the database.

        The static files are a safe fallback for fresh deployments where the
        scheduled crawler has not run yet or external crawler credentials are
        unavailable.
        """
        from .publisher_crawler.base_crawler import BookInfo

        self.init_publishers()

        data_dir = self._resolve_static_data_dir(static_data_dir)
        result: dict[str, Any] = {
            'success': True,
            'files_seen': 0,
            'total': 0,
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }

        for filename, publisher_name in self.STATIC_DATA_FILES.items():
            path = data_dir / filename
            if not path.exists():
                continue

            publisher = Publisher.query.filter_by(name_en=publisher_name).first()
            if not publisher:
                logger.warning('静态新书导入跳过，出版社不存在: %s', publisher_name)
                continue

            result['files_seen'] += 1
            try:
                rows = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning('静态新书文件读取失败 %s: %s', path, e)
                result['errors'] += 1
                continue

            if not isinstance(rows, list):
                logger.warning('静态新书文件格式无效: %s', path)
                result['errors'] += 1
                continue

            touched_books: list[NewBook] = []
            for row in rows:
                if not isinstance(row, dict):
                    result['skipped'] += 1
                    continue

                title = (row.get('title') or '').strip()
                author = (row.get('author') or '').strip()
                if not title or not author:
                    result['skipped'] += 1
                    continue

                try:
                    book_info = BookInfo(
                        title=title,
                        author=author,
                        isbn13=self._normalize_isbn(row.get('isbn13'), 13),
                        isbn10=self._normalize_isbn(row.get('isbn10'), 10),
                        description=row.get('description'),
                        cover_url=row.get('cover_url'),
                        category=row.get('category'),
                        publication_date=self._parse_static_date(row.get('publication_date')),
                        price=row.get('price'),
                        page_count=self._parse_int(row.get('page_count')),
                        language=row.get('language'),
                        buy_links=row.get('buy_links') if isinstance(row.get('buy_links'), list) else [],
                        source_url=row.get('source_url'),
                    )
                    save_result = self._save_book(
                        publisher,
                        book_info,
                        translate=False,
                        auto_commit=False,
                        touched_books=touched_books,
                    )
                    result['total'] += 1
                    if save_result == 'added':
                        result['added'] += 1
                    elif save_result == 'updated':
                        result['updated'] += 1
                    else:
                        result['skipped'] += 1
                except Exception as e:
                    logger.warning('静态新书导入失败: %s - %s', title, e)
                    result['errors'] += 1

            try:
                self._translate_and_store_language_pack(touched_books, translate=False)
                publisher.last_sync_at = datetime.now(UTC)
                if touched_books:
                    publisher.sync_count = (publisher.sync_count or 0) + 1
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.warning('静态新书批量提交失败 %s: %s', filename, e)
                result['errors'] += 1

        logger.info(
            '静态新书兜底导入完成: 文件%s个, 新增%s本, 更新%s本, 跳过%s本, 错误%s',
            result['files_seen'],
            result['added'],
            result['updated'],
            result['skipped'],
            result['errors'],
        )
        return result

    @staticmethod
    def _resolve_static_data_dir(static_data_dir: str | Path | None = None) -> Path:
        if static_data_dir:
            return Path(static_data_dir)
        if has_app_context() and current_app.static_folder:
            return Path(current_app.static_folder) / 'data'
        return Path(__file__).resolve().parents[2] / 'static' / 'data'

    @staticmethod
    def _normalize_isbn(value: Any, length: int) -> str | None:
        if not value:
            return None
        clean = re.sub(r'[^0-9Xx]', '', str(value)).upper()
        return clean if len(clean) == length else None

    @staticmethod
    def _parse_static_date(value: Any) -> date | None:
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        text = str(value).strip()
        for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
            try:
                parsed = datetime.strptime(text, fmt)
                if fmt == '%Y':
                    return date(parsed.year, 1, 1)
                if fmt == '%Y-%m':
                    return date(parsed.year, parsed.month, 1)
                return parsed.date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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

    def get_publisher_book_counts(self) -> dict[int, int]:
        """
        批量获取各出版社的书籍数量，避免N+1查询

        Returns:
            {publisher_id: book_count} 字典
        """
        from sqlalchemy import func

        results = (
            db.session.query(NewBook.publisher_id, func.count(NewBook.id).label('count'))
            .group_by(NewBook.publisher_id)
            .all()
        )
        return dict(results)

    def get_publisher(self, publisher_id: int) -> Publisher | None:
        """
        获取单个出版社

        Args:
            publisher_id: 出版社ID

        Returns:
            出版社对象或None
        """
        return db.session.get(Publisher, publisher_id)

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
        logger.info(f'更新出版社状态: {publisher.name_en} -> {"启用" if is_active else "禁用"}')
        return True

    # ==================== 爬虫管理 ====================

    # Google Books 相关爬虫类名列表（都需要 API Key）
    # v1.7.0: Hachette/HarperCollins 已改用官网直接爬取，不再需要 API Key
    _GOOGLE_BOOKS_CRAWLERS = {
        'GoogleBooksCrawler',
        'SimonSchusterGoogleCrawler',
        'HachetteGoogleCrawler',
        'HarperCollinsGoogleCrawler',
        'MacmillanGoogleCrawler',
        'MacmillanCrawler',  # v1.7.0: Sitemap+Google Books 双路策略
    }

    def get_crawler(self, crawler_class: str):
        """
        获取爬虫实例

        Args:
            crawler_class: 爬虫类名

        Returns:
            爬虫实例或None
        """
        from .publisher_crawler import get_crawler_class

        crawler_cls = get_crawler_class(crawler_class)
        if not crawler_cls:
            logger.error(f'未找到爬虫类: {crawler_class}')
            return None

        # Google Books 系列爬虫需要 API key
        if crawler_class in self._GOOGLE_BOOKS_CRAWLERS:
            from flask import current_app

            api_key = current_app.config.get('GOOGLE_API_KEY') if current_app else None
            if api_key:
                from .publisher_crawler.base_crawler import CrawlerConfig

                config = CrawlerConfig(api_key=api_key)
                return crawler_cls(config)

        return crawler_cls()

    def sync_publisher_books(
        self, publisher_id: int, category: str | None = None, max_books: int = 50, translate: bool = True
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

        batch_commit_interval = 10
        touched_books: list[NewBook] = []

        try:
            logger.info(f'开始同步 {publisher.name_en} 新书...')

            with crawler:
                for book_info in crawler.get_new_books(category=category, max_books=max_books):
                    result['total'] += 1

                    try:
                        save_result = self._save_book(
                            publisher,
                            book_info,
                            translate,
                            auto_commit=False,
                            touched_books=touched_books,
                        )

                        if save_result == 'added':
                            result['added'] += 1
                        elif save_result == 'updated':
                            result['updated'] += 1
                        else:
                            result['skipped'] += 1

                    except Exception as e:
                        logger.error(f'保存书籍失败: {book_info.title} - {e}')
                        result['errors'] += 1

                    if result['total'] % batch_commit_interval == 0:
                        db.session.commit()

            result['language_pack'] = self._translate_and_store_language_pack(touched_books, translate=translate)

            publisher.last_sync_at = datetime.now(UTC)
            publisher.sync_count += 1
            db.session.commit()

            logger.info(
                f'同步完成: {publisher.name_en} - '
                f'总计 {result["total"]}, 新增 {result["added"]}, '
                f'更新 {result["updated"]}, 跳过 {result["skipped"]}'
            )

        except Exception as e:
            logger.error(f'同步失败: {e}')
            db.session.rollback()
            result['success'] = False
            result['error'] = str(e)

        return result

    def sync_all_publishers(
        self,
        category: str | None = None,
        max_books_per_publisher: int = 30,
        translate: bool = True,
        batch_size: int = 1,
    ) -> list[dict[str, Any]]:
        """
        同步所有启用出版社的新书数据

        Args:
            category: 分类筛选
            max_books_per_publisher: 每个出版社最大同步数量
            translate: 是否翻译
            batch_size: 批处理大小，每批处理的出版社数量

        Returns:
            各出版社同步结果列表
        """
        results = []
        publishers = self.get_publishers(active_only=True)

        logger.info(f'开始同步 {len(publishers)} 个出版社...')
        logger.info(f'批处理大小: {batch_size}')

        # 分批处理出版社
        for i in range(0, len(publishers), batch_size):
            batch = publishers[i : i + batch_size]
            logger.info(f'处理批次 {i // batch_size + 1}/{(len(publishers) + batch_size - 1) // batch_size}')

            for publisher in batch:
                result = self.sync_publisher_books(
                    publisher.id, category=category, max_books=max_books_per_publisher, translate=translate
                )
                results.append(result)

                # 每处理完一个出版社，强制垃圾回收，减少内存使用
                gc.collect()

        # 汇总统计
        total_added = sum(r.get('added', 0) for r in results)
        total_updated = sum(r.get('updated', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)

        logger.info(f'全部同步完成: 新增 {total_added}, 更新 {total_updated}, 错误 {total_errors}')

        return results

    # ==================== 书籍管理 ====================

    def _save_book(
        self,
        publisher: Publisher,
        book_info,
        translate: bool = True,
        auto_commit: bool = True,
        touched_books: list[NewBook] | None = None,
    ) -> str:
        """
        保存书籍到数据库

        Args:
            publisher: 出版社对象
            book_info: 书籍信息
            translate: 是否翻译
            auto_commit: 是否自动提交（批量同步时设为False）
            touched_books: 收集本轮同步触达的书籍，用于批量写入语言包

        Returns:
            操作结果: 'added', 'updated', 'skipped'
        """
        existing = None

        if book_info.isbn13:
            existing = NewBook.query.filter_by(publisher_id=publisher.id, isbn13=book_info.isbn13).first()

        if not existing and book_info.isbn10:
            existing = NewBook.query.filter_by(publisher_id=publisher.id, isbn10=book_info.isbn10).first()

        if not existing:
            existing = NewBook.query.filter_by(
                publisher_id=publisher.id, title=book_info.title, author=book_info.author
            ).first()

        if existing:
            updated = self._update_book_fields(existing, book_info, auto_commit=auto_commit)
            translated = False
            if translate and self._translator:
                translated = self._translate_book(existing)
            if touched_books is not None:
                touched_books.append(existing)
            if updated:
                return 'updated'
            if translated:
                if auto_commit:
                    db.session.commit()
                return 'updated'
            return 'skipped'

        new_book = NewBook(
            publisher_id=publisher.id,
            title=book_info.title,
            author=book_info.author,
            isbn13=book_info.isbn13,
            isbn10=book_info.isbn10,
            description=book_info.description,
            cover_url=book_info.cover_url,
            category=self._sanitize_category(book_info.category),
            publication_date=book_info.publication_date,
            price=book_info.price,
            page_count=book_info.page_count,
            language=book_info.language,
            source_url=book_info.source_url,
        )

        if book_info.buy_links:
            new_book.set_buy_links(book_info.buy_links)

        if translate and self._translator:
            self._translate_book(new_book)

        db.session.add(new_book)
        if touched_books is not None:
            touched_books.append(new_book)
        if auto_commit:
            db.session.commit()

        return 'added'

    def _update_book_fields(self, book: NewBook, book_info, auto_commit: bool = True) -> bool:
        """
        更新书籍字段

        Args:
            book: 书籍对象
            book_info: 新的书籍信息
            auto_commit: 是否自动提交

        Returns:
            是否有更新
        """
        updated = False

        if book_info.description and book_info.description != book.description:
            book.description = book_info.description
            book.description_zh = None
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
            book.updated_at = datetime.now(UTC)
            if auto_commit:
                db.session.commit()

        return updated

    def translate_book_background(self, book_id: int, translation_service: Any) -> None:
        """
        后台翻译新书（用于 new_book_detail 路由异步翻译）

        Args:
            book_id: 书籍ID
            translation_service: 翻译服务实例
        """
        try:
            book = self.get_book(book_id)
            if not book:
                return

            if not book.title_zh and book.title:
                book.title_zh = translation_service.translate(
                    book.title, 'en', 'zh', field_type='title'
                )
            if book.description and not book.description_zh:
                book.description_zh = translation_service.translate(
                    book.description[:1000], 'en', 'zh', field_type='description'
                )
            db.session.commit()
            logger.info(f'Book {book_id} translated in background')
        except Exception as e:
            logger.warning(f'Background translation failed for book {book_id}: {e}')
            try:
                db.session.rollback()
            except Exception:
                pass

    def _translate_book(self, book: NewBook) -> bool:
        """
        翻译书籍信息

        Args:
            book: 书籍对象
        """
        if not self._translator:
            return False

        try:
            changed = False
            # 翻译书名
            if book.title and not book.title_zh:
                book.title_zh = self._translator.translate(book.title, 'en', 'zh', field_type='title')
                changed = bool(book.title_zh)

            # 翻译简介
            if book.description and not book.description_zh:
                book.description_zh = self._translator.translate(
                    book.description[:1000],  # 限制长度
                    'en',
                    'zh',
                    field_type='description',
                )
                changed = bool(book.description_zh) or changed
            return changed

        except Exception as e:
            logger.warning(f'翻译失败: {book.title} - {e}')
            return False

    def _hydrate_language_pack(self, books: list[NewBook]) -> None:
        try:
            self._language_pack.hydrate_books(books)
        except Exception as e:
            logger.debug('新书语言包补齐跳过: %s', e)

    def _translate_and_store_language_pack(self, books: list[NewBook], translate: bool = True) -> dict[str, int]:
        if not books:
            return {
                'books_seen': 0,
                'books_missing': 0,
                'fields_from_pack': 0,
                'fields_stored': 0,
                'fields_translated': 0,
                'failures': 0,
                'pack_writes': 0,
            }

        translator = self._translator if translate else None
        try:
            stats = self._language_pack.translate_and_store_books(books, translator=translator)
            logger.info(
                '新书语言包同步完成: 触达%s本, 新翻译字段%s个, 写入%s次',
                stats.get('books_seen', 0),
                stats.get('fields_translated', 0),
                stats.get('pack_writes', 0),
            )
            return stats
        except Exception as e:
            logger.warning('新书语言包同步失败: %s', e)
            return {
                'books_seen': len(books),
                'books_missing': 0,
                'fields_from_pack': 0,
                'fields_stored': 0,
                'fields_translated': 0,
                'failures': len(books),
                'pack_writes': 0,
            }

    # ==================== 查询接口 ====================

    def get_new_books(
        self,
        publisher_id: int | None = None,
        category: str | None = None,
        days: int = 30,
        page: int = 1,
        per_page: int = 20,
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
        from sqlalchemy.orm import joinedload

        query = NewBook.query.options(joinedload(NewBook.publisher)).filter(NewBook.is_displayable.is_(True))

        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        query = query.filter(NewBook.created_at >= cutoff_date)

        if publisher_id:
            query = query.filter(NewBook.publisher_id == publisher_id)

        if category:
            query = query.filter(NewBook.category == category)

        query = query.order_by(NewBook.publication_date.desc().nullslast(), NewBook.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        self._hydrate_language_pack(pagination.items)

        return pagination.items, pagination.total

    def get_book(self, book_id: int) -> NewBook | None:
        """
        获取单本书籍详情（预加载出版社信息）

        Args:
            book_id: 书籍ID

        Returns:
            书籍对象或None
        """
        from sqlalchemy.orm import joinedload

        book = NewBook.query.options(joinedload(NewBook.publisher)).get(book_id)
        if book:
            self._hydrate_language_pack([book])
        return book

    def search_books(self, keyword: str, page: int = 1, per_page: int = 20) -> tuple[list[NewBook], int]:
        """
        搜索书籍

        Args:
            keyword: 搜索关键词
            page: 页码
            per_page: 每页数量

        Returns:
            (书籍列表, 总数)
        """
        from sqlalchemy.orm import joinedload

        search_pattern = f'%{keyword}%'

        query = (
            NewBook.query.options(joinedload(NewBook.publisher))
            .filter(
                db.or_(
                    NewBook.title.ilike(search_pattern),
                    NewBook.title_zh.ilike(search_pattern),
                    NewBook.author.ilike(search_pattern),
                    NewBook.isbn13 == keyword,
                    NewBook.isbn10 == keyword,
                )
            )
            .filter(NewBook.is_displayable.is_(True))
        )

        query = query.order_by(NewBook.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        self._hydrate_language_pack(pagination.items)

        return pagination.items, pagination.total

    def get_categories(self) -> list[dict[str, str]]:
        """
        获取所有分类

        Returns:
            分类列表
        """
        from sqlalchemy import func

        results = (
            db.session.query(NewBook.category, func.count(NewBook.id).label('count'))
            .filter(NewBook.category.isnot(None), NewBook.is_displayable.is_(True))
            .group_by(NewBook.category)
            .order_by(func.count(NewBook.id).desc())
            .all()
        )

        return [{'name': r.category, 'count': r.count} for r in results]

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
        week_ago = datetime.now(UTC) - timedelta(days=7)
        recent_books = NewBook.query.filter(NewBook.created_at >= week_ago).count()

        # 分类统计
        category_stats = (
            db.session.query(NewBook.category, func.count(NewBook.id).label('count'))
            .filter(NewBook.category.isnot(None))
            .group_by(NewBook.category)
            .order_by(func.count(NewBook.id).desc())
            .limit(10)
            .all()
        )

        return {
            'total_books': total_books,
            'total_publishers': total_publishers,
            'active_publishers': active_publishers,
            'recent_books_7d': recent_books,
            'top_categories': [{'category': c.category, 'count': c.count} for c in category_stats],
        }
