"""封面地址规范化与同源封面代理（app/utils/cover_urls.py + /cover 路由）。

覆盖的是 #issue3：国内网络无法直连 storage.googleapis.com（NYT 榜单封面实际所在的
图床）、covers.openlibrary.org 等境外域名，且这些域名也不在 CSP `img-src` 白名单内，
封面因此一律退化成占位图。修复方式是把取图动作挪到服务端，浏览器只请求同源 /cover。

这些用例刻意钉住三件容易回归的事：
1. 已经是同源路径的值不会被二次包裹（否则 /cover?src=/cover?src=… 无限套娃）；
2. 非白名单域名不会被代理（代理的 src 由请求方控制，白名单是资源放大与 SSRF 的边界）；
3. CSP 放行的每个图床域名都必须同时出现在代理白名单里，否则浏览器能直连但代理会拒绝。
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from app.utils.cover_urls import (
    ALLOWED_COVER_HOSTS,
    COVER_PROXY_PATH,
    DEFAULT_COVER,
    cached_filename_from_path,
    cover_src,
    cover_src_or_default,
    is_allowed_cover_host,
)

NYT_COVER = 'https://storage.googleapis.com/du-prd/books/images/9780593139134.jpg'
OL_COVER = 'https://covers.openlibrary.org/b/isbn/9780143127550-L.jpg?default=false'


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
