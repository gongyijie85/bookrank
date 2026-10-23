"""Compression negotiation and cache policy regressions without upstream services."""

import gzip

import pytest
from flask import Flask, Response, request

from app import _apply_security_headers


@pytest.fixture
def response_client():
    app = Flask(__name__, static_folder=None)
    _apply_security_headers(app)

    @app.route('/payload', methods=['GET', 'HEAD'])
    def payload():
        response = Response('response body ' * 200, mimetype=request.args.get('type', 'text/plain'))
        response.status_code = int(request.args.get('status', 200))
        response.headers['Vary'] = 'Origin, Cookie'
        if request.args.get('multi_vary'):
            response.headers.add('Vary', 'Accept-Language')
        if request.args.get('conditional'):
            response.set_etag('payload-version')
            response.make_conditional(request)
        if request.args.get('encoded'):
            response.headers['Content-Encoding'] = 'br'
        if request.args.get('range'):
            response.headers['Content-Range'] = 'bytes 0-2799/5600'
        if request.args.get('no_transform'):
            response.headers['Cache-Control'] = 'public, no-transform'
        return response

    @app.route('/static/<path:filename>')
    def static_file(filename):
        return Response('missing', status=404)

    return app.test_client()


@pytest.mark.parametrize('encoding', ['gzip;q=0', 'br, gzip;q=0', 'xgzip', 'gzip;q=0, *;q=1'])
def test_gzip_rejection_is_respected(response_client, encoding):
    response = response_client.get('/payload', headers={'Accept-Encoding': encoding})
    assert 'Content-Encoding' not in response.headers
    assert response.vary == {'Origin', 'Cookie', 'Accept-Encoding'}


@pytest.mark.parametrize('encoding', ['gzip', 'gzip;q=0.5', '*;q=1'])
def test_compression_preserves_vary_and_correct_length(response_client, encoding):
    response = response_client.get('/payload', headers={'Accept-Encoding': encoding})
    assert response.headers['Content-Encoding'] == 'gzip'
    assert gzip.decompress(response.data) == b'response body ' * 200
    assert int(response.headers['Content-Length']) == len(response.data)
    assert response.vary == {'Origin', 'Cookie', 'Accept-Encoding'}


@pytest.mark.parametrize('query', ['status=206', 'range=1', 'encoded=1', 'no_transform=1', 'type=image/jpeg'])
def test_compression_skips_ineligible_responses(response_client, query):
    response = response_client.get(f'/payload?{query}', headers={'Accept-Encoding': 'gzip'})
    assert response.headers.get('Content-Encoding') != 'gzip'


def test_head_does_not_compress_an_unsent_body(response_client):
    response = response_client.head('/payload', headers={'Accept-Encoding': 'gzip'})
    assert 'Content-Encoding' not in response.headers
    assert response.data == b''


@pytest.mark.parametrize('encoding', ['gzip', 'gzip;q=0'])
def test_compression_preserves_all_vary_field_lines(response_client, encoding):
    response = response_client.get('/payload?multi_vary=1', headers={'Accept-Encoding': encoding})
    assert response.vary == {'Origin', 'Cookie', 'Accept-Language', 'Accept-Encoding'}


@pytest.mark.parametrize('encoding', ['gzip', 'gzip;q=0'])
def test_conditional_response_keeps_compression_vary(response_client, encoding):
    first = response_client.get('/payload?conditional=1&multi_vary=1', headers={'Accept-Encoding': encoding})
    response = response_client.get(
        '/payload?conditional=1&multi_vary=1',
        headers={'Accept-Encoding': encoding, 'If-None-Match': first.headers['ETag']},
    )
    assert response.status_code == 304
    assert response.data == b''
    assert response.vary == first.vary == {'Origin', 'Cookie', 'Accept-Language', 'Accept-Encoding'}


def test_missing_fingerprinted_asset_is_not_long_cached(response_client):
    response = response_client.get('/static/dist/missing.12345678.min.js')
    assert response.status_code == 404
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('src', ['', 'https://example.invalid/cover.jpg'])
def test_placeholder_redirect_is_not_cached(client, src):
    response = client.get('/cover', query_string={'src': src})
    assert response.status_code == 302
    assert response.headers['Cache-Control'] == 'no-store'


def test_image_cache_success_and_missing_file_have_distinct_policies(client, tmp_path, monkeypatch):
    monkeypatch.setitem(client.application.config, 'IMAGE_CACHE_DIR', tmp_path)
    filename = 'a' * 32 + '.jpg'
    image_path = tmp_path / filename
    image_path.write_bytes(b'\xff\xd8\xff' + b'0' * 256)
    first = client.get(f'/cache/images/{filename}')
    assert first.status_code == 200
    assert first.cache_control.max_age == 604800
    first.close()
    image_path.unlink()
    missing = client.get(f'/cache/images/{filename}')
    assert missing.status_code == 404
    assert missing.cache_control.no_store
