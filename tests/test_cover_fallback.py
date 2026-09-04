"""Cover fallback regression (async prefetch #178 follow-up)."""

from app.models.book import Book


def _book_with_original():
    b = Book.from_api_response(
        book_data={
            'rank': 1,
            'title': 'T',
            'author': 'A',
            'primary_isbn13': '9780593798638',
            'book_image': 'https://static01.nyt.com/x.jpg',
        },
        category_id='hardcover-fiction',
        category_name='Fiction',
        list_name='List',
        published_date='2026-01-01',
        supplement={},
    )
    b._original_cover = 'https://static01.nyt.com/x.jpg'
    b.cover = ''  # 异步未就绪 -> cover 为空
    return b


def test_to_dict_exposes_original_cover():
    d = _book_with_original().to_dict()
    assert d['_original_cover'] == 'https://static01.nyt.com/x.jpg'
    assert d['cover'] == ''
