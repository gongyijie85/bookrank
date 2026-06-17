"""收藏 API 路由测试"""

import json

import pytest


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
