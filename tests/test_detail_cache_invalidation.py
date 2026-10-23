"""Detail snapshots are invalidated only after their database writes commit."""

import pytest
from sqlalchemy import create_engine, delete, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.new_book import NewBook, Publisher
from app.models.schemas import Award, AwardBook, BookMetadata, TranslationCache, UserPreference
from app.services.book_detail_cache import cached_bestseller, cached_book
from app.services.detail_cache import DetailCache
from app.services.detail_cache_invalidation import init_detail_cache_invalidation
from app.services.recommendation_service import RecommendationService


@pytest.fixture
def detail_cache(app, db):
    init_detail_cache_invalidation()
    previous = app.extensions.get('book_detail_cache')
    cache = DetailCache(ttl=300, max_size=100)
    app.extensions['book_detail_cache'] = cache
    yield cache
    db.session.rollback()
    if previous is None:
        app.extensions.pop('book_detail_cache', None)
    else:
        app.extensions['book_detail_cache'] = previous


@pytest.fixture
def records(db, detail_cache):
    award = Award(name='Cache test award')
    publisher = Publisher(name='Cache test publisher', name_en='Cache test publisher', crawler_class='TestCrawler')
    db.session.add_all([award, publisher])
    db.session.flush()
    book = AwardBook(award_id=award.id, year=2026, title='Original title', author='Author', is_displayable=True)
    new_book = NewBook(publisher_id=publisher.id, title='Original new book', author='Author')
    metadata = BookMetadata(isbn='9780000000001', title='Original metadata', author='Author')
    translation = TranslationCache(
        source_hash='test-hash', source_text='Original', translated_text='Original translation'
    )
    db.session.add_all([book, new_book, metadata, translation])
    db.session.commit()
    return {
        'award': award,
        'award-book': book,
        'publisher': publisher,
        'new-book': new_book,
        'metadata': metadata,
        'translation': translation,
    }


def _seed(cache, records):
    keys = {
        'award': ('award', records['award-book'].id),
        'other-award': ('award', 99999),
        'new-book': ('new-book', records['new-book'].id),
        'other-new-book': ('new-book', 99999),
        'bestseller': ('bestseller', records['metadata'].isbn, 'source-hash'),
        'other-bestseller': ('bestseller', '9780000000002', 'source-hash'),
        'similarity': ('similarity', records['award-book'].id, None, None, None, 10),
        'other-similarity': ('similarity', 99999, None, None, None, 5),
    }
    for key in keys.values():
        cache.get_or_load(key, lambda: 'cached')
    return keys


def _assert_entries(cache, keys, invalidated=()):
    for name, key in keys.items():
        expected = 'fresh' if name in invalidated else 'cached'
        assert cache.get_or_load(key, lambda: 'fresh') == expected, name


@pytest.mark.parametrize('kind', ['award', 'new-book', 'bestseller', 'similarity'])
@pytest.mark.parametrize('flushed', [False, True])
@pytest.mark.parametrize('warm', [False, True])
def test_detail_reads_keep_uncommitted_values_out_of_shared_cache(db, detail_cache, records, kind, flushed, warm):
    record = records[
        {'award': 'award-book', 'new-book': 'new-book', 'bestseller': 'metadata', 'similarity': 'award-book'}[kind]
    ]
    record_id = record.isbn if kind == 'bestseller' else record.id
    committed_title = record.title

    def lookup():
        if kind in ('award', 'new-book'):
            model = AwardBook if kind == 'award' else NewBook
            return cached_book(kind, record_id, lambda: db.session.get(model, record_id)).title
        if kind == 'bestseller':

            def enrich(book, isbn):
                book['title'] = db.session.get(BookMetadata, isbn).title

            return cached_bestseller({'isbn13': record_id}, record_id, enrich, lambda *args: None)['title']
        return RecommendationService().get_similarity_recommendations(book_id=record_id)['reference_book']['title']

    if warm:
        assert lookup() == committed_title
    record.title = 'Uncommitted title'
    if flushed:
        db.session.flush()

    assert lookup() == 'Uncommitted title'
    db.session.rollback()

    assert lookup() == committed_title


