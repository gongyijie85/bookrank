"""封面热路径只读轻量路径，缺图异步补全且不污染写事务。"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import event

from app.models.schemas import Award, AwardBook
from app.services import award_cover_cache
from app.services.api_utils import ImageCacheService
from app.services.award_cover_cache import cached_award_cover
from app.services.cover_resolver import CoverResolver

ORIGINAL_COVER = 'https://books.google.com/books/content?id=cover-one'
UPDATED_COVER = 'https://books.google.com/books/content?id=cover-two'
IMAGE_BYTES = b'\xff\xd8\xff' + b'a' * 4096


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


@pytest.fixture
def cover_env(db, app, monkeypatch, tmp_path):
    cache_dir = tmp_path / 'images'
    image_cache = ImageCacheService(cache_dir)
    monkeypatch.setitem(app.config, 'IMAGE_CACHE_DIR', cache_dir)
    filename = hashlib.md5(ORIGINAL_COVER.encode(), usedforsecurity=False).hexdigest() + '.jpg'
    path = cache_dir / filename
    path.write_bytes(IMAGE_BYTES)
    award = Award(name='Cover Award', name_en='Cover Award')
    db.session.add(award)
    db.session.flush()
    book = AwardBook(
        award_id=award.id,
        year=2026,
        title='Cover Book',
        author='Cover Author',
        isbn13='9780143127550',
        cover_original_url=ORIGINAL_COVER,
        cover_local_path=f'/cache/images/{filename}',
        description='Long description ' * 100,
        details='Long detail ' * 100,
        buy_links='[]',
        is_displayable=True,
    )
    db.session.add(book)
    db.session.commit()
    book_id = book.id
    db.session.remove()
    tasks = []
    app.extensions.pop('award_cover_prefetch', None)
    monkeypatch.setattr('app.routes.main.submit_background_task', lambda fn, *args: tasks.append((fn, args)))
    with (
        patch('app.routes.main.get_service', return_value=image_cache),
        patch('app.routes.main.get_google_books_client', return_value=None),
    ):
        yield book_id, image_cache, path, tasks
    app.extensions.pop('award_cover_prefetch', None)
    image_cache._session.close()


def test_cold_cover_query_excludes_long_book_content(client, db, cover_env):
    book_id, _, _, tasks = cover_env
    with _selects(db) as statements:
        response = client.get(f'/award-book/{book_id}/cover')
    assert response.status_code == 200
    assert response.data == IMAGE_BYTES
    assert len(statements) == 1
    selected_columns = statements[0].split('FROM')[0].lower()
    for field in ('description', 'details', 'buy_links', 'verification_errors', 'title', 'isbn13'):
        assert field not in selected_columns
    assert 'award_books.id' in selected_columns
    assert 'award_books.cover_local_path' in selected_columns
    assert tasks == []


def test_warm_cover_is_zero_sql_and_ignores_return_to(client, db, cover_env):
    book_id, _, _, _ = cover_env
    first = client.get(f'/award-book/{book_id}/cover?return_to=/awards')
    with _selects(db) as statements:
        second = client.get(f'/award-book/{book_id}/cover?lang=en&return_to=/award-book/1')
    assert first.status_code == second.status_code == 200
    assert second.data == IMAGE_BYTES
    assert statements == []


def test_deleted_local_cover_queues_one_recovery_then_serves_download(client, db, cover_env):
    book_id, image_cache, path, tasks = cover_env
    image_cache.get_cached_image_url(ORIGINAL_COVER)
    assert client.get(f'/award-book/{book_id}/cover').status_code == 200
    path.unlink()
    with _selects(db) as statements, patch.object(CoverResolver, 'resolve') as resolve:
        response = client.get(f'/award-book/{book_id}/cover')
    assert response.status_code == 302
    assert response.location.endswith('/static/default-cover.png')
    assert response.headers['Cache-Control'] == 'no-store'
    resolve.assert_not_called()
    assert len(statements) == 1
    client.get(f'/award-book/{book_id}/cover')
    assert len(tasks) == 1

    def download(book, **kwargs):
        assert kwargs == {'persist': True, 'auto_commit': False}
        path.write_bytes(IMAGE_BYTES)
        return book.cover_local_path

    with patch.object(CoverResolver, 'resolve', side_effect=download) as resolve:
        tasks[0][0](*tasks[0][1])
    resolve.assert_called_once()
    assert client.get(f'/award-book/{book_id}/cover').data == IMAGE_BYTES
    with _selects(db) as warm:
        assert client.get(f'/award-book/{book_id}/cover').data == IMAGE_BYTES
    assert warm == []


def test_committed_cover_change_invalidates_cover_url_cache(client, db, cover_env):
    book_id, _, _, tasks = cover_env
    assert client.get(f'/award-book/{book_id}/cover').status_code == 200
    book = db.session.get(AwardBook, book_id)
    book.cover_local_path = None
    book.cover_original_url = UPDATED_COVER
    db.session.commit()
    db.session.remove()
    with _selects(db) as statements:
        response = client.get(f'/award-book/{book_id}/cover')
    assert response.status_code == 302
    assert response.location.endswith('/static/default-cover.png')
    assert len(statements) == 1
    assert len(tasks) == 1


@pytest.mark.parametrize('warm', [False, True])
@pytest.mark.parametrize('flushed', [False, True])
def test_uncommitted_cover_does_not_enter_shared_cache(db, cover_env, warm, flushed):
    book_id, _, path, _ = cover_env
    original_path = f'/cache/images/{path.name}'
    updated = path.with_name('b' * 32 + '.jpg')
    updated.write_bytes(IMAGE_BYTES)
    updated_path = f'/cache/images/{updated.name}'
    if warm:
        assert cached_award_cover(book_id) == original_path
    book = db.session.get(AwardBook, book_id)
    book.cover_local_path = updated_path
    if flushed:
        db.session.flush()
    assert cached_award_cover(book_id) == updated_path
    db.session.rollback()
    assert cached_award_cover(book_id) == original_path


def test_cover_read_does_not_flush_or_commit_other_pending_changes(db, cover_env):
    book_id, _, path, _ = cover_env
    book = db.session.get(AwardBook, book_id)
    book.title = 'Pending title'
    assert cached_award_cover(book_id) == f'/cache/images/{path.name}'
    assert book in db.session.dirty
    db.session.rollback()
    assert db.session.get(AwardBook, book_id).title == 'Cover Book'


def test_failed_background_resolution_keeps_original_and_retries(client, db, cover_env):
    book_id, _, path, tasks = cover_env
    path.unlink()
    first = client.get(f'/award-book/{book_id}/cover')
    with patch.object(CoverResolver, 'resolve', side_effect=RuntimeError('temporary')) as resolve:
        tasks[0][0](*tasks[0][1])
    assert db.session.get(AwardBook, book_id).cover_original_url == ORIGINAL_COVER
    second = client.get(f'/award-book/{book_id}/cover')
    assert first.status_code == second.status_code == 302
    assert first.location.endswith('/static/default-cover.png')
    assert second.location.endswith('/static/default-cover.png')
    assert first.headers['Cache-Control'] == second.headers['Cache-Control'] == 'no-store'
    resolve.assert_called_once()
    assert len(tasks) == 2


def test_missing_book_is_404_without_negative_cache(client, db):
    with _selects(db) as statements:
        first = client.get('/award-book/999999/cover')
        second = client.get('/award-book/999999/cover')
    assert first.status_code == second.status_code == 404
    assert len(statements) == 2


def test_concurrent_deleted_cover_observers_share_one_recovery(app, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'IMAGE_CACHE_DIR', tmp_path)
    cache = app.extensions['book_detail_cache']
    key = ('award-cover', 1)
    stale_url = '/cache/images/' + 'a' * 32 + '.jpg'
    cache.get_or_load(key, lambda: stale_url)
    get_or_load, invalidate_value = cache.get_or_load, cache.invalidate_value
    observed = Barrier(2)
    resolving, second_invalidated, release = Event(), Event(), Event()
    invalidations_lock = Lock()
    invalidations = 0

    def observe_stale(cache_key, loader):
        value = get_or_load(cache_key, loader)
        if value == stale_url:
            observed.wait(5)
        return value

    def expire_after_recovery_starts(cache_key, expected, **kwargs):
        nonlocal invalidations
        with invalidations_lock:
            invalidations += 1
            sequence = invalidations
        if sequence == 2:
            assert resolving.wait(5)
        result = invalidate_value(cache_key, expected, **kwargs)
        if sequence == 2:
            second_invalidated.set()
        return result

    def lookup():
        resolving.set()
        assert release.wait(5)
        return SimpleNamespace(cover_local_path=None)

    def request():
        with app.app_context():
            return cached_award_cover(1)

    with (
        patch('app.services.award_cover_cache.db') as fake_db,
        patch.object(cache, 'get_or_load', side_effect=observe_stale),
        patch.object(cache, 'invalidate_value', side_effect=expire_after_recovery_starts),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        fake_db.session.execute.return_value.scalar_one_or_none.side_effect = lookup
        requests = [pool.submit(request) for _ in range(2)]
        try:
            assert second_invalidated.wait(5)
        finally:
            release.set()
        assert [request.result(timeout=5) for request in requests] == [None, None]
        fake_db.session.execute.assert_called_once()


def test_old_missing_file_observation_keeps_same_url_after_file_recovers(app, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'IMAGE_CACHE_DIR', tmp_path)
    cache = app.extensions['book_detail_cache']
    cover_url = '/cache/images/' + 'a' * 32 + '.jpg'
    cache.get_or_load(('award-cover', 1), lambda: cover_url)
    missing_local_cover = award_cover_cache._missing_local_cover

    def recover_before_observer_reports(cover):
        missing = missing_local_cover(cover)
        if missing:
            (tmp_path / ('a' * 32 + '.jpg')).write_bytes(IMAGE_BYTES)
        return missing

    with (
        app.app_context(),
        patch('app.services.award_cover_cache._missing_local_cover', side_effect=recover_before_observer_reports),
        patch('app.services.award_cover_cache.db') as fake_db,
    ):
        assert cached_award_cover(1) == cover_url
        fake_db.session.execute.assert_not_called()
