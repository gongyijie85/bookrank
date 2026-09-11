"""Cover fallback regression (async prefetch #178 follow-up)."""

from app.models.book import Book


def _book_with_original():
    b = Book.from_api_response(
        book_data={
            'rank': 1,
            'title': 'T',
            'author': 'A',
            'primary_isbn13': '9780593798638',
            'book_image': 'https://static01.nyt.com/x.jpg',
        },
        category_id='hardcover-fiction',
        category_name='Fiction',
        list_name='List',
        published_date='2026-01-01',
        supplement={},
    )
    b._original_cover = 'https://static01.nyt.com/x.jpg'
    b.cover = ''  # 异步未就绪 -> cover 为空
    return b


def test_to_dict_exposes_original_cover():
    d = _book_with_original().to_dict()
    assert d['_original_cover'] == 'https://static01.nyt.com/x.jpg'
    assert d['cover'] == ''


def test_template_src_prefers_original_over_placeholder():
    """cover 为占位字符串时（block=False 预取未落地），src 应回退 original。

    回归：block=False 返回 '/static/default-cover.png'（非空串）使模板
    `cover if cover` 判真 → 永远占位；现在排除占位串走 original。
    """
    from jinja2 import Template

    expr = """{% set _cover = book.cover if book.cover and book.cover != '/static/default-cover.png' else '' %}{{ _cover or book._original_cover or 'FINAL-DEFAULT' }}"""
    t = Template(expr)

    # 占位 + original → original
    out = t.render(book={'cover': '/static/default-cover.png', '_original_cover': 'https://static01.nyt.com/x.jpg'})
    assert out == 'https://static01.nyt.com/x.jpg'
    # 缓存 + original → cache 优先
    out = t.render(book={'cover': '/cache/images/abc.jpg', '_original_cover': 'https://static01.nyt.com/x.jpg'})
    assert out == '/cache/images/abc.jpg'
    # 全空 → 最终默认
    out = t.render(book={'cover': '', '_original_cover': ''})
    assert out == 'FINAL-DEFAULT'


class _StubImageCache:
    """按路径集合判定存在性的最小 image_cache 替身，镜像真实服务的探测语义。"""

    def __init__(self, present_paths: tuple[str, ...] = ()) -> None:
        self.present_paths = set(present_paths)
        self.seen: list[str] = []

    def is_cached_file_present(self, local_path: str) -> bool:
        self.seen.append(local_path)
        if not local_path or not local_path.startswith('/cache/images/'):
            return True  # 非缓存目录路径无需探测，与真实实现一致
        return local_path in self.present_paths


def test_stale_local_cover_is_dropped_so_template_falls_back(app):
    """生产临时文件系统重启后本地封面文件消失，DB 路径仍在：必须探测为不可用，
    否则模板会渲染出必然 404 的 src，每张封面白跑一次失败请求。"""
    from app.routes.main import _available_local_cover

    stale = '/cache/images/de0a7b0c2d7dafee3c5b66ef7d8a4a72.jpg'
    live = '/cache/images/aaaa.jpg'
    stub = _StubImageCache(present_paths=(live,))
    app.extensions['image_cache_service'] = stub
    with app.app_context():
        assert _available_local_cover(stale) == ''
        assert _available_local_cover(live) == live
        assert _available_local_cover(None) == ''
        assert _available_local_cover('   ') == ''
        # 空路径提前返回，不触发探测
        assert stub.seen == [stale, live]


def test_non_cache_path_is_returned_without_probe(app):
    from app.routes.main import _available_local_cover

    stub = _StubImageCache()
    app.extensions['image_cache_service'] = stub
    with app.app_context():
        assert _available_local_cover('/static/default-cover.png') == '/static/default-cover.png'
