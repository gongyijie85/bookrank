import logging
from typing import Any

from ..models.schemas import Book, BookMetadata, db
from .cache_service import CacheService
from .api_client import NYTApiClient, GoogleBooksClient, ImageCacheService
from ..utils.exceptions import APIRateLimitException, APIException

logger = logging.getLogger(__name__)


class BookService:
    """图书业务服务"""
    
    def __init__(
        self,
        nyt_client: NYTApiClient,
        google_client: GoogleBooksClient,
        cache_service: CacheService,
        image_cache: ImageCacheService,
        max_workers: int = 4,
        categories: dict | None = None
    ):
        self._nyt_client = nyt_client
        self._google_client = google_client
        self._cache = cache_service
        self._image_cache = image_cache
        self._max_workers = max_workers
        self._categories = categories or {}
        
        # 线程安全：防止重复启动预翻译线程
        self._translation_thread_active = False
    
    def get_books_by_category(self, category_id: str, force_refresh: bool = False) -> list[Book]:
        """
        获取指定分类的图书列表
        
        Args:
            category_id: 分类ID
            force_refresh: 是否强制刷新缓存
            
        Returns:
            图书列表
        """
        cache_key = f"books_{category_id}"
        
        # 尝试从缓存获取
        if not force_refresh:
            cached_data = self._cache.get(cache_key)
            if cached_data:
                logger.info(f"Returning cached books for {category_id}")
                return [Book(**book_data) for book_data in cached_data]
        
        # 从API获取
        try:
            api_data = self._nyt_client.fetch_books(category_id)
            books = self._process_api_response(api_data, category_id)
            
            # 缓存结果 - NYT数据每周更新，缓存24小时
            books_data = [book.to_dict() for book in books]
            self._cache.set(cache_key, books_data, ttl=86400)  # 24小时
            
            logger.info(f"Fetched and cached {len(books)} books for {category_id}")

            # 启动后台预翻译（不阻塞响应）
            self._auto_translate_books(books)

            return books
            
        except APIRateLimitException:
            # 限流时返回缓存数据（即使已过期）
            cached_data = self._cache.get(cache_key)
            if cached_data:
                logger.warning(f"Rate limited, returning stale cache for {category_id}")
                return [Book(**book_data) for book_data in cached_data]
            raise
        except APIException as e:
            logger.error(f"Failed to fetch books for {category_id}: {e}")
            # 返回缓存数据作为降级
            cached_data = self._cache.get(cache_key)
            if cached_data:
                return [Book(**book_data) for book_data in cached_data]
            return []
    
    def _process_api_response(self, api_data: dict[str, Any], category_id: str) -> list[Book]:
        """
        处理API响应数据
        
        Args:
            api_data: API响应数据
            category_id: 分类ID
            
        Returns:
            处理后的图书列表
        """
        results = api_data.get('results', {})
        raw_books = results.get('books', [])
        list_name = results.get('list_name', 'Unknown List')
        published_date = results.get('published_date', 'Unknown')
        
        category_name = self._categories.get(category_id, category_id)
        
        isbns = [b.get('primary_isbn13') or b.get('primary_isbn10', '') for b in raw_books]
        translations = self._batch_get_translations(isbns)
        supplements = self._batch_get_supplements(isbns)
        
        processed_books = []
        for book_data in raw_books:
            try:
                book = self._process_single_book(
                    book_data,
                    category_id,
                    category_name,
                    list_name,
                    published_date,
                    translations,
                    supplements
                )
                if book:
                    processed_books.append(book)
            except Exception as e:
                logger.error(f"Error processing book: {e}")
        
        processed_books.sort(key=lambda x: x.rank)
        return processed_books
    
    def _batch_get_translations(self, isbns: list[str]) -> dict[str, dict]:
        """批量获取翻译数据，避免在子线程中访问数据库"""
        translations = {}
        if not isbns:
            return translations
        try:
            from ..models.schemas import BookMetadata
            records = BookMetadata.query.filter(
                BookMetadata.isbn.in_(isbns)
            ).all()
            for r in records:
                translations[r.isbn] = {
                    'title_zh': r.title_zh,
                    'description_zh': r.description_zh,
                    'details_zh': r.details_zh
                }
        except Exception as e:
            logger.debug(f"批量获取翻译失败: {e}")
        return translations
    
    def _batch_get_supplements(self, isbns: list[str]) -> dict[str, dict]:
        """并发获取Google Books补充信息，提升批量查询效率"""
        supplements = {}
        if not isbns:
            return supplements

        valid_isbns = [isbn for isbn in isbns if isbn]
        if not valid_isbns:
            return supplements

        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _fetch_one(isbn: str) -> tuple[str, dict]:
                try:
                    return isbn, self._google_client.fetch_book_details(isbn)
                except Exception:
                    return isbn, {}

            with ThreadPoolExecutor(max_workers=min(self._max_workers, len(valid_isbns))) as executor:
                futures = {executor.submit(_fetch_one, isbn): isbn for isbn in valid_isbns}
                for future in as_completed(futures):
                    isbn, result = future.result()
                    supplements[isbn] = result
        except Exception as e:
            logger.debug("并发获取补充信息失败，降级为串行: %s", e)
            for isbn in valid_isbns:
                try:
                    supplements[isbn] = self._google_client.fetch_book_details(isbn)
                except Exception:
                    supplements[isbn] = {}

        return supplements
    
    def _process_single_book(
        self,
        book_data: dict[str, Any],
        category_id: str,
        category_name: str,
        list_name: str,
        published_date: str,
        translations: dict[str, dict],
        supplements: dict[str, dict]
    ) -> Book | None:
        """
        处理单本图书数据
        
        Args:
            book_data: 原始图书数据
            category_id: 分类ID
            category_name: 分类名称
            list_name: 榜单名称
            published_date: 发布日期
            translations: 翻译数据字典
            supplements: 补充信息字典
            
        Returns:
            处理后的Book对象
        """
        isbn = book_data.get('primary_isbn13') or book_data.get('primary_isbn10', '')
        
        supplement = supplements.get(isbn, {})
        
        book = Book.from_api_response(
            book_data=book_data,
            category_id=category_id,
            category_name=category_name,
            list_name=list_name,
            published_date=published_date,
            supplement=supplement
        )
        
        book.cover = self._image_cache.get_cached_image_url(
            book_data.get('book_image')
        )
        
        if isbn in translations:
            trans = translations[isbn]
            book.title_zh = trans.get('title_zh')
            book.description_zh = trans.get('description_zh')
            book.details_zh = trans.get('details_zh')
        
        return book
    
    def _attach_translation(self, book: Book, isbn: str):
        """
        附加翻译内容到图书对象
        
        Args:
            book: Book对象
            isbn: ISBN
        """
        if not isbn:
            return
        
        try:
            from flask import current_app
            app = current_app._get_current_object()
            with app.app_context():
                metadata = BookMetadata.query.get(isbn)
                if metadata:
                    book.description_zh = metadata.description_zh
                    book.details_zh = metadata.details_zh
        except Exception as e:
            logger.debug(f"获取翻译失败 for {isbn}: {e}")
    
    def save_book_translation(self, isbn: str, title_zh: str = None, description_zh: str = None, details_zh: str = None) -> bool:
        """
        保存图书翻译到数据库

        Args:
            isbn: 图书ISBN
            title_zh: 翻译后的书名
            description_zh: 翻译后的描述
            details_zh: 翻译后的详情

        Returns:
            是否保存成功
        """
        if not isbn:
            return False

        try:
            metadata = BookMetadata.query.get(isbn)
            if not metadata:
                # 如果没有元数据记录，创建一个新记录
                metadata = BookMetadata(
                    isbn=isbn,
                    title='',
                    author=''
                )
                db.session.add(metadata)

            if title_zh:
                metadata.title_zh = title_zh
            if description_zh:
                metadata.description_zh = description_zh
            if details_zh:
                metadata.details_zh = details_zh
            
            from datetime import datetime, timezone
            metadata.translated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            logger.info(f"翻译已保存: {isbn}")
            return True
            
        except Exception as e:
            logger.error(f"保存翻译失败: {e}")
            db.session.rollback()
            return False

    def _auto_translate_books(self, books: list[Book]) -> None:
        """
        自动预翻译图书信息（后台异步执行）

        在后台线程中自动翻译图书的标题和描述，
        并保存到数据库，下次访问时直接读取已翻译内容

        Args:
            books: 图书列表
        """
        # 线程安全检查：如果已有翻译线程在运行，跳过
        if self._translation_thread_active:
            logger.info("预翻译线程已在运行中，跳过重复启动")
            return

        if not books or len(books) == 0:
            logger.debug("无图书数据，跳过预翻译")
            return

        import threading
        import time

        def translate_in_background():
            """后台线程执行翻译任务"""
            try:
                from .zhipu_translation_service import get_translation_service

                service = get_translation_service()
                if not service or not service.zhipu.is_available():
                    logger.warning("智谱AI不可用，跳过预翻译")
                    return

                translated_count = 0
                for book in books:
                    isbn = book.isbn13 or book.isbn10
                    if not isbn:
                        continue

                    # 跳过已有完整翻译的图书
                    if book.title_zh and book.description_zh:
                        continue

                    try:
                        # 翻译书名（最重要）
                        title_zh = None
                        if not book.title_zh and book.title:
                            title_zh = service.translate(book.title)
                            if title_zh:
                                logger.info(f"预翻译书名: {book.title[:30]}... -> {title_zh[:30]}...")

                        # 翻译描述
                        desc_zh = None
                        if book.description:
                            desc_zh = service.translate(book.description)
                            if desc_zh:
                                logger.debug(f"预翻译描述: {isbn}")

                        # 保存到数据库
                        if title_zh or desc_zh:
                            self.save_book_translation(
                                isbn=isbn,
                                title_zh=title_zh,
                                description_zh=desc_zh,
                                details_zh=book.details_zh
                            )
                            translated_count += 1

                        # 添加延迟避免API限流（0.2秒间隔）
                        time.sleep(0.2)

                    except Exception as e:
                        logger.error(f"预翻译失败 {isbn}: {e}")
                        continue

                logger.info(f"批量预翻译完成: 共翻译 {translated_count} 本图书")

            except Exception as e:
                logger.error(f"后台翻译线程异常: {e}")
            finally:
                # 无论成功失败，都清除线程活动标志
                self._translation_thread_active = False

        # 设置线程活动标志
        self._translation_thread_active = True

        # 启动守护线程（主进程退出时自动结束）
        thread = threading.Thread(target=translate_in_background, daemon=True)
        thread.start()
        logger.info(f"已启动后台预翻译线程，共 {len(books)} 本图书待处理")
    
    def _get_book_supplement(self, isbn: str, book_data: dict[str, Any]) -> dict[str, Any]:
        """
        获取图书补充信息
        
        Args:
            isbn: 图书ISBN
            book_data: 原始图书数据
            
        Returns:
            补充信息字典
        """
        if not isbn:
            return {}
        
        supplement = self._google_client.fetch_book_details(isbn)
        
        return supplement
    
    def search_books(self, keyword: str, categories: list[str] | None = None) -> list[Book]:
        """
        搜索图书
        
        Args:
            keyword: 搜索关键词
            categories: 要搜索的分类列表，默认为所有分类
            
        Returns:
            匹配的图书列表
        """
        if not categories:
            categories = list(self._categories.keys())
        
        results = []
        keyword_lower = keyword.lower()
        
        for category_id in categories:
            try:
                books = self.get_books_by_category(category_id)
                for book in books:
                    if (keyword_lower in book.title.lower() or 
                        keyword_lower in book.author.lower()):
                        results.append(book)
            except Exception as e:
                logger.error(f"Error searching in category {category_id}: {e}")
        
        return results
    
    def get_latest_cache_time(self) -> str:
        """获取最新的缓存时间"""
        latest_time = None
        
        for category_id in self._categories.keys():
            cache_time = self._cache.get_cache_time(f"books_{category_id}")
            if cache_time:
                from datetime import datetime
                try:
                    cache_dt = datetime.strptime(cache_time, "%Y-%m-%d %H:%M:%S")
                    if not latest_time or cache_dt > latest_time:
                        latest_time = cache_dt
                except ValueError:
                    continue
        
        return latest_time.strftime("%Y-%m-%d %H:%M:%S") if latest_time else "暂无数据"