@pytest.mark.parametrize('operation', ['metadata', 'isbn-change', 'translation', 'bulk'])
def test_book_details_api_cache_tracks_metadata_and_translation(db, detail_cache, records, operation):
    isbn = records['metadata'].isbn
    keys = [('book-api', isbn), ('book-api', '9780000000002')]
    for key in keys:
        detail_cache.get_or_load(key, lambda: 'cached')
    if operation == 'metadata':
        records['metadata'].details_zh = 'Updated'
    elif operation == 'isbn-change':
        records['metadata'].isbn = keys[1][1]
    elif operation == 'translation':
        records['translation'].translated_text = 'Updated'
    else:
        db.session.execute(update(BookMetadata).values(details_zh='Updated'))
    db.session.commit()
    assert detail_cache.get_or_load(keys[0], lambda: 'fresh') == 'fresh'
    expected = 'cached' if operation == 'metadata' else 'fresh'
    assert detail_cache.get_or_load(keys[1], lambda: 'fresh') == expected


@pytest.mark.parametrize('operation', ['update', 'delete', 'insert'])
def test_award_book_flush_waits_for_commit(db, detail_cache, records, operation):
    keys = _seed(detail_cache, records)
    if operation == 'update':
        records['award-book'].title = 'Changed'
        changed_key = 'award'
    elif operation == 'delete':
        db.session.delete(records['award-book'])
        changed_key = 'award'
    else:
        db.session.add(AwardBook(id=99999, award_id=records['award'].id, year=2025, title='Inserted', author='Author'))
        changed_key = 'other-award'
    db.session.flush()
    _assert_entries(detail_cache, keys)

    db.session.commit()

    _assert_entries(detail_cache, keys, {changed_key, 'similarity', 'other-similarity'})


@pytest.mark.parametrize(
    ('record', 'field', 'invalidated'),
    [
        ('award', 'name', {'award', 'other-award', 'similarity', 'other-similarity'}),
        ('new-book', 'title', {'new-book'}),
        ('publisher', 'name', {'new-book', 'other-new-book'}),
        ('metadata', 'title_zh', {'bestseller'}),
        ('translation', 'translated_text', {'new-book', 'other-new-book', 'bestseller', 'other-bestseller'}),
    ],
)
def test_model_dependencies_invalidate_only_matching_entries(db, detail_cache, records, record, field, invalidated):
    keys = _seed(detail_cache, records)
    setattr(records[record], field, 'Changed')
    db.session.commit()

    _assert_entries(detail_cache, keys, invalidated)


