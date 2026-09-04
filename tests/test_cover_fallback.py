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
