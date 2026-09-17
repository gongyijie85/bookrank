"""封面地址规范化：把任意来源的封面 URL 收敛为浏览器可直接加载的同源地址。

## 为什么需要这一层

封面原始地址分散在三类境外图床上：

- NYT 榜单的 `book_image` → `https://storage.googleapis.com/du-prd/books/images/...`
- Open Library → `https://covers.openlibrary.org/b/isbn/....jpg`
- Google Books → `https://books.google.com/books/content?...`

国内网络环境下这些域名不可直连，浏览器只能渲染成占位图；同时
`app/__init__.py:add_security_headers` 的 CSP `img-src` 也没放行
`storage.googleapis.com`，即使网络通也会被浏览器拦掉。两条路径的修复成本不同、
效果却一致：**让浏览器只请求本站**，由服务端回源并本地化缓存。

所以本模块只做一件事：判断一个封面值是不是"本站可直接加载的地址"，是就原样返回，
不是就改写成 `/cover?src=<原始地址>`（见 `app/routes/main.py:cover_proxy`）。

模板侧通过 `cover_src` / `cover_src_or_default` 两个过滤器使用，
JS 侧用同名的 `window.BookRankCover.toSrc`（见 `static/js/base.js`），
两边规则必须保持一致，由 `tests/test_cover_urls.py` 钉住。
"""

from __future__ import annotations

from urllib.parse import quote, urlparse

#: 全站默认封面，同时也是所有封面回退链的终点。
DEFAULT_COVER = '/static/default-cover.png'

#: 同源封面代理的路径，供模板/JS 拼接时复用。
COVER_PROXY_PATH = '/cover'

#: 允许直接下发给浏览器的本站前缀。命中其一即无需代理。
#: - `/static/`：随包发布的默认封面与本地素材
#: - `/cache/images/`：ImageCacheService 落盘的封面
#: - `/cover`：已经是代理地址，避免二次包裹
_LOCAL_PREFIXES = ('/static/', '/cache/images/', COVER_PROXY_PATH)

#: 允许代理回源的封面域名。
#:
#: 与 `app/__init__.py` 的 CSP `img-src` 白名单保持同一集合——那边是"浏览器直连"的
#: 许可，这边是"服务端代取"的许可，两边任意一侧漏了域名，封面都会掉回占位图，
#: 所以新增封面源时必须同时改两处。`tests/test_cover_urls.py` 会比对两者的域名集合。
#:
#: 之所以要白名单而不是直接信任 `_is_safe_image_url`：代理路由的 `src` 完全由请求方
#: 控制，仅靠 SSRF 防护仍可被用来驱动服务端下载任意 https 图片（磁盘与带宽放大）。
ALLOWED_COVER_HOSTS: tuple[str, ...] = (
    # NYT 榜单封面（book_image 实际落在 GCS 上，而非 nytimes.com）
    'storage.googleapis.com',
    'static01.nyt.com',
    'nytimes.com',
    # Google Books（详情接口与出版商爬虫的 thumbnail）
    'books.google.com',
    'books.googleusercontent.com',
    # Open Library / Internet Archive
    'covers.openlibrary.org',
    'openlibrary.org',
    'archive.org',
    # 出版社官方图床
    'images.penguinrandomhouse.com',
    'penguinrandomhouse.com',
    'harpercollins.com',
    'macmillan.com',
    'simonandschuster.com',
    'hachettebookgroup.com',
    # 零售商（NYT buy_links 侧的历史封面源）
    'amazon.com',
    'amazonaws.com',
)


def is_local_cover(value: str) -> bool:
    """值是否已是本站可直连的地址（本站相对路径或代理地址）。"""
    return value.startswith(_LOCAL_PREFIXES)


def is_allowed_cover_host(url: str) -> bool:
    """URL 的主机是否在封面源白名单内。

    精确匹配或 `.后缀` 匹配，因此 `evil-storage.googleapis.com` 不会被
    `storage.googleapis.com` 的条目放行（`endswith('storage.googleapis.com')`
    这类写法正是这类绕过的来源）。
    """
    try:
        hostname = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    if not hostname:
        return False
    return any(hostname == host or hostname.endswith('.' + host) for host in ALLOWED_COVER_HOSTS)


def cover_src(raw: object) -> str:
    """把封面值规范化为同源地址；空值返回空串。

    空串而非默认封面是有意为之：模板里 `data-original` 这类属性需要区分
    "没有原始地址"和"原始地址是默认封面"，前者应保持为空以便 JS 回退链跳过它。
    """
    value = '' if raw is None else str(raw).strip()
    if not value:
        return ''
    if is_local_cover(value):
        return value
    return f'{COVER_PROXY_PATH}?src={quote(value, safe="")}'


def cover_src_or_default(raw: object) -> str:
    """同 `cover_src`，但空值时回退到默认封面（用于 `<img src>`）。"""
    return cover_src(raw) or DEFAULT_COVER


def cached_filename_from_path(local_path: str) -> str | None:
    """从 `/cache/images/<md5>.jpg` 取出文件名；非该形态返回 None。

    供封面代理与获奖图书封面路由复用，避免各自实现一遍前缀解析。
    """
    prefix = '/cache/images/'
    if not local_path.startswith(prefix):
        return None
    filename = local_path[len(prefix) :]
    if not filename or '/' in filename or '\\' in filename:
        return None
    return filename
