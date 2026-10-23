"""详情缓存必须省去真实 SQL，并保留每次请求的展示上下文。"""

from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import event

from app.models.new_book import NewBook, Publisher
from app.models.schemas import Award, AwardBook


@contextmanager
def _selects(db):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        yield statements
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)


def _award_books(db):
    award = Award(name='缓存奖', name_en='Cache Award')
    db.session.add(award)
    db.session.flush()
    books = [
        AwardBook(
            award_id=award.id,
            year=2026,
            title=title,
            title_zh=zh,
            author='Author',
            is_displayable=True,
            description='Description',
            description_zh='中文简介',
            details='Details',
            buy_links='[]',
        )
        for title, zh in [('Target Book', '目标书'), ('Related Book', '相关书')]
    ]
    db.session.add_all(books)
    db.session.commit()
    ids = [book.id for book in books]
    db.session.remove()
    return ids


def test_cached_award_preserves_author_honor_without_warm_sql(app, db):
    from app.services.book_detail_cache import cached_book
    from app.utils.book_labels import award_result_kind

    book_id, _ = _award_books(db)
    book = db.session.get(AwardBook, book_id)
    book.award.wikidata_id = 'Q37922'
    book.category = 'Winner'
    db.session.commit()
    db.session.remove()

    def load():
        return db.session.get(AwardBook, book_id)

    first = cached_book('award', book_id, load)
    assert award_result_kind(first.category, first.award.wikidata_id) == 'author_honor'
    db.session.remove()
    with _selects(db) as warm:
        second = cached_book('award', book_id, load)
        assert award_result_kind(second.category, second.award.wikidata_id) == 'author_honor'
    assert warm == []


def test_award_repeat_request_ignores_return_to_and_keeps_request_locale(client, app, db):
    book_id, related_id = _award_books(db)
    with _selects(db) as cold:
        first = client.get(f'/award-book/{book_id}?lang=zh&return_to=/awards')
    assert first.status_code == 200
    assert cold
    with _selects(db) as warm:
        second = client.get(
            f'/award-book/{book_id}',
            query_string={'lang': 'en', 'return_to': '/awards?year=2025'},
            headers={'Referer': 'http://localhost/awards?year=2026'},
        )
    assert second.status_code == 200
    assert b'Target Book' in second.data
    assert f'/award-book/{related_id}'.encode() in second.data
    assert 'window.location.href = "/awards?year=2025";' in second.get_data(as_text=True)
    assert warm == []


def test_award_update_refreshes_target_and_other_books_recommendations(client, app, db):
    target_id, related_id = _award_books(db)
    client.get(f'/award-book/{target_id}')
    related = db.session.get(AwardBook, related_id)
    related.title = 'Updated Related Book'
    db.session.commit()
    db.session.remove()
    result = client.get(f'/award-book/{target_id}?lang=en')
    assert b'Updated Related Book' in result.data
    target = db.session.get(AwardBook, target_id)
    target.is_displayable = False
    db.session.commit()
    db.session.remove()
    hidden = client.get(f'/award-book/{target_id}?lang=zh')
    assert hidden.status_code == 404
    assert b'Target Book' not in hidden.data


def test_new_book_repeat_request_has_no_sql_and_keeps_publisher_and_buy_links(client, app, db):
    publisher = Publisher(name='缓存出版社', name_en='Cache Publisher', crawler_class='TestCrawler')
    db.session.add(publisher)
    db.session.flush()
    book = NewBook(
        publisher_id=publisher.id,
        title='A New Book',
        title_zh='新书',
        author='Writer',
        description='English description',
        description_zh='中文简介',
        is_displayable=True,
        buy_links='[{"name":"Store","url":"https://example.com/book"}]',
    )
    db.session.add(book)
    db.session.commit()
    book_id = book.id
    db.session.remove()
    client.get(f'/new-book/{book_id}?lang=zh')
    with _selects(db) as warm:
        result = client.get(f'/new-book/{book_id}?lang=en&return_to=/new-books')
    assert result.status_code == 200
    assert b'Cache Publisher' in result.data
    assert b'https://example.com/book' in result.data
    assert warm == []


def test_bestseller_enrichment_is_reused_but_changed_source_is_fresh(client, app):
    book = {'title': 'Book One', 'isbn13': '9780143127550', 'author': 'Writer'}
    with (
        patch('app.routes.main._get_books_for_category', return_value=([book], None)),
        patch('app.routes.main.enrich_book_details') as enrich,
        patch('app.routes.main.merge_or_translate_book') as merge,
        patch('app.routes.main.render_adaptive', return_value='ok'),
    ):
        client.get('/book/0?category=hardcover-fiction&return_to=/')
        client.get('/book/0?category=hardcover-fiction&return_to=/book/0?return_to=/')
        assert enrich.call_count == merge.call_count == 1
        book['title'] = 'Updated source'
        client.get('/book/0?category=hardcover-fiction')
        assert enrich.call_count == merge.call_count == 2


def test_recommendation_candidate_select_omits_large_text_columns(client, app, db):
    target_id, _ = _award_books(db)
    with _selects(db) as statements:
        client.get(f'/award-book/{target_id}')
    candidates = [sql for sql in statements if 'award_books.id !=' in sql]
    assert len(candidates) == 1
    assert 'award_books.description' not in candidates[0]
    assert 'award_books.details' not in candidates[0]


def test_new_book_translation_is_queued_once_for_repeated_visits(client, app):
    book = NewBook(id=987, title='Untranslated Book', author='Writer', publisher=None)
    with (
        patch('app.routes.main.get_new_book_modules') as modules,
        patch('app.routes.main.get_service', return_value=object()),
        patch('app.routes.main.submit_background_task') as submit,
        patch('app.routes.main.render_adaptive', return_value='ok'),
    ):
        modules.return_value.query_service.get_book.return_value = book
        client.get('/new-book/987')
        client.get('/new-book/987?return_to=/new-books')
        assert submit.call_count == 1
