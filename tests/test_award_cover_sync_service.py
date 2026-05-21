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


class FakeImageCache:
    def __init__(self):
        self.cached_urls = []

    def get_cached_image_url(self, original_url, ttl=3600):
        self.cached_urls.append((original_url, ttl))
        return '/cache/images/test-cover.jpg'


class DefaultOnlyImageCache:
    def get_cached_image_url(self, original_url, ttl=3600):
        return '/static/default-cover.png'


def test_sync_missing_covers_updates_books_with_null_cover_fields(db):
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


def test_sync_missing_covers_replaces_uncacheable_openlibrary_source(db):
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
