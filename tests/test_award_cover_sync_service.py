from unittest.mock import MagicMock

from app.models.schemas import Award, AwardBook
from app.services.award_cover_sync_service import AwardCoverSyncService


class FakeGoogleBooksClient:
    def fetch_book_details(self, isbn):
        return {'cover_url': f'https://books.google.com/books/content?id={isbn}&img=1'}

    def search_book_by_title(self, title, author=None):
        return {}


class FakeOpenLibraryClient:
    def get_cover_url(self, isbn, size='L'):
        return None

    def get_cover_url_by_title(self, title, author=None, size='L'):
        return None


class FakeImageCache:
    def __init__(self):
        self.cached_urls = []

    def get_cached_image_url(self, original_url, ttl=3600):
        self.cached_urls.append((original_url, ttl))
        return '/cache/images/test-cover.jpg'


class DefaultOnlyImageCache:
    def get_cached_image_url(self, original_url, ttl=3600):
        return '/static/default-cover.png'


class TestShouldRefreshCoverSource:
    """测试 _should_refresh_cover_source 方法"""

    def setup_method(self):
        self.service = AwardCoverSyncService(
            google_client=MagicMock(),
            openlibrary_client=MagicMock(),
            image_cache=MagicMock(),
        )

    def test_ol_url_returns_true(self):
        url = 'https://covers.openlibrary.org/b/isbn/9780143127550-M.jpg'
        assert self.service._should_refresh_cover_source(url) is True

    def test_ol_url_id_returns_true(self):
        url = 'https://covers.openlibrary.org/b/id/14631041-L.jpg?default=false'
        assert self.service._should_refresh_cover_source(url) is True

    def test_google_url_returns_false(self):
        url = 'https://books.google.com/books/content?id=abc&img=1'
        assert self.service._should_refresh_cover_source(url) is False

    def test_arbitrary_url_returns_false(self):
        url = 'https://example.com/covers/image.jpg'
        assert self.service._should_refresh_cover_source(url) is False

    def test_empty_string_returns_false(self):
        assert self.service._should_refresh_cover_source('') is False


class TestIsCachedPathAvailable:
    """测试 _is_cached_path_available 方法"""

    def setup_method(self):
        self.service = AwardCoverSyncService(
            google_client=MagicMock(),
            openlibrary_client=MagicMock(),
            image_cache=MagicMock(),
        )

    def test_empty_path_returns_false(self):
        assert self.service._is_cached_path_available('') is False

    def test_whitespace_path_not_in_cache_dir_returns_true(self):
        assert self.service._is_cached_path_available('   ') is True

    def test_default_cover_path_returns_false(self):
        assert self.service._is_cached_path_available('/static/default-cover.png') is False

    def test_non_cache_path_returns_true(self):
        assert self.service._is_cached_path_available('/uploads/custom.jpg') is True

    def test_non_cache_relative_path_returns_true(self):
        assert self.service._is_cached_path_available('covers/photo.png') is True

    def test_cache_path_without_image_cache_returns_true(self):
        service = AwardCoverSyncService(
            google_client=MagicMock(),
            openlibrary_client=MagicMock(),
            image_cache=None,
        )
        assert service._is_cached_path_available('/cache/images/test.jpg') is True

    def test_cache_path_no_cache_dir_attribute_returns_true(self):
        cache = MagicMock(spec=[])
        service = AwardCoverSyncService(
            google_client=MagicMock(),
            openlibrary_client=MagicMock(),
            image_cache=cache,
        )
        assert service._is_cached_path_available('/cache/images/test.jpg') is True

    def test_cache_path_file_exists(self, tmp_path):
        cache_file = tmp_path / 'cover.jpg'
        cache_file.write_bytes(b'fake image')
        cache = MagicMock()
        cache._cache_dir = str(tmp_path)
        service = AwardCoverSyncService(
            google_client=MagicMock(),
            openlibrary_client=MagicMock(),
            image_cache=cache,
        )
        assert service._is_cached_path_available('/cache/images/cover.jpg') is True

    def test_cache_path_file_not_exists(self, tmp_path):
        cache = MagicMock()
        cache._cache_dir = str(tmp_path)
        service = AwardCoverSyncService(
            google_client=MagicMock(),
            openlibrary_client=MagicMock(),
            image_cache=cache,
        )
        assert service._is_cached_path_available('/cache/images/nonexistent.jpg') is False


