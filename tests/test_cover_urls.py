"""封面地址规范化与同源封面代理（app/utils/cover_urls.py + /cover 路由）。

覆盖的是 #issue3：国内网络无法直连 storage.googleapis.com（NYT 榜单封面实际所在的
图床）、covers.openlibrary.org 等境外域名，且这些域名也不在 CSP `img-src` 白名单内，
封面因此一律退化成占位图。修复方式是把取图动作挪到服务端，浏览器只请求同源 /cover。

这些用例刻意钉住四件容易回归的事：
1. 已经是同源路径的值不会被二次包裹（否则 /cover?src=/cover?src=… 无限套娃）；
2. 非白名单域名不会被代理（代理的 src 由请求方控制，白名单是资源放大与 SSRF 的边界）；
3. CSP 放行的每个图床域名都必须同时出现在代理白名单里，否则浏览器能直连但代理会拒绝；
4. **白名单门与下载守卫必须一致**（`TestGateParity`）——两道门判据不同就会形成
   「过了白名单、被守卫静默拒掉」的死角，且拒绝发生在"提交后台预取"之前，
   表现是该封面**永久**显示占位图、日志里只有一行 warning。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from urllib.parse import quote

import pytest
import requests
from flask import Flask, has_app_context, has_request_context
from sqlalchemy import text
from sqlalchemy.pool import QueuePool

from app.models.schemas import Award, AwardBook
from app.services.api_cache_service import APICacheService
from app.services.api_utils import ImageCacheService, _is_safe_image_url
from app.services.google_books_client import GoogleBooksClient
from app.utils.cover_urls import (
    ALLOWED_COVER_HOSTS,
    COVER_PROXY_PATH,
    DEFAULT_COVER,
    cached_filename_from_path,
    cover_src,
    cover_src_or_default,
    is_allowed_cover_host,
    normalize_cover_url,
)

NYT_COVER = 'https://storage.googleapis.com/du-prd/books/images/9780593139134.jpg'
OL_COVER = 'https://covers.openlibrary.org/b/isbn/9780143127550-L.jpg?default=false'

#: Google Books API 的 `imageLinks.thumbnail` 默认就是这个 http:// 形态
#: （注意 `source=gbs_api`），线上实测这类封面全部永久退化成占位图。
GOOGLE_BOOKS_HTTP_COVER = (
    'http://books.google.com/books/content?id=6c6fEQAAQBAJ&printsec=frontcover&img=1&zoom=1&source=gbs_api'
)


class TestCoverSrc:
    def test_empty_returns_empty_string(self):
        """空值返回空串而不是默认封面：模板要靠它区分「没有原始地址」。"""
        assert cover_src('') == ''
        assert cover_src(None) == ''
        assert cover_src('   ') == ''

    def test_empty_falls_back_to_default_cover(self):
        assert cover_src_or_default('') == DEFAULT_COVER
        assert cover_src_or_default(None) == DEFAULT_COVER

    @pytest.mark.parametrize(
        'local_path',
        ['/static/default-cover.png', '/cache/images/' + 'a' * 32 + '.jpg', COVER_PROXY_PATH + '?src=x'],
    )
    def test_local_paths_pass_through(self, local_path):
        """同源路径原样返回，尤其是代理地址本身，避免二次包裹。"""
        assert cover_src(local_path) == local_path

    def test_external_url_is_proxied(self):
        assert cover_src(NYT_COVER) == f'{COVER_PROXY_PATH}?src={quote(NYT_COVER, safe="")}'

    def test_external_url_is_percent_encoded(self):
        """查询串里的 ? 与 = 必须编码，否则会截断 /cover 自身的 query。"""
        proxied = cover_src(OL_COVER)
        assert proxied.startswith(f'{COVER_PROXY_PATH}?src=')
        assert '?' not in proxied[len(f'{COVER_PROXY_PATH}?src=') :]
        assert OL_COVER not in proxied

    def test_http_external_url_is_upgraded_before_proxying(self):
        """http:// 封面必须在**进入代理参数之前**升级为 https。

        否则下发的 src 是 http://…，代理把它交给图片缓存，而缓存的下载守卫
        只允许 https —— 守卫会在"提交后台预取"之前返回占位图，这张封面就永久不显示了。
        """
        proxied = cover_src(GOOGLE_BOOKS_HTTP_COVER)
        assert proxied.startswith(f'{COVER_PROXY_PATH}?src=https%3A%2F%2Fbooks.google.com%2F')
        assert 'http%3A' not in proxied.replace('https%3A', '')


class TestNormalizeCoverUrl:
    """http → https 升级：Google Books 的 thumbnail 默认就是 http 形态。"""

    def test_upgrades_http_keeping_path_and_query(self):
        upgraded = normalize_cover_url(GOOGLE_BOOKS_HTTP_COVER)
        assert upgraded.startswith('https://books.google.com/books/content?')
        # 查询串里的 & 与 = 必须原样保留，否则 Google Books 会返回 400
        assert 'id=6c6fEQAAQBAJ' in upgraded
        assert 'source=gbs_api' in upgraded

    def test_https_is_untouched(self):
        assert normalize_cover_url(NYT_COVER) == NYT_COVER
        assert normalize_cover_url(OL_COVER) == OL_COVER

    @pytest.mark.parametrize('value', ['', '   ', None, '/static/default-cover.png', 'not-a-url'])
    def test_non_http_values_pass_through(self, value):
        """只做 scheme 升级，不猜、不补、不把非 URL 变成 URL。"""
        assert normalize_cover_url(value) in ('', '/static/default-cover.png', 'not-a-url')

    def test_idempotent(self):
        once = normalize_cover_url(GOOGLE_BOOKS_HTTP_COVER)
        assert normalize_cover_url(once) == once


class TestGateParity:
    """白名单门（cover_urls）与下载守卫（api_utils._is_safe_image_url）必须一致。

    历史 bug：白名单只看 hostname，下载守卫额外要求 `scheme == 'https'`。
    Google Books 返回的 `http://books.google.com/…&source=gbs_api` 因此**过了第一道门、
    被第二道门静默拒掉**，而且拒绝发生在提交后台预取之前 —— 线上实测这类封面
    反复请求也永远停在占位图（75 张抽样里 5 张，全部是 http 形态）。
    """

    @pytest.mark.parametrize('host', ALLOWED_COVER_HOSTS)
    def test_whitelisted_host_survives_the_download_guard(self, host):
        for url in (f'https://{host}/cover.jpg', f'http://{host}/cover.jpg'):
            assert is_allowed_cover_host(url) is True
            assert _is_safe_image_url(normalize_cover_url(url)) is True, (
                f'{url} 过了白名单却过不了下载守卫，该封面会永久退化成占位图'
            )

    def test_real_world_google_books_thumbnail(self):
        """线上抓到的真实卡住样本：http + source=gbs_api。"""
        assert is_allowed_cover_host(GOOGLE_BOOKS_HTTP_COVER) is True
        assert _is_safe_image_url(normalize_cover_url(GOOGLE_BOOKS_HTTP_COVER)) is True

    def test_guard_still_rejects_unsafe_targets(self):
        """升级 scheme 不能变成万能钥匙：内网/回环/link-local/非 443 端口仍须被守卫拦下。

        注意两道门的**分工**：`_is_safe_image_url` 只管 SSRF（scheme + 目标地址），
        主机白名单由 `is_allowed_cover_host` 负责。所以 `https://evil.example.com` 过守卫
        是**正确**的，它必须被白名单拦下 —— 把这条也钉住，免得日后有人把两道门合并。
        """
        for url in (
            'http://169.254.169.254/latest/meta-data/',
            'http://localhost/cover.jpg',
            'https://metadata.google.internal/x',
            'https://internal.internal/x.jpg',
            'https://example.com:8080/cover.jpg',
            'ftp://books.google.com/x.jpg',
        ):
            assert _is_safe_image_url(normalize_cover_url(url)) is False, url

        # 守卫放行但白名单必须拦住（资源放大 / 任意图片下载的边界）
        assert _is_safe_image_url('https://evil.example.com/cover.jpg') is True
        assert is_allowed_cover_host('https://evil.example.com/cover.jpg') is False


class TestAllowedCoverHost:
    @pytest.mark.parametrize(
        'url',
        [
            NYT_COVER,
            OL_COVER,
            'https://books.google.com/books/content?id=x',
            'https://books.googleusercontent.com/books/content?id=x',
            'https://images.penguinrandomhouse.com/cover/9780593139134',
            'https://static01.nyt.com/images/2024/01/01/books/cover.jpg',
        ],
    )
    def test_known_cover_hosts_allowed(self, url):
        assert is_allowed_cover_host(url) is True

    @pytest.mark.parametrize(
        'url',
        [
            'https://evil.example.com/cover.jpg',
            'https://internal.corp/cover.jpg',
            '',
            'not-a-url',
            # 后缀相似但主机不同：endswith('storage.googleapis.com') 式写法会在这里放行
            'https://evil-storage.googleapis.com/cover.jpg',
            'https://storage.googleapis.com.evil.example.com/cover.jpg',
        ],
    )
    def test_unknown_hosts_rejected(self, url):
        assert is_allowed_cover_host(url) is False

    def test_subdomain_of_allowed_host_is_allowed(self):
        assert is_allowed_cover_host('https://media.covers.openlibrary.org/x.jpg') is True


class TestCachedFilename:
    def test_extracts_filename(self):
        assert cached_filename_from_path('/cache/images/' + 'b' * 32 + '.jpg') == 'b' * 32 + '.jpg'

    @pytest.mark.parametrize(
        'path',
        ['', '/static/default-cover.png', '/cache/images/', '/cache/images/sub/dir.jpg', '/cache/images/../x.jpg'],
    )
    def test_rejects_non_cache_paths(self, path):
        assert cached_filename_from_path(path) is None


class _FakeImageCache:
    """按 URL 返回预设本地路径的假缓存，避免测试触发真实网络请求。"""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping
        self.calls: list[tuple[str, int, bool]] = []

    def get_cached_image_url(self, url: str, ttl: int = 3600, block: bool = True) -> str:
        self.calls.append((url, ttl, block))
        return self._mapping.get(url, DEFAULT_COVER)


@pytest.fixture
def cover_cache(app, tmp_path):
    """把 image_cache_service 与 IMAGE_CACHE_DIR 换成临时目录，测完还原。"""
    cache_dir = tmp_path / 'images'
    cache_dir.mkdir(parents=True, exist_ok=True)
    original_service = app.extensions.get('image_cache_service')
    original_dir = app.config.get('IMAGE_CACHE_DIR')
    app.config['IMAGE_CACHE_DIR'] = cache_dir
    try:
        yield cache_dir
    finally:
        if original_service is None:
            app.extensions.pop('image_cache_service', None)
        else:
            app.extensions['image_cache_service'] = original_service
        app.config['IMAGE_CACHE_DIR'] = original_dir


class TestCoverProxyRoute:
    def test_missing_src_redirects_to_default(self, client, cover_cache):
        resp = client.get('/cover')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(DEFAULT_COVER)

    def test_disallowed_host_redirects_to_default(self, client, cover_cache):
        app_cache = _FakeImageCache({})
        client.application.extensions['image_cache_service'] = app_cache
        resp = client.get('/cover', query_string={'src': 'https://evil.example.com/x.jpg'})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(DEFAULT_COVER)
        # 非白名单域名必须在触达缓存/网络之前就被拒绝
        assert app_cache.calls == []

    def test_cached_cover_is_served_inline(self, client, cover_cache):
        """命中本地缓存时直接下发图片字节，而不是再 302 一次。"""
        filename = 'c' * 32 + '.jpg'
        (cover_cache / filename).write_bytes(b'\xff\xd8\xff' + b'0' * 4096)
        client.application.extensions['image_cache_service'] = _FakeImageCache({NYT_COVER: f'/cache/images/{filename}'})

        resp = client.get('/cover', query_string={'src': NYT_COVER})

        assert resp.status_code == 200
        assert resp.mimetype == 'image/jpeg'
        assert len(resp.data) > 1024
        assert resp.headers['X-Cover-Source'] == 'cache'
        assert resp.headers['X-Cover-Path'] == f'/cache/images/{filename}'
        assert 'max-age' in resp.headers['Cache-Control']

    def test_download_failure_redirects_without_caching(self, client, cover_cache):
        """回源失败回落到默认封面，且不缓存失败结果（否则一次抖动会长期锁死）。"""
        client.application.extensions['image_cache_service'] = _FakeImageCache({})

        resp = client.get('/cover', query_string={'src': NYT_COVER})

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(DEFAULT_COVER)
        assert resp.headers['Cache-Control'] == 'no-store'

    def test_missing_cache_service_redirects_to_default(self, client, cover_cache):
        client.application.extensions.pop('image_cache_service', None)
        resp = client.get('/cover', query_string={'src': NYT_COVER})
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(DEFAULT_COVER)

    def test_request_path_never_blocks_on_upstream(self, client, cover_cache):
        """热路径必须 block=False，绝不能同步回源。

        这条不是性能优化而是可用性约束：本路由是列表页热路径（首页一屏 15 个封面），
        生产是 workers=1 / threads=2（多 worker 会绕过进程内限流器），同步回源在上游变慢时
        会 3 次 10s 重试占满全部线程，整站一起卡住。仓库约定见
        `app/setup.py:_cover_prefetch_task` 与 `book_service.py` 的 block=False。
        """
        app_cache = _FakeImageCache({NYT_COVER: f'/cache/images/{"d" * 32}.jpg'})
        client.application.extensions['image_cache_service'] = app_cache

        client.get('/cover', query_string={'src': NYT_COVER})

        assert app_cache.calls, '代理应查询图片缓存'
        assert app_cache.calls[0][2] is False, '热路径必须传 block=False'


@pytest.fixture
def award_cover_pipeline(app, db, cover_cache, monkeypatch):
    """真实路由/Resolver/图片缓存/源客户端，HTTP 边界合成且后台队列不执行。"""
    from app.routes import main

    assert app.config['TESTING'] and 'memory' in app.config['SQLALCHEMY_DATABASE_URI']
    award = Award(name='Synthetic Cover Award', name_en='Synthetic Cover Award')
    db.session.add(award)
    db.session.flush()
    book = AwardBook(
        award_id=award.id,
        year=2026,
        title='Synthetic Cover Book',
        author='Synthetic Author',
        isbn13='9780306406157',
        is_displayable=True,
    )
    db.session.add(book)
    db.session.commit()
    book_id = book.id
    image_cache = ImageCacheService(cover_cache)
    google = GoogleBooksClient(api_key=None, base_url='https://www.googleapis.com/books/v1/volumes')
    google._api_cache = APICacheService()
    monkeypatch.setitem(app.extensions, 'image_cache_service', image_cache)
    monkeypatch.setattr(main, 'get_google_books_client', lambda: google)
    jobs, trace = [], []
    capture_job = lambda job, *args: jobs.append((job, args))  # noqa: E731
    monkeypatch.setattr('app.utils.service_helpers.submit_background_task', capture_job)
    monkeypatch.setattr(main, 'submit_background_task', capture_job)
    app.extensions.pop('award_cover_prefetch', None)
    request_thread = threading.get_ident()

    def synthetic_http(session, method, url, **kwargs):
        query = (kwargs.get('params') or {}).get('q', '')
        trace.append(
            {
                'method': method.upper(),
                'url': url,
                'query': query,
                'in_request': has_request_context(),
                'request_thread': threading.get_ident() == request_thread,
                'db_transaction_active': db.session().in_transaction(),
            }
        )
        response = requests.Response()
        response.url = url
        response.status_code = 200
        if method.upper() == 'HEAD':
            response.status_code = 404
            payload = b''
        elif url == 'https://openlibrary.org/search.json':
            payload = json.dumps({'docs': []}).encode()
        elif url == google._base_url:
            # ISBN lookup misses; the final title lookup returns the synthetic source.
            data = (
                {'items': []}
                if query.startswith('isbn:')
                else {
                    'items': [
                        {
                            'volumeInfo': {
                                'title': 'Synthetic Cover Book',
                                'authors': ['Synthetic Author'],
                                'imageLinks': {'thumbnail': NYT_COVER},
                            },
                        }
                    ]
                }
            )
            payload = json.dumps(data).encode()
        elif url == NYT_COVER:
            payload = b'\xff\xd8\xff' + b'0' * 4096
            response.headers.update({'Content-Type': 'image/jpeg', 'Content-Length': str(len(payload))})
        else:
            raise AssertionError(f'Unexpected synthetic HTTP boundary: {method} {url}')
        response._content = payload
        response._content_consumed = True
        return response

    monkeypatch.setattr(requests.sessions.Session, 'request', synthetic_http)
    yield {
        'book': book,
        'book_id': book_id,
        'trace': trace,
        'jobs': jobs,
        'cache_dir': cover_cache,
        'image_cache': image_cache,
        'google': google,
    }
    image_cache._session.close()
    google._session.close()
    app.extensions.pop('award_cover_prefetch', None)


def _run_award_cover_job(job):
    """实际另起线程执行被捕获的任务，传播错误而不使用 Flask 请求上下文。"""
    errors = []

    def run():
        try:
            fn, args = job
            fn(*args)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=3)
    assert not thread.is_alive(), 'Synthetic background work must finish promptly'
    assert errors == [], errors


class TestAwardCoverRequestPipeline:
    @pytest.mark.parametrize('method', ['get', 'head'])
    def test_existing_tiny_cache_is_rejected_and_queued(
        self, client, db, award_cover_pipeline, method, record_property
    ):
        fixture = award_cover_pipeline
        filename = 'e' * 32 + '.jpg'
        content = b'GIF89a' + b'0' * 37  # Historical 43-byte Open Library placeholder.
        (fixture['cache_dir'] / filename).write_bytes(content)
        fixture['book'].cover_local_path = f'/cache/images/{filename}'
        db.session.commit()
        response = getattr(client, method)(f'/award-book/{fixture["book_id"]}/cover')
        record_property('cached_file_bytes', len(content))
        record_property('synthetic_http_trace', json.dumps(fixture['trace']))
        assert response.status_code == 302
        assert response.location.endswith(DEFAULT_COVER)
        assert response.headers['Cache-Control'] == 'no-store'
        assert 'X-Cover-Path' not in response.headers
        assert len(fixture['jobs']) == 1
        assert fixture['trace'] == []
        if method == 'head':
            assert response.data == b''

    def test_actual_worker_unvalidated_configured_key_quota_never_calls_google(
        self, client, db, award_cover_pipeline, record_property
    ):
        fixture = award_cover_pipeline
        source = fixture['google']
        source._api_key = 'synthetic-key-not-a-credential'
        assert not source._key_validated
        cache = source._api_cache
        cache.set('google_books', GoogleBooksClient._QUOTA_BLOCKED_KEY, True)
        cache._mem_cache.clear()
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert fixture['trace'] == []
        assert len(fixture['jobs']) == 1
        _run_award_cover_job(fixture['jobs'][0])
        record_property('synthetic_http_trace', json.dumps(fixture['trace']))
        google_calls = [call for call in fixture['trace'] if call['url'] == source._base_url]
        assert google_calls == [], 'Active quota must block even the unvalidated configured-Key q=test request'
        assert len(fixture['trace']) == 2  # The existing OL fallbacks still run.
        assert all(not call['in_request'] and not call['db_transaction_active'] for call in fixture['trace'])
        assert not source._key_validated
        assert not source._key_is_valid

    def test_cold_head_and_get_share_one_task(self, client, award_cover_pipeline):
        fixture = award_cover_pipeline
        url = f'/award-book/{fixture["book_id"]}/cover'
        for method in (client.head, client.get, client.head):
            response = method(url)
            assert response.status_code == 302
            assert response.location.endswith(DEFAULT_COVER)
            assert response.headers['Cache-Control'] == 'no-store'
        assert fixture['trace'] == []
        assert len(fixture['jobs']) == 1

    @pytest.mark.parametrize('source', ['known_url', 'missing_url'])
    def test_cold_award_cover_never_runs_upstream_in_request(
        self, client, db, award_cover_pipeline, source, record_property
    ):
        fixture = award_cover_pipeline
        if source == 'known_url':
            fixture['book'].cover_original_url = NYT_COVER
            db.session.commit()
        started = time.perf_counter()
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        record_property('elapsed_seconds', time.perf_counter() - started)
        record_property('synthetic_http_trace', json.dumps(fixture['trace']))

        assert response.status_code == 302
        assert response.location.endswith(DEFAULT_COVER)
        assert response.headers['Cache-Control'] == 'no-store'
        assert len(fixture['jobs']) == 1
        request_http = [call for call in fixture['trace'] if call['in_request'] or call['request_thread']]
        assert request_http == [], 'Cold award cover must return before remote resolution/download runs'

    def test_warm_award_cover_serves_real_file_without_upstream(
        self, client, db, award_cover_pipeline, record_property
    ):
        fixture = award_cover_pipeline
        filename = 'd' * 32 + '.jpg'
        content = b'\xff\xd8\xff' + b'0' * 4096
        (fixture['cache_dir'] / filename).write_bytes(content)
        fixture['book'].cover_local_path = f'/cache/images/{filename}'
        db.session.commit()
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        record_property('synthetic_http_trace', json.dumps(fixture['trace']))

        assert response.status_code == 200
        assert response.data == content
        assert response.headers['X-Cover-Source'] == 'cache'
        assert response.headers['X-Cover-Path'] == f'/cache/images/{filename}'
        assert fixture['trace'] == []
        assert fixture['jobs'] == []

        head = client.head(f'/award-book/{fixture["book_id"]}/cover')
        assert head.status_code == 200
        assert head.data == b''
        assert head.headers['X-Cover-Path'] == f'/cache/images/{filename}'
        assert fixture['trace'] == []
        assert fixture['jobs'] == []

    def test_generic_cover_cold_path_already_queues_without_upstream(
        self, client, award_cover_pipeline, record_property
    ):
        fixture = award_cover_pipeline
        response = client.get('/cover', query_string={'src': NYT_COVER})
        record_property('synthetic_http_trace', json.dumps(fixture['trace']))

        assert response.status_code == 302
        assert response.location.endswith(DEFAULT_COVER)
        assert response.headers['Cache-Control'] == 'no-store'
        assert fixture['trace'] == []
        assert len(fixture['jobs']) == 1
        filename = hashlib.md5(NYT_COVER.encode(), usedforsecurity=False).hexdigest() + '.jpg'
        assert not (fixture['cache_dir'] / filename).exists()

    @pytest.mark.parametrize('source', ['known_url', 'missing_url'])
    def test_background_resolution_persists_and_next_request_serves_file(
        self, client, db, award_cover_pipeline, source
    ):
        fixture = award_cover_pipeline
        if source == 'known_url':
            fixture['book'].cover_original_url = NYT_COVER
            db.session.commit()
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert fixture['trace'] == []
        assert len(fixture['jobs']) == 1

        _run_award_cover_job(fixture['jobs'][0])

        assert len(fixture['trace']) == (1 if source == 'known_url' else 5)
        assert all(not call['in_request'] and not call['request_thread'] for call in fixture['trace'])
        assert all(not call['db_transaction_active'] for call in fixture['trace'])
        db.session.expire_all()
        persisted = db.session.get(AwardBook, fixture['book_id'])
        assert persisted.cover_original_url == NYT_COVER
        assert persisted.cover_local_path.startswith('/cache/images/')
        trace_count = len(fixture['trace'])
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 200
        assert len(response.data) > 1024
        assert response.headers['X-Cover-Source'] == 'cache'
        assert len(fixture['jobs']) == 1
        assert len(fixture['trace']) == trace_count

    def test_repeated_cold_requests_submit_once(self, client, award_cover_pipeline):
        fixture = award_cover_pipeline
        for _ in range(4):
            response = client.get(f'/award-book/{fixture["book_id"]}/cover')
            assert response.status_code == 302
            assert response.headers['Cache-Control'] == 'no-store'
        assert fixture['trace'] == []

    def test_concurrent_record_edit_is_preserved(self, client, db, award_cover_pipeline, monkeypatch):
        from app.services.cover_resolver import CoverResolver

        fixture = award_cover_pipeline
        real_resolve = CoverResolver.resolve

        def resolve_and_edit(resolver, book, *args, **kwargs):
            result = real_resolve(resolver, book, *args, **kwargs)
            with client.application.app_context():
                current = db.session.get(AwardBook, fixture['book_id'])
                current.title = 'Edited during cover resolution'
                db.session.commit()
            return result

        monkeypatch.setattr(CoverResolver, 'resolve', resolve_and_edit)
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert len(fixture['jobs']) == 1
        _run_award_cover_job(fixture['jobs'][0])
        db.session.expire_all()
        current = db.session.get(AwardBook, fixture['book_id'])
        assert current.title == 'Edited during cover resolution'
        assert current.cover_local_path.startswith('/cache/images/')
        assert len(fixture['jobs']) == 1

    def test_submit_failure_releases_reservation(self, client, award_cover_pipeline, monkeypatch):
        from app.routes import main

        fixture = award_cover_pipeline
        attempts = []

        def reject(job, *args):
            attempts.append(job)
            raise RuntimeError('synthetic executor unavailable')

        monkeypatch.setattr(main, 'submit_background_task', reject)
        for _ in range(2):
            response = client.get(f'/award-book/{fixture["book_id"]}/cover')
            assert response.status_code == 302
            assert response.location.endswith(DEFAULT_COVER)
            assert response.headers['Cache-Control'] == 'no-store'
        assert len(attempts) == 2
        assert fixture['trace'] == []

    def test_failed_download_retries_only_in_worker_and_allows_later_retry(
        self, client, db, award_cover_pipeline, monkeypatch
    ):
        fixture = award_cover_pipeline
        fixture['book'].cover_original_url = NYT_COVER
        db.session.commit()
        calls, sleeps = [], []

        def fail_http(session, method, url, **kwargs):
            calls.append((has_request_context(), threading.get_ident(), db.session().in_transaction()))
            raise requests.RequestException('synthetic image transport failure')

        monkeypatch.setattr(requests.sessions.Session, 'request', fail_http)
        monkeypatch.setattr('app.services.api_utils.time.sleep', sleeps.append)
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert response.location.endswith(DEFAULT_COVER)
        assert calls == []
        assert sleeps == []
        assert len(fixture['jobs']) == 1
        _run_award_cover_job(fixture['jobs'][0])
        assert len(calls) == 3
        assert sleeps == [0.4, 0.8]
        assert all(
            not in_request and thread_id != threading.get_ident() and not transaction
            for in_request, thread_id, transaction in calls
        )
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert response.headers['Cache-Control'] == 'no-store'
        assert len(fixture['jobs']) == 2
        assert len(calls) == 3

    def test_resolve_failure_releases_reservation(self, client, award_cover_pipeline, monkeypatch):
        from app.services.cover_resolver import CoverResolver

        fixture = award_cover_pipeline
        contexts = []

        def fail(self, book, *args, **kwargs):
            contexts.append((has_app_context(), has_request_context(), threading.get_ident()))
            raise RuntimeError('synthetic resolver failure')

        monkeypatch.setattr(CoverResolver, 'resolve', fail)
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert contexts == []
        assert len(fixture['jobs']) == 1
        _run_award_cover_job(fixture['jobs'][0])
        assert contexts[0][0:2] == (True, False)
        assert contexts[0][2] != threading.get_ident()
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert len(fixture['jobs']) == 2

    def test_deleted_book_worker_exits_without_resolution(self, client, db, award_cover_pipeline):
        fixture = award_cover_pipeline
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert len(fixture['jobs']) == 1
        db.session.delete(fixture['book'])
        db.session.commit()
        _run_award_cover_job(fixture['jobs'][0])
        assert fixture['trace'] == []
        assert client.get(f'/award-book/{fixture["book_id"]}/cover').status_code == 404

    def test_worker_reloads_current_record(self, client, db, award_cover_pipeline):
        fixture = award_cover_pipeline
        response = client.get(f'/award-book/{fixture["book_id"]}/cover')
        assert response.status_code == 302
        assert fixture['trace'] == []
        assert len(fixture['jobs']) == 1
        fixture['book'].cover_original_url = NYT_COVER
        db.session.commit()
        _run_award_cover_job(fixture['jobs'][0])
        assert len(fixture['trace']) == 1
        assert fixture['trace'][0]['method'] == 'GET'
        assert not fixture['trace'][0]['in_request']

    def test_pending_is_bounded_across_distinct_books(self, client, db, award_cover_pipeline):
        fixture = award_cover_pipeline
        books = [
            AwardBook(
                award_id=fixture['book'].award_id,
                year=2026,
                title=f'Synthetic queued book {index}',
                author='Synthetic Author',
                is_displayable=True,
            )
            for index in range(35)
        ]
        db.session.add_all(books)
        db.session.commit()
        for book in books:
            response = client.get(f'/award-book/{book.id}/cover')
            assert response.status_code == 302
            assert response.headers['Cache-Control'] == 'no-store'
        assert len(fixture['jobs']) == 32
        assert fixture['trace'] == []

    def test_pending_is_separate_for_each_app(self, client, award_cover_pipeline, monkeypatch):
        from app.routes.main import main_bp
        from app.services.award_book_service import AwardBookService

        fixture = award_cover_pipeline
        monkeypatch.setattr(AwardBookService, 'get_award_book_by_id', lambda self, book_id: fixture['book'])
        other_app = Flask('synthetic-other-cover-app')
        other_app.config['IMAGE_CACHE_DIR'] = fixture['cache_dir']
        other_app.register_blueprint(main_bp)
        for app_client in (client, other_app.test_client(), client):
            response = app_client.get(f'/award-book/{fixture["book_id"]}/cover')
            assert response.status_code == 302
            assert response.headers['Cache-Control'] == 'no-store'
        assert len(fixture['jobs']) == 2
        assert fixture['trace'] == []

    def test_three_slow_workers_leave_database_pool_available(self, award_cover_pipeline, tmp_path, monkeypatch):
        from app.models.database import db
        from app.routes.main import main_bp

        fixture = award_cover_pipeline
        pooled_app = Flask('synthetic-pooled-award-covers')
        pooled_app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI=f'sqlite:///{(tmp_path / "cover-pool.sqlite").as_posix()}',
            SQLALCHEMY_ENGINE_OPTIONS={
                'poolclass': QueuePool,
                'pool_size': 3,
                'max_overflow': 0,
                'pool_timeout': 0.25,
                'connect_args': {'check_same_thread': False},
            },
            IMAGE_CACHE_DIR=fixture['cache_dir'],
        )
        pooled_app.extensions['image_cache_service'] = fixture['image_cache']
        db.init_app(pooled_app)
        pooled_app.register_blueprint(main_bp)
        with pooled_app.app_context():
            db.create_all()
            engine = db.engine
            award = Award(name='Synthetic pool award')
            db.session.add(award)
            db.session.flush()
            books = [
                AwardBook(
                    award_id=award.id,
                    year=2026,
                    title=f'Synthetic pooled book {index}',
                    author='Synthetic Author',
                    cover_original_url=NYT_COVER.replace('.jpg', f'-pool-{index}.jpg'),
                    is_displayable=True,
                )
                for index in range(3)
            ]
            db.session.add_all(books)
            db.session.flush()
            ids = [book.id for book in books]
            db.session.commit()
        all_network_started, release_network = threading.Event(), threading.Event()
        state_lock = threading.Lock()
        network_threads, transactions, errors = set(), [], []

        def paused_http(session, method, url, **kwargs):
            assert not has_request_context(), 'Pooled route may not run remote HTTP'
            with state_lock:
                transactions.append(db.session().in_transaction())
                network_threads.add(threading.get_ident())
                if len(network_threads) == 3:
                    all_network_started.set()
            assert release_network.wait(timeout=3), 'Synthetic network barrier must be released'
            result = requests.Response()
            result.status_code = 200
            result.headers['Content-Type'] = 'image/jpeg'
            result._content = b'\xff\xd8\xff' + b'0' * 4096
            result._content_consumed = True
            return result

        monkeypatch.setattr(requests.sessions.Session, 'request', paused_http)
        app_client = pooled_app.test_client()
        for book_id in ids:
            response = app_client.get(f'/award-book/{book_id}/cover')
            assert response.status_code == 302
            assert response.location.endswith(DEFAULT_COVER)
        assert len(fixture['jobs']) == 3

        def run(job):
            try:
                fn, args = job
                fn(*args)
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=run, args=(job,)) for job in fixture['jobs']]
        try:
            for worker in workers:
                worker.start()
            assert all_network_started.wait(timeout=2), 'All three workers must reach the real image HTTP seam'
            assert engine.pool.checkedout() == 0, 'Slow cover HTTP may not lease any of the three DB connections'
            started = time.perf_counter()
            with pooled_app.app_context():
                assert db.session.execute(text('SELECT 1')).scalar() == 1
            assert time.perf_counter() - started < 0.5
        finally:
            release_network.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(timeout=3)
            engine.dispose()
        assert all(not worker.is_alive() for worker in workers)
        assert errors == []
        assert transactions == [False, False, False]


class TestCspParity:
    """CSP 的 img-src 白名单必须是代理白名单的子集。"""

    @staticmethod
    def _csp_img_hosts(csp: str) -> set[str]:
        match = re.search(r'img-src ([^;]+);', csp)
        assert match, f'CSP 中找不到 img-src 指令: {csp}'
        hosts = set()
        for token in match.group(1).split():
            if not token.startswith('https://'):
                continue
            host = token[len('https://') :]
            hosts.add(host[2:] if host.startswith('*.') else host)
        return hosts

    def test_every_csp_image_host_is_proxyable(self, client):
        csp = client.get('/').headers.get('Content-Security-Policy', '')
        csp_hosts = self._csp_img_hosts(csp)
        assert csp_hosts, 'CSP img-src 白名单为空，测试本身可能失效'

        missing = sorted(h for h in csp_hosts if h not in ALLOWED_COVER_HOSTS)
        assert not missing, (
            f'CSP 放行但代理白名单缺失的封面域名: {missing}；'
            f'浏览器能直连却会被 /cover 拒绝，需要同步 app/utils/cover_urls.py'
        )