def test_rollback_discards_flushed_invalidations(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    records['award-book'].title = 'Rolled back'
    db.session.flush()
    db.session.rollback()
    db.session.commit()

    _assert_entries(detail_cache, keys)
    assert records['award-book'].title == 'Original title'


def test_failed_commit_does_not_invalidate_snapshots(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    records['award-book'].title = 'Uncommitted change'
    db.session.flush()
    db.session.add(Award(name=None))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    db.session.commit()

    _assert_entries(detail_cache, keys)


def test_metadata_isbn_change_invalidates_old_and_new_keys(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    records['metadata'].isbn = '9780000000002'
    db.session.commit()

    _assert_entries(detail_cache, keys, {'bestseller', 'other-bestseller'})


def test_savepoint_commit_waits_for_outer_commit(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    with db.session.begin_nested():
        records['award-book'].title = 'Savepoint commit'
        db.session.flush()
    _assert_entries(detail_cache, keys)

    db.session.commit()

    _assert_entries(detail_cache, keys, {'award', 'similarity', 'other-similarity'})


def test_savepoint_rollback_preserves_outer_invalidations(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    records['new-book'].title = 'Outer change'
    db.session.flush()
    savepoint = db.session.begin_nested()
    records['award-book'].title = 'Savepoint rollback'
    db.session.flush()
    savepoint.rollback()
    db.session.commit()

    _assert_entries(detail_cache, keys, {'new-book'})


def test_outer_rollback_discards_committed_savepoint_invalidations(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    with db.session.begin_nested():
        records['award-book'].title = 'Savepoint change'
        db.session.flush()
    db.session.rollback()
    db.session.commit()

    _assert_entries(detail_cache, keys)


@pytest.mark.parametrize(
    ('model', 'values', 'invalidated'),
    [
        (AwardBook, {'title': 'Bulk title'}, {'award', 'other-award', 'similarity', 'other-similarity'}),
        (Award, {'name': 'Bulk award'}, {'award', 'other-award', 'similarity', 'other-similarity'}),
        (NewBook, {'title': 'Bulk title'}, {'new-book', 'other-new-book'}),
        (Publisher, {'name': 'Bulk publisher'}, {'new-book', 'other-new-book'}),
        (BookMetadata, {'title': 'Bulk metadata'}, {'bestseller', 'other-bestseller'}),
        (
            TranslationCache,
            {'translated_text': 'Bulk translation'},
            {'new-book', 'other-new-book', 'bestseller', 'other-bestseller'},
        ),
    ],
)
def test_bulk_updates_wait_for_commit(db, detail_cache, records, model, values, invalidated):
    keys = _seed(detail_cache, records)
    db.session.execute(update(model).values(**values))
    _assert_entries(detail_cache, keys)
    db.session.commit()

    _assert_entries(detail_cache, keys, invalidated)


@pytest.mark.parametrize('operation', ['query-update', 'query-delete', 'execute-delete', 'execute-insert'])
def test_bulk_mutation_forms_are_observed(db, detail_cache, records, operation):
    keys = _seed(detail_cache, records)
    if operation == 'query-update':
        AwardBook.query.update({'title': 'Bulk changed'}, synchronize_session=False)
    elif operation == 'query-delete':
        AwardBook.query.delete(synchronize_session=False)
    elif operation == 'execute-delete':
        db.session.execute(delete(AwardBook))
    else:
        db.session.execute(
            insert(AwardBook).values(award_id=records['award'].id, year=2024, title='Bulk inserted', author='Author')
        )
    _assert_entries(detail_cache, keys)
    db.session.commit()

    _assert_entries(detail_cache, keys, {'award', 'other-award', 'similarity', 'other-similarity'})


def test_bulk_rollback_keeps_cached_snapshots(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    db.session.execute(update(AwardBook).values(title='Bulk rollback'))
    db.session.rollback()
    db.session.commit()

    _assert_entries(detail_cache, keys)


def test_bulk_savepoint_rollback_keeps_outer_invalidations(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    records['new-book'].title = 'Outer update'
    db.session.flush()
    savepoint = db.session.begin_nested()
    db.session.execute(update(AwardBook).values(title='Rolled back bulk write'))
    savepoint.rollback()
    db.session.commit()

    _assert_entries(detail_cache, keys, {'new-book'})


def test_core_bulk_write_starts_and_tracks_a_new_transaction(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    db.session.commit()
    assert db.session().get_transaction() is None

    db.session.execute(update(AwardBook.__table__).values(title='Core update'))
    _assert_entries(detail_cache, keys)
    db.session.commit()

    _assert_entries(detail_cache, keys, {'award', 'other-award', 'similarity', 'other-similarity'})


def test_unrelated_commit_keeps_cached_snapshots(db, detail_cache, records):
    keys = _seed(detail_cache, records)
    db.session.add(UserPreference(session_id='cache-test-user'))
    db.session.commit()

    _assert_entries(detail_cache, keys)


def test_missing_cache_extension_does_not_break_writes(app, db, detail_cache, records):
    app.extensions.pop('book_detail_cache')
    records['award-book'].title = 'No cache installed'
    db.session.commit()

    assert records['award-book'].title == 'No cache installed'
    assert 'book_detail_cache_invalidations' not in db.session.info


def test_session_outside_flask_context_does_not_track_invalidations():
    init_detail_cache_invalidation()
    engine = create_engine('sqlite:///:memory:')
    Award.__table__.create(engine)
    try:
        with Session(engine) as session:
            session.add(Award(name='Outside Flask'))
            session.commit()
            assert 'book_detail_cache_invalidations' not in session.info
    finally:
        engine.dispose()


def test_event_installation_is_idempotent(db, detail_cache, records, monkeypatch):
    init_detail_cache_invalidation()
    init_detail_cache_invalidation()
    _seed(detail_cache, records)
    invalidations = []
    original = detail_cache.invalidate

    def track(predicate):
        invalidations.append(predicate)
        original(predicate)

    monkeypatch.setattr(detail_cache, 'invalidate', track)
    records['award-book'].title = 'Changed once'
    db.session.commit()

    assert len(invalidations) == 1