class TestGetSyncStatus:
    """测试 get_sync_status 方法"""

    def test_no_books(self, app, db):
        with app.app_context():
            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            status = service.get_sync_status()
            assert status['total_books'] == 0
            assert status['has_cover'] == 0
            assert status['missing_cover'] == 0
            assert status['coverage_percent'] == 0
            assert status['is_syncing'] is False

    def test_with_books_all_have_cover(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Book With Cover',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url='https://example.com/cover.jpg',
                cover_local_path='/cache/images/cover.jpg',
            )
            db.session.add(book)
            db.session.commit()

            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            status = service.get_sync_status()
            assert status['total_books'] == 1
            assert status['has_cover'] == 1
            assert status['missing_cover'] == 0
            assert status['coverage_percent'] == 100.0

    def test_with_books_missing_cover(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book_no_cover = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Book Without Cover',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url=None,
                cover_local_path=None,
            )
            book_with_cover = AwardBook(
                award_id=award.id,
                year=2025,
                category='Nonfiction',
                rank=1,
                title='Book With Cover',
                author='Author B',
                isbn13='9780000000002',
                is_displayable=True,
                cover_original_url='https://example.com/cover.jpg',
                cover_local_path='/cache/images/cover.jpg',
            )
            db.session.add_all([book_no_cover, book_with_cover])
            db.session.commit()

            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            status = service.get_sync_status()
            assert status['total_books'] == 2
            assert status['has_cover'] == 1
            assert status['missing_cover'] == 1
            assert status['coverage_percent'] == 50.0

    def test_non_displayable_books_excluded(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Hidden Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=False,
                cover_original_url='https://example.com/cover.jpg',
            )
            db.session.add(book)
            db.session.commit()

            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            status = service.get_sync_status()
            assert status['total_books'] == 0
            assert status['has_cover'] == 0

    def test_is_syncing_flag(self, app, db):
        with app.app_context():
            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            assert service.get_sync_status()['is_syncing'] is False
            service._is_running = True
            assert service.get_sync_status()['is_syncing'] is True


class TestSyncMissingCovers:
    """测试 sync_missing_covers 方法"""

    def test_no_books_to_update(self, app, db):
        with app.app_context():
            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            result = service.sync_missing_covers(batch_size=10, delay=0)
            assert result['status'] == 'complete'
            assert result['total_checked'] == 0

    def test_concurrent_run_detection(self, app, db):
        with app.app_context():
            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            service._is_running = True
            result = service.sync_missing_covers()
            assert result['status'] == 'already_running'

    def test_concurrent_flag_reset_after_error(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Error Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url=None,
            )
            db.session.add(book)
            db.session.commit()

            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            service._cache_cover = MagicMock(side_effect=Exception('DB error'))
            service.sync_missing_covers(delay=0)
            assert service._is_running is False


