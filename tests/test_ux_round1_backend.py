"""读者 HTML 入口与周报记录必须使用签名 session_id。"""

from __future__ import annotations

import re
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_HEX_SESSION = re.compile(r'^[0-9a-f]{32}$')
_FORGED_COOKIE = 'forged-plain-cookie'
_OWNER_SESSION = 'signed-owner-id'
_REPORT_DATE = '2024-01-15'
_REPORT_ID = 11


def _signed_session_id(client) -> str | None:
    with client.session_transaction() as sess:
        value = sess.get('session_id')
    return value or None


@contextmanager
def _book_service(app):
    with app.app_context():
        previous = app.extensions.get('book_service', None)
        app.extensions['book_service'] = MagicMock()
    try:
        yield
    finally:
        with app.app_context():
            if previous is None:
                app.extensions.pop('book_service', None)
            else:
                app.extensions['book_service'] = previous


def _report_service():
    report = SimpleNamespace(id=_REPORT_ID)
    service = MagicMock()
    service.get_report_by_week_end.return_value = report
    service.get_report_by_date.return_value = None
    return service


def _presentation():
    return {'content': {}, 'summary': '', 'summary_source': 'test'}


@pytest.mark.parametrize(
    'path',
    ['/', '/book/0', '/search', '/reports/weekly', '/awards', '/new-books'],
)
def test_reader_entry_mints_distinct_signed_session_ids(app, db, path):
    """两个独立客户端进入读者页，各自得到签名 session，且不采纳同一个明文 cookie。"""
    with (
        patch('app.routes.main.render_adaptive', return_value='ok'),
        patch('app.routes.main.get_service', return_value=MagicMock()),
        patch('app.routes.main._get_books_for_category', return_value=([], None)),
        patch('app.routes.main.get_new_book_modules', return_value=MagicMock()),
        patch('app.routes.main._load_new_books_data', return_value={}),
        patch('app.tasks.weekly_report_task.generate_weekly_report'),
    ):
        client_a = app.test_client()
        client_b = app.test_client()
        client_a.set_cookie('session_id', _FORGED_COOKIE)
        client_b.set_cookie('session_id', _FORGED_COOKIE)

        response_a = client_a.get(path, follow_redirects=True)
        response_b = client_b.get(path, follow_redirects=True)

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    sid_a = _signed_session_id(client_a)
    sid_b = _signed_session_id(client_b)
    assert sid_a and _HEX_SESSION.fullmatch(sid_a), sid_a
    assert sid_b and _HEX_SESSION.fullmatch(sid_b), sid_b
    assert sid_a != sid_b
    assert sid_a != _FORGED_COOKIE
    assert sid_b != _FORGED_COOKIE
    assert sid_a != 'anonymous'
    assert sid_b != 'anonymous'


def test_weekly_report_view_records_existing_signed_id_not_forged_cookie(app, db):
    service = _report_service()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['session_id'] = _OWNER_SESSION
    client.set_cookie('session_id', _FORGED_COOKIE)

    with (
        _book_service(app),
        patch('app.services.weekly_report_service.WeeklyReportService', return_value=service),
        patch('app.routes.main.parse_report_content', return_value={}),
        patch('app.routes.main.prepare_report_presentation', return_value=_presentation()),
        patch('app.routes.main.render_adaptive', return_value='ok'),
    ):
        response = client.get(f'/reports/weekly/{_REPORT_DATE}')

    assert response.status_code == 200
    assert _signed_session_id(client) == _OWNER_SESSION
    recorded = service.record_report_view.call_args.kwargs
    assert recorded['report_id'] == _REPORT_ID
    assert recorded['session_id'] == _OWNER_SESSION


def test_weekly_report_export_records_existing_signed_id_not_forged_cookie(app, db):
    service = _report_service()
    export_service = MagicMock()
    export_service.export_weekly_report_pdf.return_value = BytesIO(b'%PDF-1.4')
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['session_id'] = _OWNER_SESSION
    client.set_cookie('session_id', _FORGED_COOKIE)

    with (
        _book_service(app),
        patch('app.services.weekly_report_service.WeeklyReportService', return_value=service),
        patch('app.services.export_service.ExportService', return_value=export_service),
        patch('app.routes.main.prepare_report_presentation', return_value=_presentation()),
        patch('app.routes.main.render_adaptive', return_value='ok'),
    ):
        response = client.get(f'/reports/weekly/{_REPORT_DATE}/export?format=pdf')

    assert response.status_code == 200
    assert _signed_session_id(client) == _OWNER_SESSION
    recorded = service.record_report_export.call_args.kwargs
    assert recorded['date'] == _REPORT_DATE
    assert recorded['session_id'] == _OWNER_SESSION


def test_fresh_weekly_report_view_does_not_record_forged_or_anonymous(app, db):
    service = _report_service()
    client = app.test_client()
    client.set_cookie('session_id', _FORGED_COOKIE)

    with (
        _book_service(app),
        patch('app.services.weekly_report_service.WeeklyReportService', return_value=service),
        patch('app.routes.main.parse_report_content', return_value={}),
        patch('app.routes.main.prepare_report_presentation', return_value=_presentation()),
        patch('app.routes.main.render_adaptive', return_value='ok'),
    ):
        response = client.get(f'/reports/weekly/{_REPORT_DATE}')

    assert response.status_code == 200
    recorded_id = service.record_report_view.call_args.kwargs['session_id']
    assert recorded_id == _signed_session_id(client)
    assert _HEX_SESSION.fullmatch(recorded_id), recorded_id
    assert recorded_id != _FORGED_COOKIE
    assert recorded_id != 'anonymous'
    assert service.record_report_view.call_args.kwargs['report_id'] == _REPORT_ID
