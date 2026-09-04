import pytest

from app.models.database import db
from app.models.new_book import NewBook

pytestmark = pytest.mark.usefixtures('app')


def _seed_book(publisher, title, author, isbn, publication_dt=None):
    book = NewBook(
        publisher_id=publisher.id,
        title=title,
        author=author,
        isbn13=isbn,
        publication_date=publication_dt,
        is_displayable=True,
        is_verified=False,
    )
    db.session.add(book)
    return book


def test_self_category_books_parallel_returns_all(tmp_path, app, client):
    from app.routes.api.books import self_category_books_parallel

    class _FakeService:
        def get_books_by_category(self, cat_id):
            from app.models.book import Book

            b = Book.from_api_response(
                book_data={
                    'rank': 1,
                    'title': f'book-{cat_id}',
                    'author': 'author',
                    'primary_isbn13': '9780593798638',
                    'book_image': '',
                },
                category_id=cat_id,
                category_name=cat_id,
                list_name='List',
                published_date='2026-01-01',
                supplement={},
            )
            return [b]

    service = _FakeService()
    cats = ['hardcover-fiction', 'trade-fiction-paperback', 'hardcover-nonfiction', 'advice-how-to-and-miscellaneous']
    result = self_category_books_parallel(service, cats)
    assert set(result.keys()) == set(cats)
    assert all(len(v) == 1 for v in result.values())


def test_self_category_books_parallel_degrades(tmp_path, app):
    from app.routes.api.books import self_category_books_parallel

    class _BoomService:
        def get_books_by_category(self, cat_id):
            if cat_id == 'boom':
                raise RuntimeError('boom')
            return []

    result = self_category_books_parallel(_BoomService(), ['boom', 'ok'])
    assert result['boom'] == []
    assert result['ok'] == []


def test_self_category_books_parallel_empty(app):
    from app.routes.api.books import self_category_books_parallel

    assert self_category_books_parallel(None, []) == {}
