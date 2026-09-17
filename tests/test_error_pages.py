"""Error pages: 404 and 500 must say different, self-consistent things.

Before this, `error.html` hard-coded its `<h1>` to 「出错了」 (a 500-flavoured phrase) while the
handlers only passed a sub-message. A 404 therefore rendered three mutually contradictory
phrases on one page: `<title>` 「出错」, `<h1>` 「出错了」, body "Page not found".

`<title>` and `<h1>` now share the handler-supplied `heading`, so they cannot drift apart.
"""

from __future__ import annotations

import re

from flask import render_template

from app import create_app


def _heading(html: str) -> str:
    return re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S).group(1).strip()


def _title(html: str) -> str:
    return re.search(r'<title[^>]*>(.*?)</title>', html, re.S).group(1).strip()


class TestNotFoundPage:
    def test_heading_says_page_not_found_in_chinese(self, client) -> None:
        response = client.get('/definitely-not-a-real-path?lang=zh')
        assert response.status_code == 404
        html = response.get_data(as_text=True)
        heading = _heading(html)
        assert heading == '页面不存在', f'404 heading should name the actual problem, got {heading!r}'
        assert '出错了' not in html, '404 must not keep the generic 500-flavoured heading'

    def test_title_and_heading_agree(self, client) -> None:
        """The ticket's core complaint: <title> and <h1> contradicted each other."""
        response = client.get('/definitely-not-a-real-path?lang=zh')
        html = response.get_data(as_text=True)
        heading = _heading(html)
        title = _title(html)
        assert heading in title, f'<title> ({title!r}) should contain <h1> ({heading!r})'

    def test_english_locale_renders_english(self, client) -> None:
        response = client.get('/definitely-not-a-real-path?lang=en')
        html = response.get_data(as_text=True)
        assert _heading(html) == 'Page not found'
        assert 'Page not found' in _title(html)

        # Scope the CJK check to the error block itself. The rest of the page legitimately
        # contains CJK: the language switcher renders the Chinese option's own glyphs (中/简)
        # so speakers can find their language, exactly like the Chinese UI shows "English".
        block = re.search(r'<div class="error-page">.*?</div>\s*</div>\s*</div>', html, re.S)
        assert block, 'error block not found'
        text = re.sub(r'<[^>]+>', ' ', block.group(0))
        assert not re.search(r'[\u4e00-\u9fff]', text), f'404 body still Chinese: {text.strip()[:80]}'

    def test_has_noindex(self, client) -> None:
        html = client.get('/definitely-not-a-real-path?lang=zh').get_data(as_text=True)
        assert 'noindex' in html, '404 responses must carry a noindex directive'

    def test_normal_pages_remain_indexable(self, client) -> None:
        """The noindex override is per-error-page, not global."""
        html = client.get('/?lang=zh').get_data(as_text=True)
        assert 'index, follow' in html
        assert 'noindex' not in html


class TestServerErrorPage:
    def _server_error_html(self, lang: str) -> str:
        """Force a real 500 through the registered handler.

        A throwaway app instance keeps the route out of the session-scoped `app` fixture, so
        this cannot leak into other tests.
        """
        app = create_app('testing')
        app.config['PROPAGATE_EXCEPTIONS'] = False

        @app.route('/__boom__')
        def _boom():  # pragma: no cover - only reached through the error path
            raise RuntimeError('boom')

        return app.test_client().get(f'/__boom__?lang={lang}').get_data(as_text=True)

    def test_heading_says_server_error_in_chinese(self) -> None:
        html = self._server_error_html('zh')
        heading = _heading(html)
        assert heading == '服务器出错', f'500 heading should say the server failed, got {heading!r}'

    def test_distinct_from_not_found(self) -> None:
        html = self._server_error_html('zh')
        heading = _heading(html)
        assert heading != '页面不存在', '500 and 404 must not share a heading'

    def test_not_noindex(self) -> None:
        """A 500 is transient — it should not be permanently de-indexed."""
        html = self._server_error_html('zh')
        assert 'noindex' not in html


class TestOtherErrorPageCallers:
    """`error.html` has ~17 callers (book missing, service unavailable, ...).

    They pass no `heading`, so the generic one must still render — this guards the refactor
    from leaving them with an empty `<h1>`.
    """

    def test_template_falls_back_when_no_heading_is_given(self, app) -> None:
        with app.test_request_context('/?lang=zh'):
            html = render_template('error.html', message='书籍不存在', back_url='/')
        assert _heading(html) == '出错了'
        assert '书籍不存在' in html

    def test_explicit_heading_wins(self, app) -> None:
        with app.test_request_context('/?lang=zh'):
            html = render_template('error.html', heading='页面不存在', message='x', noindex=True, back_url='/')
        assert _heading(html) == '页面不存在'
        assert 'noindex' in html


class TestApiRoutesUnaffected:
    """The ticket requires API routes to keep returning JSON, not the HTML error page."""

    def test_api_404_returns_json(self, client) -> None:
        response = client.get('/api/definitely-not-a-real-endpoint')
        assert response.status_code == 404
        body = response.get_json()
        assert body is not None, 'API 404 must stay JSON, not render the HTML error page'
        assert body.get('success') is False
        assert response.get_data(as_text=True).lstrip().startswith('{')

    def test_api_path_does_not_render_the_error_template(self, client) -> None:
        html = client.get('/api/definitely-not-a-real-endpoint').get_data(as_text=True)
        assert '<h1' not in html
        assert 'noindex' not in html
