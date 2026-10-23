"""HTML 书列只读展示列，塑形和完整模板渲染不得把详情逐行读回来。"""

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from flask import render_template
from sqlalchemy import event, inspect

from app.models.new_book import NewBook, Publisher
from app.models.schemas import Award, AwardBook
from app.services.award_book_service import AwardBookService
from app.services.book_language_pack import BookLanguagePack
from app.services.new_book.query_service import NewBookQueryService
from app.services.new_book.translation_pipeline import TranslationPipeline


@contextmanager
def _selects(db):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        yield statements
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)


@pytest.fixture
def list_books(db):
    publisher = Publisher(
        name='测试出版社', name_en='Test Publisher', crawler_class='TestCrawler', site_display_primary=True
    )
    award = Award(name='测试奖', name_en='Test Award')
    db.session.add_all([publisher, award])
    db.session.flush()
    for index in range(3):
        db.session.add(
            AwardBook(
                award_id=award.id,
                year=2026,
                category='Novel',
                rank=index + 1,
                title=f'Test Award Book {index}',
                title_zh=f'测试获奖书 {index}',
                author='Test Author',
                description='Award card description',
                description_zh='获奖书卡简介',
                isbn13=f'97800000001{index:02d}',
                publisher='Test Publisher',
                publication_year=2026,
                details='DETAIL BODY ' * 2000,
                buy_links='[{"url": "https://example.com/buy"}]',
                verification_errors='AUDIT RECORD ' * 2000,
                is_displayable=True,
            )
        )
        db.session.add(
            NewBook(
                publisher_id=publisher.id,
                title=f'Test New Book {index}',
                title_zh=f'测试新书 {index}',
                author='Test Author',
                description='New book card description',
                description_zh='新书卡片简介',
                isbn13=f'97800000002{index:02d}',
                publication_date=datetime.now(UTC).date(),
                category='Fiction',
                language='en',
                price='20',
                buy_links='[{"url": "https://example.com/buy"}]',
                source_url='https://example.com/source',
                canonical_source_url='https://example.com/canonical',
                editions_json='[{"format": "Hardcover"}]',
                field_provenance_json='[{"field": "title", "source": "publisher"}]',
                last_import_batch_id='import-test',
                is_displayable=True,
            )
        )
    db.session.commit()
    db.session.expunge_all()


def _award_books(app, search, list_only):
    service = AwardBookService(app)
    options = {'list_only': True} if list_only else {}
    if search:
        return service.search_award_books('Test', **options)
    return service.get_award_books(include_displayable_only=True, **options)


def _new_books(search, list_only):
    service = NewBookQueryService(TranslationPipeline(None, BookLanguagePack()))
    options = {'list_only': True} if list_only else {}
    if search:
        return service.search_books('Test', **options)
    return service.get_new_books(**options)


@pytest.mark.parametrize('search', [False, True])
@pytest.mark.parametrize('template', ['awards.html', 'mobile/awards.html'])
def test_award_list_projection_survives_shaping_and_render(app, db, list_books, search, template):
    from app.routes.main import _shape_award_book

    with app.test_request_context('/awards?lang=zh'):
        app.preprocess_request()
        with _selects(db) as statements:
            books, total = _award_books(app, search, list_only=True)
            shaped = [_shape_award_book(book) for book in books]
            html = render_template(
                template,
                books=shaped,
                awards=[books[0].award],
                years=[2026],
                categories=['Novel'],
                total_books=total,
                selected_award='',
                selected_year=2026,
                selected_category='',
                search_query='',
                award_sections=[{'award': books[0].award, 'books': shaped}],
                page=1,
                total_pages=1,
                has_prev=False,
                has_next=False,
            )
        assert total == 3
        assert 'Test Author' in html
        assert '测试获奖书 0' in html
        assert len(statements) == 3, statements
        row_sql = next(sql for sql in statements if sql.startswith('SELECT award_books.id')).split('FROM')[0]
        for column in ('details', 'buy_links', 'verification_errors', 'verification_checked_at'):
            assert f'award_books.{column}' not in row_sql
            assert column in inspect(books[0]).unloaded


@pytest.mark.parametrize('search', [False, True])
@pytest.mark.parametrize('template', ['new_books.html', 'mobile/new_books.html'])
def test_new_book_list_projection_survives_hydration_and_render(app, db, list_books, search, template):
    with app.test_request_context('/new-books?lang=zh'):
        app.preprocess_request()
        with _selects(db) as statements:
            books, total = _new_books(search, list_only=True)
            publisher = books[0].publisher
            html = render_template(
                template,
                books=books,
                publishers=[publisher],
                publisher_sections=[{'publisher': publisher, 'books': books}],
                publisher_book_counts={publisher.id: total},
                publisher_kind={publisher.id: 'publisher'},
                categories=[{'name': 'Fiction', 'count': total}],
                stats={'total_books': total, 'active_publishers': 1},
                total=total,
                selected_publisher=None,
                selected_category='Fiction',
                selected_days=30,
                search_query='',
                page=1,
                per_page=20,
                total_pages=1,
                future_preview_days=14,
                category_alias_labels={},
                publisher_labels={},
            )
        assert total == 3
        assert 'Test Author' in html
        assert '测试新书 0' in html
        # 1 列表（join 出版社）+ 1 count + 1 批量语言包查询；模板不再回源。
        assert len(statements) == 3, statements
        row_sql = next(sql for sql in statements if sql.startswith('SELECT new_books.id')).split('FROM')[0]
        for column in ('buy_links', 'editions_json', 'field_provenance_json', 'last_import_batch_id'):
            assert f'new_books.{column}' not in row_sql
            assert column in inspect(books[0]).unloaded
        assert 'publishers_1.last_error_summary' not in row_sql
        assert 'publishers_1.crawler_class' not in row_sql
        if template.startswith('mobile/'):
            assert '新书卡片简介' in html


@pytest.mark.parametrize('search', [False, True])
def test_default_award_query_preserves_full_data_contract(app, db, list_books, search):
    with _selects(db) as statements:
        books, total = _award_books(app, search, list_only=False)
        assert total == 3
        for book in books:
            assert book.details.startswith('DETAIL BODY')
            assert book.verification_errors.startswith('AUDIT RECORD')
            assert 'example.com/buy' in book.buy_links
            assert book.to_dict()['title_zh'].startswith('测试获奖书')
    assert len(statements) == 3


@pytest.mark.parametrize('search', [False, True])
def test_default_new_book_query_preserves_export_contract(app, db, list_books, search):
    with _selects(db) as statements:
        books, total = _new_books(search, list_only=False)
        assert total == 3
        for book in books:
            data = book.to_dict()
            assert data['editions'] == [{'format': 'Hardcover'}]
            assert data['field_provenance'] == [{'field': 'title', 'source': 'publisher'}]
            assert data['buy_links'][0]['url'] == 'https://example.com/buy'
            assert data['canonical_source_url'] == 'https://example.com/canonical'
    assert len(statements) == 3
