"""
图书服务测试

测试 BookService 的核心功能，包括获取图书列表、搜索图书、保存翻译等
"""

import json
from unittest.mock import Mock, patch

import pytest

from app.models.book import Book
from app.models.schemas import BookMetadata, SystemConfig, TranslationCache
from app.services.book_language_pack import BookLanguagePack
from app.services.book_service import BookService
from app.services.translation_cache_service import TranslationCacheService
from app.utils.exceptions import APIException


class TestBookService:
    """图书服务测试类"""

    @pytest.fixture
    def book_service(self, db):
        """创建图书服务实例"""
        # 模拟依赖服务
        nyt_client = Mock()
        google_client = Mock()
        cache_service = Mock()
        image_cache = Mock()

        # 配置模拟对象
        nyt_client.fetch_books.return_value = {
            'results': {
                'list_name': 'Hardcover Fiction',
                'published_date': '2024-01-14',
                'books': [
                    {
                        'primary_isbn13': '9780143127550',
                        'primary_isbn10': '014312755X',
                        'rank': 1,
                        'title': 'Test Book Title',
                        'author': 'Test Author',
                        'description': 'A compelling story.',
                        'book_image': 'https://example.com/image.jpg',
                        'publisher': 'Test Publisher',
                        'weeks_on_list': 10,
                        'rank_last_week': '2',
                        'price': '28.00',
                        'buy_links': [{'name': 'Amazon', 'url': 'https://amazon.com'}],
                    }
                ],
            }
        }

        google_client.fetch_book_details.return_value = {
            'isbn_13': '9780143127550',
            'isbn_10': '014312755X',
            'title': 'Test Book Title',
            'author': 'Test Author',
            'publisher': 'Test Publisher',
            'publication_dt': '2023-10-01',
            'page_count': 320,
            'language': 'eng',
            'details': 'Detailed book description from Google Books.',
            'cover_url': 'https://example.com/cover.jpg',
        }

        cache_service.get.return_value = None
        cache_service.get_stale.return_value = None
        cache_service.set.return_value = True
        cache_service.get_cache_time.return_value = '2024-01-14 12:00:00'

        image_cache.get_cached_image_url.return_value = 'https://example.com/cached_image.jpg'

        # 创建图书服务实例
        return BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            categories={'hardcover-fiction': '精装小说'},
        )

    def test_get_books_by_category(self, book_service, db):
        """测试获取指定分类的图书列表"""
        # 执行测试
        books = book_service.get_books_by_category('hardcover-fiction', auto_translate=False)

        # 验证结果
        assert len(books) == 1
        assert isinstance(books[0], Book)
        assert books[0].title == 'Test Book Title'
        assert books[0].author == 'Test Author'
        assert books[0].isbn13 == '9780143127550'
        assert books[0].category_id == 'hardcover-fiction'

    def test_force_refresh_reaches_nyt_client(self, book_service):
        book_service.get_books_by_category('hardcover-fiction', force_refresh=True, auto_translate=False)

        book_service._nyt_client.fetch_books.assert_called_once_with('hardcover-fiction', force_refresh=True)

    def test_get_books_by_category_with_cache(self, book_service):
        """测试从缓存获取图书列表"""
        # 模拟缓存数据
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = cached_books

        # 执行测试
        books = book_service.get_books_by_category('hardcover-fiction')

        # 验证结果
        assert len(books) == 1
        assert books[0].title == 'Cached Book'
        assert books[0].author == 'Cached Author'

    def test_get_books_by_category_hydrates_cached_books_from_static_language_pack(self, book_service, tmp_path):
        """测试缓存图书会从静态语言包补齐中文字段"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        pack_path.write_text(
            json.dumps(
                {
                    'books': {
                        '9780143127550': {
                            'title_zh': '缓存书名',
                            'description_zh': '缓存简介',
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        book_service._language_pack = BookLanguagePack(pack_path)
        book_service._cache.get.return_value = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]

        books = book_service.get_books_by_category('hardcover-fiction')

        assert books[0].title_zh == '缓存书名'
        assert books[0].description_zh == '缓存简介'

    def test_get_books_by_category_hydrates_cached_books_from_translation_cache(self, book_service, db):
        """测试缓存图书会从翻译缓存补齐中文字段"""
        for source, translated in [('Cached Book', '缓存书名'), ('Test description', '缓存简介')]:
            db.session.add(
                TranslationCache(
                    source_hash=TranslationCacheService._compute_source_hash(source),
                    source_text=source,
                    source_lang='en',
                    target_lang='zh',
                    translated_text=translated,
                    model_name='test',
                )
            )
        db.session.commit()

        book_service._cache.get.return_value = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]

        books = book_service.get_books_by_category('hardcover-fiction')

        assert books[0].title_zh == '缓存书名'
        assert books[0].description_zh == '缓存简介'

    def test_language_pack_translates_and_writes_missing_fields(self, tmp_path):
        """测试语言包会翻译缺失字段并写回JSON文件"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book = Book(
            id='9780143127550',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            cover='',
            list_name='Hardcover Fiction',
            category_id='hardcover-fiction',
            category_name='精装小说',
            rank=1,
            weeks_on_list=1,
            rank_last_week='0',
            published_date='2024-01-01',
            description='A test description',
            details='Detailed book description',
            publication_dt='2024-01-01',
            page_count='200',
            language='English',
            buy_links=[],
            isbn13='9780143127550',
            isbn10='0143127550',
            price='19.99',
        )

        class FakeTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                return {
                    'title': '测试书名',
                    'description': '测试简介',
                    'details': '测试详情',
                }[field_type]

        stats = BookLanguagePack(pack_path).translate_and_store_books([book], translator=FakeTranslator())

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert stats['fields_translated'] == 3
        assert saved['books']['9780143127550']['title_zh'] == '测试书名'
        assert saved['books']['9780143127550']['description_zh'] == '测试简介'
        assert saved['books']['9780143127550']['details_zh'] == '测试详情'
        assert book.title_zh == '测试书名'

    def test_sync_all_categories_refreshes_metadata_and_language_pack(self, book_service, db, tmp_path):
        """测试每周NYT同步会补资料、翻译并写入语言包和数据库"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)

        class FakeTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                return {
                    'title': '测试书名',
                    'description': '测试简介',
                    'details': '测试详情',
                }[field_type]

        with patch.object(book_service, '_auto_translate_books') as auto_translate:
            results = book_service.sync_all_categories(translator=FakeTranslator())

        assert results == [
            {
                'category_id': 'hardcover-fiction',
                'category_name': '精装小说',
                'success': True,
                'books': 1,
                'metadata_saved': 1,
                'language_pack': {
                    'books_seen': 1,
                    'books_missing': 1,
                    'fields_from_pack': 0,
                    'fields_stored': 0,
                    'fields_translated': 3,
                    'failures': 0,
                    'pack_writes': 1,
                },
            }
        ]
        auto_translate.assert_not_called()

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert saved['books']['9780143127550']['title_zh'] == '测试书名'
        assert saved['books']['9780143127550']['description_zh'] == '测试简介'
        assert saved['books']['9780143127550']['details_zh'] == '测试详情'

        metadata = db.session.get(BookMetadata, '9780143127550')
        assert metadata is not None
        assert metadata.title == 'Test Book Title'
        assert metadata.author == 'Test Author'
        assert metadata.details == 'Detailed book description from Google Books.'
        assert metadata.title_zh == '测试书名'
        assert metadata.description_zh == '测试简介'
        assert metadata.details_zh == '测试详情'

    def test_get_books_by_category_returns_stale_cache_on_api_failure(self, book_service):
        """测试API失败时返回过期文件缓存"""
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = cached_books
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT unavailable')

        books = book_service.get_books_by_category('hardcover-fiction')

        assert len(books) == 1
        assert books[0].title == 'Cached Book'

    def test_get_books_by_category_treats_error_payload_as_failure(self, book_service):
        """测试NYT错误缓存不会被当成空榜单写入缓存"""
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = cached_books
        book_service._nyt_client.fetch_books.return_value = {'error': 'rate_limit_exceeded'}

        books = book_service.get_books_by_category('hardcover-fiction')

        assert len(books) == 1
        assert books[0].title == 'Cached Book'
        book_service._cache.set.assert_not_called()

    def test_save_book_translation(self, book_service, db):
        """测试保存图书翻译"""
        # 执行测试
        result = book_service.save_book_translation(
            isbn='9780143127550', title_zh='测试书名', description_zh='测试描述', details_zh='测试详情'
        )

        # 验证结果
        assert result is True

        # 验证数据库中是否保存了翻译
        metadata = db.session.get(BookMetadata, '9780143127550')
        assert metadata is not None
        assert metadata.title_zh == '测试书名'
        assert metadata.description_zh == '测试描述'
        assert metadata.details_zh == '测试详情'

    def test_save_book_translation_invalid_isbn(self, book_service):
        """测试保存图书翻译时ISBN无效的情况"""
        # 执行测试
        result = book_service.save_book_translation(isbn='', title_zh='测试书名')

        # 验证结果
        assert result is False

    def test_search_books(self, book_service):
        """测试搜索图书"""
        # 执行测试
        with patch.object(book_service, 'get_books_by_category') as mock_get_books:
            # 模拟返回的图书数据
            mock_book = Mock()
            mock_book.title = 'Test Book Title'
            mock_book.author = 'Test Author'
            mock_get_books.return_value = [mock_book]

            # 执行搜索
            results = book_service.search_books('Test')

            # 验证结果
            assert len(results) == 1

    def test_search_books_no_results(self, book_service):
        """测试搜索图书无结果的情况"""
        # 执行测试
        with patch.object(book_service, 'get_books_by_category') as mock_get_books:
            # 模拟返回的图书数据
            mock_book = Mock()
            mock_book.title = 'Other Book Title'
            mock_book.author = 'Other Author'
            mock_get_books.return_value = [mock_book]

            # 执行搜索
            results = book_service.search_books('Test')

            # 验证结果
            assert len(results) == 0

    def test_get_latest_cache_time(self, book_service):
        """测试获取最新缓存时间"""
        # 执行测试
        cache_time = book_service.get_latest_cache_time()

        # 验证结果
        assert cache_time == '2024-01-14 12:00:00'

    def test_get_latest_cache_time_no_data(self, book_service):
        """测试获取最新缓存时间时无数据的情况"""
        # 模拟缓存时间为None
        book_service._cache.get_cache_time.return_value = None

        # 执行测试
        cache_time = book_service.get_latest_cache_time()

        # 验证结果
        assert cache_time == '暂无数据'

    def test_save_book_metadata_batch_uses_single_select(self, book_service, db, app):
        """测试批量保存元数据只发起一次 SELECT 查询（避免 N+1）"""
        from sqlalchemy import event

        books = [
            Book(
                id='9780000001001',
                title=f'Batch Book {i}',
                author=f'Author {i}',
                publisher='Publisher',
                cover='',
                list_name='Test',
                category_id='hardcover-fiction',
                category_name='精装小说',
                rank=i,
                weeks_on_list=1,
                rank_last_week='0',
                published_date='2024-01-01',
                description='desc',
                details='details',
                publication_dt='2024-01-01',
                page_count='200',
                language='English',
                buy_links=[],
                isbn13=f'978000000100{i}',
                isbn10=f'000000100{i}',
                price='19.99',
            )
            for i in range(1, 6)
        ]

        select_count = 0

        def _count_selects(conn, cursor, statement, parameters, context, executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith('SELECT'):
                select_count += 1

        with app.app_context():
            event.listen(db.engine, 'before_cursor_execute', _count_selects)
            try:
                saved = book_service.save_book_metadata_batch(books)
            finally:
                event.remove(db.engine, 'before_cursor_execute', _count_selects)

        assert saved == 5
        assert select_count == 1  # 一次 IN 查询

    def test_save_book_metadata_loop_uses_multiple_selects(self, book_service, db, app):
        """测试逐条保存元数据会产生多次 SELECT 查询（对照组，说明 N+1）"""
        from sqlalchemy import event

        books = [
            Book(
                id='9780000002001',
                title=f'Loop Book {i}',
                author=f'Author {i}',
                publisher='Publisher',
                cover='',
                list_name='Test',
                category_id='hardcover-fiction',
                category_name='精装小说',
                rank=i,
                weeks_on_list=1,
                rank_last_week='0',
                published_date='2024-01-01',
                description='desc',
                details='details',
                publication_dt='2024-01-01',
                page_count='200',
                language='English',
                buy_links=[],
                isbn13=f'978000000200{i}',
                isbn10=f'000000200{i}',
                price='19.99',
            )
            for i in range(1, 6)
        ]

        select_count = 0

        def _count_selects(conn, cursor, statement, parameters, context, executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith('SELECT'):
                select_count += 1

        with app.app_context():
            event.listen(db.engine, 'before_cursor_execute', _count_selects)
            try:
                for book in books:
                    book_service.save_book_metadata(book)
            finally:
                event.remove(db.engine, 'before_cursor_execute', _count_selects)

        assert select_count == 5  # 每本书一次 SELECT


def test_nyt_ranking_sync_task_refreshes_all_categories(app, db):
    """测试后台NYT任务会触发全分类刷新和语言包写入"""
    from app.setup import _nyt_ranking_sync_task

    book_service = Mock()
    translator = Mock()
    book_service.sync_all_categories.return_value = [
        {
            'success': True,
            'books': 2,
            'metadata_saved': 2,
            'language_pack': {'fields_translated': 4},
        }
    ]
    original_book_service = app.extensions.get('book_service')
    original_translation_service = app.extensions.get('translation_service')

    try:
        app.extensions['book_service'] = book_service
        app.extensions['translation_service'] = translator

        with app.app_context():
            _nyt_ranking_sync_task(app)

            book_service.sync_all_categories.assert_called_once_with(
                force_refresh=True,
                translate=True,
                translator=translator,
            )
            assert SystemConfig.get_value('last_nyt_ranking_sync_time') is not None
    finally:
        if original_book_service is not None:
            app.extensions['book_service'] = original_book_service
        else:
            app.extensions.pop('book_service', None)
        if original_translation_service is not None:
            app.extensions['translation_service'] = original_translation_service
        else:
            app.extensions.pop('translation_service', None)
