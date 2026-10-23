"""真实 HTML 列表读取不应带未展示的长字段或逐行补查。"""

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app.models.new_book import NewBook, Publisher
from app.models.schemas import Award, AwardBook

MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148'


@contextmanager
def _queries(db):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        yield statements
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)


@pytest.mark.parametrize('ua', ['', MOBILE_UA])
@pytest.mark.parametrize(('locale', 'expected_title'), [('en', 'Card Title 0'), ('zh', '书目0')])
def test_award_html_list_omits_details_without_per_book_lazy_queries(app, db, ua, locale, expected_title):
    client = app.test_client()
    award = Award(name='Traffic Award', name_en='Traffic Award')
    db.session.add(award)
    db.session.flush()
    for index in range(3):
        db.session.add(
            AwardBook(
                award_id=award.id,
                year=2026,
                title=f'Card Title {index}',
                title_zh=f'书目{index}',
                author='Card Author',
                description='Card introduction',
                description_zh='卡片简介',
                details='Private detail payload ' * 100,
                buy_links='[]',
                is_displayable=True,
            )
        )
    db.session.commit()
    db.session.remove()
    with _queries(db) as statements:
        result = client.get(
            '/awards',
            query_string={'award': 'Traffic Award', 'year': '2026', 'lang': locale},
            headers={'User-Agent': ua},
        )
    assert result.status_code == 200
    html = result.get_data(as_text=True)
    assert 'Card Author' in html
    assert expected_title in html
    books = [sql for sql in statements if sql.lstrip().startswith('SELECT award_books.id AS')]
    assert len(books) == 1
    projection = books[0].split('FROM', 1)[0]
    assert 'award_books.details' not in projection
    assert 'award_books.buy_links' not in projection
    assert 'award_books.verification_errors' not in projection


@pytest.mark.parametrize('ua', ['', MOBILE_UA])
@pytest.mark.parametrize('locale', ['en', 'zh'])
def test_new_book_html_list_omits_source_payloads(app, db, ua, locale):
    client = app.test_client()
    publisher = Publisher(name='展示出版社', name_en='Card Publisher', crawler_class='TestCrawler')
    db.session.add(publisher)
    db.session.flush()
    db.session.add(
        NewBook(
            publisher_id=publisher.id,
            title='New Card Title',
            title_zh='新书卡片',
            author='New Card Author',
            publication_date=datetime.now(UTC).date(),
            description='Introduction',
            description_zh='简介',
            is_displayable=True,
            editions_json='[{"format":"hardcover"}]',
            field_provenance_json='[{"source":"large-source-document"}]',
            buy_links='[]',
        )
    )
    db.session.commit()
    db.session.remove()
    with _queries(db) as statements:
        result = client.get(f'/new-books?days=30&lang={locale}', headers={'User-Agent': ua})
    assert result.status_code == 200
    assert 'New Card Author' in result.get_data(as_text=True)
    books = [sql for sql in statements if sql.lstrip().startswith('SELECT new_books.id AS')]
    assert books
    for sql in books:
        projection = sql.split('FROM', 1)[0]
        assert 'new_books.editions_json' not in projection
        assert 'new_books.field_provenance_json' not in projection
        assert 'new_books.buy_links' not in projection
