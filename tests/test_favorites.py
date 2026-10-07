"""收藏 API 路由测试"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def csrf_token(client):
    """获取CSRF令牌（返回可调用对象，每次调用获取新token）"""

    def _get_token():
        response = client.get('/api/csrf-token')
        data = response.get_json()
        return data['data']['csrf_token']

    return _get_token


def _set_session(client, session_id: str | None = None):
    with client.session_transaction() as sess:
        if session_id:
            sess['session_id'] = session_id
        else:
            sess.pop('session_id', None)


@pytest.mark.parametrize(
    'payload',
    [
        {'isbn': 'ABCDEFGHIJ'},
        {'isbn': '1234567890123'},
        {'isbn': 9780306406157},
        {'isbn': True},
        {'isbn': ['9780306406157']},
        {'isbn': {'value': '9780306406157'}},
        {'isbn': '978-0-306-40615-7'},
        {'isbn': '0 8044 2957  x'},
        ['9780306406157'],
        '9780306406157',
    ],
)
def test_favorite_invalid_payload_is_400_without_write_with_real_csrf(app, db, monkeypatch, payload):
    from app.models.schemas import UserFavorite

    client = app.test_client()
    _set_session(client, 'invalid-favorite-audit')
    monkeypatch.setitem(app.config, 'TESTING', False)
    token = client.get('/api/csrf-token').get_json()['data']['csrf_token']
    response = client.post('/api/favorites', json=payload, headers={'X-CSRF-Token': token})
    assert response.status_code == 400
    assert response.get_json()['success'] is False
    assert UserFavorite.query.count() == 0


@pytest.mark.parametrize(
    ('submitted', 'stored'),
    [
        (' 9780306406157 ', '9780306406157'),
        (' 080442957x ', '080442957x'),
        ('0 8044 2957 x', '0 8044 2957 x'),
    ],
)
def test_favorite_existing_formats_strip_only_and_are_idempotent(app, db, monkeypatch, submitted, stored):
    from app.models.schemas import UserFavorite

    client = app.test_client()
    _set_session(client, 'existing-format-favorite-audit')
    monkeypatch.setitem(app.config, 'TESTING', False)
    responses = []
    for value in (submitted, stored):
        token = client.get('/api/csrf-token').get_json()['data']['csrf_token']
        responses.append(client.post('/api/favorites', json={'isbn': value}, headers={'X-CSRF-Token': token}))
    assert [response.status_code for response in responses] == [201, 200]
    assert [response.get_json()['data']['isbn'] for response in responses] == [stored, stored]
    assert UserFavorite.query.filter_by(session_id='existing-format-favorite-audit', isbn=stored).count() == 1
    assert client.get(f'/api/favorites/check/{stored}').get_json()['data']['is_favorited'] is True
    token = client.get('/api/csrf-token').get_json()['data']['csrf_token']
    assert client.delete(f'/api/favorites/{stored}', headers={'X-CSRF-Token': token}).status_code == 200
    assert client.get(f'/api/favorites/check/{stored}').get_json()['data']['is_favorited'] is False
    assert UserFavorite.query.filter_by(session_id='existing-format-favorite-audit').count() == 0


@pytest.mark.parametrize('preexisting', [False, True])
def test_favorite_lowercase_x_keeps_check_delete_and_legacy_row_with_real_csrf(app, db, monkeypatch, preexisting):
    from app.models.schemas import UserFavorite

    isbn = '080442957x'
    sid = 'lowercase-favorite-audit'
    if preexisting:
        db.session.add(UserFavorite(session_id=sid, isbn=isbn))
        db.session.commit()
    client = app.test_client()
    _set_session(client, sid)
    monkeypatch.setitem(app.config, 'TESTING', False)
    token = client.get('/api/csrf-token').get_json()['data']['csrf_token']
    added = client.post('/api/favorites', json={'isbn': isbn}, headers={'X-CSRF-Token': token})
    assert added.status_code == (200 if preexisting else 201)
    assert added.get_json()['data']['isbn'] == isbn
    assert client.get(f'/api/favorites/check/{isbn}').get_json()['data']['is_favorited'] is True
    assert UserFavorite.query.filter_by(session_id=sid).count() == 1
    token = client.get('/api/csrf-token').get_json()['data']['csrf_token']
    removed = client.delete(f'/api/favorites/{isbn}', headers={'X-CSRF-Token': token})
    assert removed.status_code == 200
    assert client.get(f'/api/favorites/check/{isbn}').get_json()['data']['is_favorited'] is False
    assert UserFavorite.query.filter_by(session_id=sid).count() == 0


def test_favorite_write_keeps_single_use_csrf_and_signed_identity(app, db, monkeypatch):
    from app.models.schemas import UserFavorite

    client = app.test_client()
    _set_session(client, 'csrf-favorite-audit')
    client.set_cookie('session_id', 'forged-other-reader')
    monkeypatch.setitem(app.config, 'TESTING', False)
    payload = {'isbn': '9780306406157'}
    assert client.post('/api/favorites', json=payload).status_code == 403
    token = client.get('/api/csrf-token').get_json()['data']['csrf_token']
    headers = {'X-CSRF-Token': token}
    assert client.post('/api/favorites', json=payload, headers=headers).status_code == 201
    assert client.post('/api/favorites', json=payload, headers=headers).status_code == 403
    assert UserFavorite.query.filter_by(session_id='csrf-favorite-audit', isbn=payload['isbn']).count() == 1
    assert UserFavorite.query.filter_by(session_id='forged-other-reader').count() == 0


class TestGetFavorites:
    """GET /api/favorites"""

    def test_empty(self, client, db):
        _set_session(client, 'get-test')
        response = client.get('/api/favorites')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['favorites'] == []
        assert data['data']['total'] == 0

    def test_after_adding(self, client, db, csrf_token):
        _set_session(client, 'get-test2')
        client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': csrf_token()},
        )
        response = client.get('/api/favorites')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['total'] == 1
        assert data['data']['favorites'][0]['isbn'] == '9780063021426'


class TestAddFavorite:
    """POST /api/favorites"""

    def test_add(self, client, db, csrf_token):
        _set_session(client, 'add-test')
        response = client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': csrf_token()},
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['isbn'] == '9780063021426'

    def test_invalid_isbn(self, client, db, csrf_token):
        _set_session(client, 'add-invalid')
        response = client.post(
            '/api/favorites',
            data=json.dumps({'isbn': 'invalid'}),
            content_type='application/json',
            headers={'X-CSRF-Token': csrf_token()},
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'ISBN' in data['message']

    def test_duplicate(self, client, db, csrf_token):
        _set_session(client, 'add-dup')
        token1 = csrf_token()
        client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': token1},
        )
        token2 = csrf_token()
        response2 = client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': token2},
        )
        data2 = json.loads(response2.data)
        assert data2['success'] is True
        assert '收藏中' in data2['message']

    def test_no_session(self, client, db, csrf_token):
        _set_session(client, None)
        response = client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': csrf_token()},
        )
        data = json.loads(response.data)
        assert data['success'] is False


class TestRemoveFavorite:
    """DELETE /api/favorites/<isbn>"""

    def test_remove(self, client, db, csrf_token):
        _set_session(client, 'rm-test')
        client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': csrf_token()},
        )
        response = client.delete('/api/favorites/9780063021426', headers={'X-CSRF-Token': csrf_token()})
        data = json.loads(response.data)
        assert data['success'] is True

        check = client.get('/api/favorites')
        check_data = json.loads(check.data)
        assert check_data['data']['total'] == 0

    def test_not_found(self, client, db, csrf_token):
        _set_session(client, 'rm-notfound')
        response = client.delete('/api/favorites/9780000000000', headers={'X-CSRF-Token': csrf_token()})
        data = json.loads(response.data)
        assert data['success'] is False
        assert response.status_code == 404


class TestCheckFavorite:
    """GET /api/favorites/check/<isbn>"""

    def test_not_favorited(self, client, db):
        _set_session(client, 'chk-no')
        response = client.get('/api/favorites/check/9780063021426')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['is_favorited'] is False

    def test_favorited(self, client, db, csrf_token):
        _set_session(client, 'chk-yes')
        client.post(
            '/api/favorites',
            data=json.dumps({'isbn': '9780063021426'}),
            content_type='application/json',
            headers={'X-CSRF-Token': csrf_token()},
        )
        response = client.get('/api/favorites/check/9780063021426')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['is_favorited'] is True

    def test_no_session(self, client, db):
        _set_session(client, None)
        response = client.get('/api/favorites/check/9780063021426')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['is_favorited'] is False


def _fresh_client(app):
    """独立客户端，避免 session 级 client fixture 把签名会话串到别的用例。"""
    return app.test_client()


def _signed_session_id(client) -> str | None:
    with client.session_transaction() as sess:
        value = sess.get('session_id')
    return value or None


def _profile_context(client) -> dict:
    from flask import template_rendered

    captured: dict = {}

    def _capture(sender, template, context, **kwargs):
        if not str(template.name).endswith('profile.html'):
            return
        favorites = context.get('favorites') or []
        captured['session_id'] = context.get('session_id')
        captured['isbns'] = [item.get('isbn') for item in favorites]

    with template_rendered.connected_to(_capture, client.application):
        response = client.get('/profile')
    captured['status_code'] = response.status_code
    return captured


def _post_favorite(client, isbn: str, csrf_token: str | None = None):
    headers = {'X-CSRF-Token': csrf_token} if csrf_token else {}
    return client.post(
        '/api/favorites',
        data=json.dumps({'isbn': isbn}),
        content_type='application/json',
        headers=headers,
    )


class TestSignedSessionFavorites:
    """个人中心与收藏必须共用 Flask 签名 session_id，不能认明文 cookie。"""

    def test_profile_mints_unique_signed_session_when_absent(self, app, db):
        client_a = _fresh_client(app)
        client_b = _fresh_client(app)

        assert _profile_context(client_a)['status_code'] == 200
        assert _profile_context(client_b)['status_code'] == 200

        sid_a = _signed_session_id(client_a)
        sid_b = _signed_session_id(client_b)
        assert sid_a, 'profile did not establish Flask session session_id'
        assert sid_b, 'profile did not establish Flask session session_id'
        assert sid_a != sid_b
        assert sid_a != 'anonymous'
        assert sid_b != 'anonymous'

    def test_profile_reads_signed_favorites_and_ignores_forged_cookie(self, app, db):
        from app.services.user_service import UserService

        owner = 'signed-owner-id'
        attacker = 'attacker-cookie'
        owner_isbn = '9780143127550'
        attacker_isbn = '9780063021426'
        anonymous_isbn = '9781111111111'
        service = UserService()
        service.add_favorite(owner, owner_isbn)
        service.add_favorite(attacker, attacker_isbn)
        service.add_favorite('anonymous', anonymous_isbn)

        client = _fresh_client(app)
        with client.session_transaction() as sess:
            sess['session_id'] = owner
        client.set_cookie('session_id', attacker)

        captured = _profile_context(client)
        assert captured['status_code'] == 200
        assert _signed_session_id(client) == owner
        assert captured['session_id'] == owner
        assert captured['isbns'] == [owner_isbn]

    def test_forged_cookie_clients_get_isolated_signed_favorites(self, app, db):
        from app.services.user_service import UserService

        forged = 'forged-shared-cookie'
        forged_isbn = '9782222222222'
        anonymous_isbn = '9781111111111'
        isbn_a = '9780143127550'
        isbn_b = '9780063021426'
        service = UserService()
        service.add_favorite(forged, forged_isbn)
        service.add_favorite('anonymous', anonymous_isbn)

        client_a = _fresh_client(app)
        client_b = _fresh_client(app)
        client_a.set_cookie('session_id', forged)
        client_b.set_cookie('session_id', forged)

        first_a = _profile_context(client_a)
        first_b = _profile_context(client_b)
        assert first_a['status_code'] == 200
        assert first_b['status_code'] == 200
        sid_a = _signed_session_id(client_a)
        sid_b = _signed_session_id(client_b)
        assert sid_a and sid_a not in {forged, 'anonymous'}
        assert sid_b and sid_b not in {forged, 'anonymous'}
        assert sid_a != sid_b
        assert first_a['session_id'] == sid_a
        assert first_b['session_id'] == sid_b
        assert forged_isbn not in first_a['isbns']
        assert anonymous_isbn not in first_a['isbns']
        assert forged_isbn not in first_b['isbns']
        assert anonymous_isbn not in first_b['isbns']

        assert _post_favorite(client_a, isbn_a).status_code in (200, 201)
        assert _post_favorite(client_b, isbn_b).status_code in (200, 201)
        again_a = _profile_context(client_a)
        again_b = _profile_context(client_b)
        assert again_a['isbns'] == [isbn_a]
        assert again_b['isbns'] == [isbn_b]

    def test_profile_entry_enables_favorite_post(self, app, db):
        client = _fresh_client(app)
        assert _profile_context(client)['status_code'] == 200

        isbn = '9780143127550'
        created = _post_favorite(client, isbn)
        assert created.status_code in (200, 201), created.get_json()
        body = created.get_json()
        assert body['success'] is True
        assert body['data']['isbn'] == isbn

        duplicate = _post_favorite(client, isbn)
        assert duplicate.status_code == 200
        duplicate_body = duplicate.get_json()
        assert duplicate_body['success'] is True
        assert '收藏中' in duplicate_body['message']
        listed = client.get('/api/favorites')
        assert listed.status_code == 200
        payload = listed.get_json()['data']
        assert payload['total'] == 1
        assert payload['favorites'][0]['isbn'] == isbn

    def test_favorite_post_without_session_stays_400_after_csrf_token(self, app, db):
        client = _fresh_client(app)
        token_response = client.get('/api/csrf-token')
        assert token_response.status_code == 200
        token = token_response.get_json()['data']['csrf_token']

        response = _post_favorite(client, '9780143127550', csrf_token=token)
        assert response.status_code == 400
        body = response.get_json()
        assert body['success'] is False
        assert _signed_session_id(client) is None

        listing = client.get('/api/favorites')
        assert listing.status_code == 200
        assert listing.get_json()['data'] == {'favorites': [], 'total': 0}
        check = client.get('/api/favorites/check/9780143127550')
        assert check.status_code == 200
        assert check.get_json()['data'] == {'is_favorited': False}


class TestConcurrentFavoriteIdempotence:
    """同一 session/ISBN 并发插入撞上唯一约束时，只认已经落库的那一行。"""

    def test_post_unique_conflict_returns_existing_duplicate(self, app, db):
        from app.models.schemas import UserFavorite

        sid = 'concurrent-owner'
        other_sid = 'concurrent-other'
        isbn = '9780143127550'
        existing = UserFavorite(session_id=sid, isbn=isbn)
        other = UserFavorite(session_id=other_sid, isbn=isbn)
        db.session.add(existing)
        db.session.add(other)
        db.session.commit()
        db.session.refresh(existing)
        existing_id = existing.id

        client = _fresh_client(app)
        with client.session_transaction() as sess:
            sess['session_id'] = sid

        with patch('flask_sqlalchemy.query.Query.first', side_effect=[None, existing]):
            response = _post_favorite(client, isbn)

        assert response.status_code == 200
        body = response.get_json()
        assert body['success'] is True
        assert '收藏中' in body['message']
        assert body['data']['id'] == existing_id
        assert body['data']['session_id'] == sid
        assert body['data']['isbn'] == isbn
        matched = UserFavorite.query.filter_by(session_id=sid, isbn=isbn).all()
        assert len(matched) == 1
        assert matched[0].id == existing_id
        assert UserFavorite.query.filter_by(session_id=other_sid, isbn=isbn).count() == 1

    def test_unrelated_integrity_error_reraises_after_rollback(self, app, db):
        from app.models.schemas import UserFavorite
        from app.services.user_service import UserService

        sid = 'concurrent-missing'
        other_sid = 'concurrent-keeper'
        isbn = '9780063021426'
        other = UserFavorite(session_id=other_sid, isbn=isbn)
        db.session.add(other)
        db.session.commit()
        original_error = IntegrityError('unrelated insert', {}, Exception('unrelated'))
        service = UserService()

        with patch.object(db.session, 'commit', side_effect=original_error):
            with pytest.raises(IntegrityError) as caught:
                service.add_favorite(sid, isbn)

        assert caught.value is original_error
        assert service.check_favorite(sid, isbn) is False
        assert UserFavorite.query.filter_by(session_id=sid, isbn=isbn).count() == 0
        kept = UserFavorite.query.filter_by(session_id=other_sid, isbn=isbn).one()
        assert kept.id == other.id


@pytest.mark.parametrize('locale', ['zh', 'en'])
def test_profile_favorite_titles_resolve_award_new_and_unknown(app, db, locale):
    from unittest.mock import patch
    from urllib.parse import parse_qs, urlsplit

    from app.models.new_book import NewBook, Publisher
    from app.models.schemas import Award, AwardBook, BookMetadata, UserFavorite

    award = Award(name='Prize')
    pub = Publisher(name='House', name_en='House', crawler_class='HouseCrawler')
    db.session.add_all([award, pub])
    db.session.flush()
    award_book = AwardBook(
        award_id=award.id,
        year=2026,
        title='Award Title',
        title_zh='奖项书名',
        author='Award Author',
        isbn13='9780306406157',
        is_displayable=True,
    )
    new_book = NewBook(
        publisher_id=pub.id,
        title='New Title',
        title_zh='新书书名',
        author='New Author',
        isbn10='0132350882',
        isbn13='9780132350884',
        is_displayable=True,
        last_import_batch_id=None,
    )
    db.session.add_all(
        [
            award_book,
            new_book,
            BookMetadata(isbn='9780306406157', title='9780306406157', title_zh='', author=''),
            UserFavorite(session_id='profile-source', isbn='9780306406157'),
            UserFavorite(session_id='profile-source', isbn='0132350882'),
            UserFavorite(session_id='profile-source', isbn='9780596007973'),
        ]
    )
    db.session.commit()
    award_id, new_id = award_book.id, new_book.id
    captured = {}

    def _capture(_template, **context):
        captured.update(context)
        return 'captured'

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['session_id'] = 'profile-source'
    with patch('app.routes.main.render_adaptive', side_effect=_capture):
        response = client.get('/profile', query_string={'lang': locale})
    assert response.status_code == 200
    rows = {row['isbn']: row for row in captured['favorites']}
    award_row = rows['9780306406157']
    new_row = rows['0132350882']
    unknown = rows['9780596007973']
    allowed = {'isbn', 'title_en', 'title_zh', 'title', 'author', 'detail_url'}
    assert set(rows) == {'9780306406157', '0132350882', '9780596007973'}
    assert allowed <= set(award_row)
    assert allowed <= set(new_row)
    assert allowed <= set(unknown)
    zh = locale == 'zh'
    assert (award_row['title_en'], award_row['title_zh'], award_row['title'], award_row['author']) == (
        'Award Title',
        '奖项书名',
        '奖项书名' if zh else 'Award Title',
        'Award Author',
    )
    assert (new_row['title_en'], new_row['title_zh'], new_row['title'], new_row['author']) == (
        'New Title',
        '新书书名',
        '新书书名' if zh else 'New Title',
        'New Author',
    )
    assert (unknown['title_en'], unknown['title_zh'], unknown['title'], unknown['author']) == (
        '9780596007973',
        '',
        '9780596007973',
        '',
    )
    award_url, new_url, unknown_url = (
        urlsplit(award_row['detail_url']),
        urlsplit(new_row['detail_url']),
        urlsplit(unknown['detail_url']),
    )
    assert (award_url.path, new_url.path, unknown_url.path) == (
        f'/award-book/{award_id}',
        f'/new-book/{new_id}',
        '/',
    )
    award_q, new_q, unknown_q = parse_qs(award_url.query), parse_qs(new_url.query), parse_qs(unknown_url.query)
    assert award_q['lang'] == new_q['lang'] == unknown_q['lang'] == [locale]
    assert award_q['return_to'] == new_q['return_to'] == [f'/profile?lang={locale}']
    assert unknown_q['search'] == ['9780596007973']


def test_profile_favorites_selects_flat_for_one_then_twenty(app, db, monkeypatch):
    from sqlalchemy import event

    from app.models.schemas import BookMetadata, UserFavorite

    def _add(row):
        db.session.add(row)
        db.session.commit()
        db.session.expire_all()
        db.session.remove()

    for i in range(20):
        _add(BookMetadata(isbn=f'978100000{i:04d}', title=f'Title{i}', author=f'Author{i}', title_zh=f'书{i}'))
    _add(UserFavorite(session_id='profile-batch', isbn='9781000000000'))
    saved = tuple(db.session.query(BookMetadata.title, BookMetadata.author).order_by(BookMetadata.isbn).all())
    db.session.remove()
    box = {}

    def _capture(_template, **kwargs):
        box['favorites'] = kwargs['favorites']
        return 'captured'

    monkeypatch.setattr('app.routes.main.render_adaptive', _capture)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['session_id'] = 'profile-batch'

    def _measure():
        seen = []

        def _before(_conn, _cur, statement, _params, _ctx, _executemany):
            if statement.lstrip()[:6].upper() == 'SELECT':
                seen.append(1)

        event.listen(db.engine, 'before_cursor_execute', _before)
        try:
            status = client.get('/profile?lang=en').status_code
            length = len(box['favorites'])
        finally:
            event.remove(db.engine, 'before_cursor_execute', _before)
        return status, len(seen), length

    status_a, selects_a, length_a = _measure()
    assert db.session.query(UserFavorite.isbn).filter_by(session_id='profile-batch').count() == 1
    for i in range(1, 20):
        _add(UserFavorite(session_id='profile-batch', isbn=f'978100000{i:04d}'))
    status_b, selects_b, length_b = _measure()
    assert db.session.query(UserFavorite.isbn).filter_by(session_id='profile-batch').count() == 20
    again = tuple(db.session.query(BookMetadata.title, BookMetadata.author).order_by(BookMetadata.isbn).all())
    assert (status_a, status_b, length_a, length_b, again) == (200, 200, 1, 20, saved)
    assert 0 < selects_a <= 5 and selects_a == selects_b


@pytest.mark.parametrize('locale', ['en', 'zh'])
def test_profile_hides_undisplayable_sources_and_prefers_metadata(app, db, monkeypatch, locale):
    """Hidden award/new rows stay ISBN fallbacks; visible metadata wins the same ISBN."""
    from urllib.parse import parse_qs, urlsplit

    from app.models.new_book import NewBook, Publisher
    from app.models.schemas import Award, AwardBook, BookMetadata, UserFavorite

    hidden_award_isbn = '9780143127550'
    hidden_new_isbn = '9780063021426'
    shared_isbn = '9780306406157'
    sid = 'profile-hidden-display'

    award = Award(name='Visibility Prize')
    publisher = Publisher(
        name='Visible House',
        name_en='Visible House',
        crawler_class='VisibleHouseCrawler',
        is_active=True,
        site_display_primary=True,
    )
    db.session.add_all([award, publisher])
    db.session.flush()
    db.session.add_all(
        [
            AwardBook(
                award_id=award.id,
                year=2026,
                title='Hidden award',
                title_zh='隐藏奖项',
                author='Hidden Award Author',
                isbn13=hidden_award_isbn,
                is_displayable=False,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='Hidden new',
                title_zh='隐藏新书',
                author='Hidden New Author',
                isbn13=hidden_new_isbn,
                is_displayable=False,
                last_import_batch_id=None,
            ),
            AwardBook(
                award_id=award.id,
                year=2024,
                title='Visible Award',
                title_zh='可见奖项',
                author='Visible Award Author',
                isbn13=shared_isbn,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='Visible New',
                title_zh='可见新书',
                author='Visible New Author',
                isbn13=shared_isbn,
                is_displayable=True,
                last_import_batch_id=None,
            ),
            BookMetadata(
                isbn=shared_isbn,
                title='Metadata Title',
                title_zh='元数据书名',
                author='Metadata Author',
            ),
            UserFavorite(session_id=sid, isbn=hidden_award_isbn),
            UserFavorite(session_id=sid, isbn=hidden_new_isbn),
            UserFavorite(session_id=sid, isbn=shared_isbn),
        ]
    )
    db.session.commit()

    captured = {}

    def _capture(_template, **context):
        captured.update(context)
        return 'captured'

    monkeypatch.setattr('app.routes.main.render_adaptive', _capture)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['session_id'] = sid

    response = client.get('/profile', query_string={'lang': locale})
    assert response.status_code == 200
    rows = {row['isbn']: row for row in captured['favorites']}

    def _assert_isbn_homepage(row, isbn):
        assert (row['title_en'], row['title_zh'], row['title'], row['author']) == (
            isbn,
            '',
            isbn,
            '',
        )
        parsed = urlsplit(row['detail_url'])
        assert (parsed.scheme, parsed.netloc, parsed.path) == ('', '', '/')
        query = parse_qs(parsed.query)
        assert query['lang'] == [locale]
        assert query['search'] == [isbn]

    _assert_isbn_homepage(rows[hidden_award_isbn], hidden_award_isbn)
    _assert_isbn_homepage(rows[hidden_new_isbn], hidden_new_isbn)
    meta = rows[shared_isbn]
    assert (meta['title_en'], meta['title_zh'], meta['author']) == (
        'Metadata Title',
        '元数据书名',
        'Metadata Author',
    )
    assert meta['title'] == ('元数据书名' if locale == 'zh' else 'Metadata Title')
