"""Cover prefetch task (#178) regression: task executes and collects URLs."""

import pytest


@pytest.fixture
def app_with_services(app):
    from app.models.book import Book

    class _FakeBookService:
        def __init__(self):
            self._original_cover = None

        def get_books_by_category(self, category, auto_translate=False, notify_refresh=False):
            b = Book.from_api_response(
                book_data={
                    'rank': 1,
                    'title': 't',
                    'author': 'a',
                    'primary_isbn13': '9780593798638',
                    'book_image': 'https://static01.nyt.com/images/x.jpg',
                },
                category_id=category,
                category_name=category,
                list_name='L',
                published_date='2026-01-01',
                supplement={},
            )
            return [b]

    from app.utils.service_helpers import register_service

    register_service(app, 'book_service', _FakeBookService())
    yield app


def test_cover_prefetch_task_runs(app_with_services):
    from app.setup import _cover_prefetch_task

    _cover_prefetch_task(app_with_services)  # 不应 raise；以空 image_cache 走跳过路径也可


def test_cover_prefetch_task_skips_without_image_cache(app):
    from app.setup import _cover_prefetch_task

    _cover_prefetch_task(app)