class TestResolveCoverForBook:
    """测试 resolve_cover_for_book 方法"""

    def test_local_path_available(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Cached Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_local_path='/uploads/custom.jpg',
                cover_original_url='https://example.com/cover.jpg',
            )
            db.session.add(book)
            db.session.commit()

            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=MagicMock(),
            )
            result = service.resolve_cover_for_book(book)
            assert result == '/uploads/custom.jpg'

    def test_ol_url_cached_successfully(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='OL Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url='https://covers.openlibrary.org/b/isbn/9780000000001-M.jpg',
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            image_cache = FakeImageCache()
            service = AwardCoverSyncService(
                google_client=MagicMock(),
                openlibrary_client=MagicMock(),
                image_cache=image_cache,
            )
            result = service.resolve_cover_for_book(book)
            assert result == '/cache/images/test-cover.jpg'
            db.session.refresh(book)
            assert book.cover_local_path == '/cache/images/test-cover.jpg'

    def test_fetch_from_remote_when_no_url(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Remote Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url=None,
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            google_client = MagicMock()
            google_client.fetch_book_details.return_value = {
                'cover_url': 'https://books.google.com/books/content?id=9780000000001&img=1'
            }
            image_cache = FakeImageCache()
            service = AwardCoverSyncService(
                google_client=google_client,
                openlibrary_client=FakeOpenLibraryClient(),
                image_cache=image_cache,
            )
            result = service.resolve_cover_for_book(book)
            assert result == '/cache/images/test-cover.jpg'
            db.session.refresh(book)
            assert book.cover_original_url == 'https://books.google.com/books/content?id=9780000000001&img=1'
            assert book.cover_local_path == '/cache/images/test-cover.jpg'

    def test_no_persist_skips_commit(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='No Persist Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url=None,
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            google_client = MagicMock()
            google_client.fetch_book_details.return_value = {
                'cover_url': 'https://books.google.com/books/content?id=9780000000001&img=1'
            }
            service = AwardCoverSyncService(
                google_client=google_client,
                openlibrary_client=FakeOpenLibraryClient(),
                image_cache=FakeImageCache(),
            )
            result = service.resolve_cover_for_book(book, persist=False)
            assert result is not None
            db.session.refresh(book)
            assert book.cover_original_url is None

    def test_fallback_to_original_url_on_fetch_failure(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='desc', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Fallback Book',
                author='Author A',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url='https://example.com/fallback.jpg',
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            service = AwardCoverSyncService(
                google_client=None,
                openlibrary_client=FakeOpenLibraryClient(),
                image_cache=MagicMock(),
            )
            service._cache_cover = MagicMock(return_value=None)
            result = service.resolve_cover_for_book(book, persist=False)
            assert result == 'https://example.com/fallback.jpg'


class TestSyncMissingCoversWithBooks:
    """测试 sync_missing_covers 的书籍更新逻辑"""

    def test_updates_books_with_null_cover_fields(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='Test award', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Missing Cover',
                author='Author One',
                isbn13='9780143127550',
                is_displayable=True,
                cover_original_url=None,
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            image_cache = FakeImageCache()
            service = AwardCoverSyncService(
                FakeGoogleBooksClient(),
                openlibrary_client=FakeOpenLibraryClient(),
                image_cache=image_cache,
            )
            result = service.sync_missing_covers(batch_size=10, delay=0)

            db.session.refresh(book)
            assert result['total_checked'] == 1
            assert result['updated'] == 1
            assert book.cover_original_url == 'https://books.google.com/books/content?id=9780143127550&img=1'
            assert book.cover_local_path == '/cache/images/test-cover.jpg'
            assert image_cache.cached_urls == [(book.cover_original_url, 86400 * 365)]

    def test_replaces_uncacheable_openlibrary_source(self, app, db):
        with app.app_context():
            award = Award(name='Test Award', description='Test award', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='Open Library Placeholder',
                author='Author One',
                isbn13='9780143127550',
                is_displayable=True,
                cover_original_url='https://covers.openlibrary.org/b/isbn/9780143127550-M.jpg',
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            service = AwardCoverSyncService(
                FakeGoogleBooksClient(),
                openlibrary_client=FakeOpenLibraryClient(),
                image_cache=DefaultOnlyImageCache(),
            )
            result = service.sync_missing_covers(batch_size=10, delay=0)

            db.session.refresh(book)
            assert result['updated'] == 1
            assert book.cover_original_url == 'https://books.google.com/books/content?id=9780143127550&img=1'
            assert book.cover_local_path is None

    def test_uses_openlibrary_title_search_before_google(self, app, db):
        class TitleSearchOpenLibraryClient:
            def get_cover_url(self, isbn, size='L'):
                return None

            def get_cover_url_by_title(self, title, author=None, size='L'):
                return 'https://covers.openlibrary.org/b/id/14631041-L.jpg?default=false'

        google_client = FakeGoogleBooksClient()
        google_client.fetch_calls = 0

        def fetch_book_details(isbn):
            google_client.fetch_calls += 1
            return {'cover_url': f'https://books.google.com/books/content?id={isbn}&img=1'}

        google_client.fetch_book_details = fetch_book_details

        with app.app_context():
            award = Award(name='Test Award', description='Test award', country='US')
            db.session.add(award)
            db.session.flush()

            book = AwardBook(
                award_id=award.id,
                year=2025,
                category='Fiction',
                rank=1,
                title='The Safekeep',
                author='Yael van der Wouden',
                isbn13='9781668052541',
                is_displayable=True,
                cover_original_url=None,
                cover_local_path=None,
            )
            db.session.add(book)
            db.session.commit()

            image_cache = FakeImageCache()
            service = AwardCoverSyncService(
                google_client,
                openlibrary_client=TitleSearchOpenLibraryClient(),
                image_cache=image_cache,
            )
            result = service.sync_missing_covers(batch_size=10, delay=0)

            db.session.refresh(book)
            assert result['updated'] == 1
            assert google_client.fetch_calls == 0
            assert book.cover_original_url == 'https://covers.openlibrary.org/b/id/14631041-L.jpg?default=false'
            assert book.cover_local_path == '/cache/images/test-cover.jpg'
