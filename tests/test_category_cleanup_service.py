"""Category cleanup service tests (was 0% coverage)."""

import pytest

from app.models.database import db
from app.models.new_book import NewBook, Publisher
from app.services.category_cleanup_service import apply_cleanup, scan


@pytest.fixture
def publisher_with_books(app, db):
    with app.app_context():
        pub = Publisher(
            name='测试出版社',
            name_en='Test Pub',
            crawler_class='DummyCrawler',
            is_active=True,
        )
        db.session.add(pub)
        db.session.commit()
        yield pub
        db.session.remove()


def _add_book(publisher, title, category):
    book = NewBook(
        publisher_id=publisher.id,
        title=title,
        author='Author',
        isbn13='9780000000001',
        category=category,
        is_displayable=True,
        is_verified=False,
    )
    db.session.add(book)
    return book


def test_scan_identifies_invalid(app, db, publisher_with_books):
    with app.app_context():
        db.session.add(
            NewBook(
                publisher_id=publisher_with_books.id,
                title='A',
                author='A',
                isbn13='9780000000002',
                category='Fiction',
                is_displayable=True,
                is_verified=False,
            )
        )
        db.session.commit()
        result = scan()
        assert result.total_checked == 1
        assert len(result.invalid) == 1
        assert result.invalid[0].new_category == '小说'


def test_scan_clean_category_no_invalid(app, db, publisher_with_books):
    with app.app_context():
        _add_book(publisher_with_books, 'Clean', 'Adventure')
        db.session.commit()
        result = scan()
        assert result.invalid == []


def test_apply_dry_run_no_write(app, db, publisher_with_books):
    with app.app_context():
        _add_book(publisher_with_books, 'B', 'Fiction')
        db.session.commit()
        result = apply_cleanup(dry_run=True)
        assert result.invalid_found == 1
        assert result.updated == 0
        # 未写入
        book = NewBook.query.filter_by(title='B').first()
        assert book.category == 'Fiction'


def test_apply_writes(app, db, publisher_with_books):
    with app.app_context():
        _add_book(publisher_with_books, 'C', 'Fiction')
        db.session.commit()
        result = apply_cleanup(dry_run=False)
        assert result.updated == 1
        book = NewBook.query.filter_by(title='C').first()
        assert book.category == '小说'
