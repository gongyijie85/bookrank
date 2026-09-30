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
