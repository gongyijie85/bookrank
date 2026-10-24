"""周报轮询只读取状态，不应反复搬运周报正文。"""

from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import event

from app.models.schemas import WeeklyReport


@contextmanager
def _selects(db):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        yield statements
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)


def _report(report_date, week_start, week_end):
    return WeeklyReport(
        report_date=report_date,
        week_start=week_start,
        week_end=week_end,
        title='Weekly status fixture',
        summary='SUMMARY ' * 10000,
        content='CONTENT ' * 10000,
        top_changes='CHANGES ' * 10000,
        featured_books='FEATURED ' * 10000,
    )


@pytest.fixture
def status_week(monkeypatch):
    monkeypatch.setattr('app.routes.main.get_service', lambda name: object())
    monkeypatch.setattr(
        'app.tasks.weekly_report_task_helpers.compute_expected_week_range',
        lambda today: (date(2026, 10, 5), date(2026, 10, 11)),
    )


def test_status_reads_only_status_fields_in_one_query(app, db, status_week):
    """状态接口保持原 JSON 和 report_date 排序，但不查询四个大文本字段。"""
    db.session.add_all(
        [
            _report(date(2026, 10, 12), date(2026, 10, 5), date(2026, 10, 11)),
            _report(date(2026, 10, 14), date(2026, 9, 14), date(2026, 9, 20)),
        ]
    )
    db.session.commit()
    db.session.expunge_all()

    with _selects(db) as statements:
        response = app.test_client().get('/api/weekly-report/status')

    assert response.status_code == 200
    assert response.get_json() == {
        'has_current_week': True,
        'expected_week_start': '2026-10-05',
        'expected_week_end': '2026-10-11',
        'latest_week_end': '2026-09-20',
    }
    assert len(statements) == 1
    sql = statements[0].lower()
    for column in ('summary', 'content', 'top_changes', 'featured_books'):
        assert column not in sql


def test_empty_status_observes_newly_generated_report_on_next_poll(app, db, status_week):
    """缺失状态不能被缓存，新报告提交后下一次轮询立即就绪。"""
    client = app.test_client()
    with _selects(db) as before_statements:
        before = client.get('/api/weekly-report/status')
    assert before.get_json() == {
        'has_current_week': False,
        'expected_week_start': '2026-10-05',
        'expected_week_end': '2026-10-11',
        'latest_week_end': None,
    }
    assert len(before_statements) == 1

    db.session.add(_report(date(2026, 10, 12), date(2026, 10, 5), date(2026, 10, 11)))
    db.session.commit()
    db.session.expunge_all()

    with _selects(db) as after_statements:
        after = client.get('/api/weekly-report/status')
    assert after.get_json()['has_current_week'] is True
    assert after.get_json()['latest_week_end'] == '2026-10-11'
    assert len(after_statements) == 1


def test_missing_current_report_still_returns_latest_week_end(app, db, status_week):
    db.session.add(_report(date(2026, 10, 5), date(2026, 9, 28), date(2026, 10, 4)))
    db.session.commit()
    db.session.expunge_all()

    response = app.test_client().get('/api/weekly-report/status')

    assert response.status_code == 200
    assert response.get_json()['has_current_week'] is False
    assert response.get_json()['latest_week_end'] == '2026-10-04'


def test_status_database_failure_keeps_unready_fallback(app, db, status_week, caplog):
    def fail_status(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'weekly_reports' in statement:
            raise RuntimeError('status database unavailable')

    event.listen(db.engine, 'before_cursor_execute', fail_status)
    try:
        response = app.test_client().get('/api/weekly-report/status')
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_status)

    assert response.status_code == 200
    assert response.get_json()['has_current_week'] is False
    assert response.get_json()['latest_week_end'] is None
    assert 'status database unavailable' in caplog.text


def test_status_service_unavailable_remains_503_without_query(app, db, status_week, monkeypatch):
    monkeypatch.setattr('app.routes.main.get_service', lambda name: None)

    with _selects(db) as statements:
        response = app.test_client().get('/api/weekly-report/status')

    assert response.status_code == 503
    assert statements == []
