"""Scheduler errors must retain context and require real webhook receipts."""

from unittest.mock import Mock

import pytest
import requests
from flask import has_app_context

from app import create_app, setup
from app.models.database import db
from app.models.schemas import SystemConfig


def test_scheduler_failure_outside_request_persists_only_failure_counter(monkeypatch):
    application = create_app('testing')
    monkeypatch.setattr(setup, '_task_failure_counts', {})
    monkeypatch.delenv('ALERT_WEBHOOK_URL', raising=False)

    def failing_task(app):
        db.session.add(SystemConfig(key='uncommitted_task_result', value='must not persist'))
        raise RuntimeError('simulated task failure')

    assert not has_app_context()
    try:
        setup._scheduler_wrapper(application, failing_task)()
        assert not has_app_context()
        with application.app_context():
            assert SystemConfig.get_value('last_failure_count_failing_task') == '1'
            assert SystemConfig.get_value('uncommitted_task_result') is None
    finally:
        with application.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.mark.parametrize(
    'status, body',
    [(500, {'code': 0}), (200, {'code': 999}), (200, {'code': False}), (200, {}), (200, []), (204, None)],
)
def test_task_alert_does_not_report_rejected_or_unconfirmed_delivery(app, monkeypatch, caplog, status, body):
    monkeypatch.setenv('ALERT_WEBHOOK_URL', 'https://example.invalid/hook')
    response = Mock(status_code=status)
    response.raise_for_status.side_effect = requests.HTTPError('simulated rejection') if status == 500 else None
    response.json.return_value = body
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, 'post', post)
    assert setup._notify_task_failure(app, 'probe_task', 2, 'RuntimeError') is False
    assert '已发送后台任务失败告警' not in caplog.text
    assert post.call_count == 1


@pytest.mark.parametrize('body', [{'code': 0}, {'StatusCode': 0}, {'success': True}])
def test_task_alert_accepts_explicit_delivery(app, monkeypatch, body):
    monkeypatch.setenv('ALERT_WEBHOOK_URL', 'https://example.invalid/hook')
    response = Mock(status_code=200)
    response.json.return_value = body
    monkeypatch.setattr(requests, 'post', Mock(return_value=response))
    assert setup._notify_task_failure(app, 'probe_task', 2, 'RuntimeError') is True


def test_missing_all_alert_channels_is_explicit(app, monkeypatch, caplog):
    monkeypatch.delenv('ALERT_WEBHOOK_URL', raising=False)
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', False)
    assert setup._notify_task_failure(app, 'probe_task', 2, 'RuntimeError') is False
    assert '未发送' in caplog.text


def test_task_alert_timeout_is_nonfatal_and_redacts_exception(app, monkeypatch, caplog):
    monkeypatch.setenv('ALERT_WEBHOOK_URL', 'https://example.invalid/hook')
    marker = 'simulated-private-query-value'
    post = Mock(side_effect=requests.Timeout(marker))
    monkeypatch.setattr(requests, 'post', post)
    assert setup._notify_task_failure(app, 'probe_task', 2, 'RuntimeError') is False
    assert marker not in caplog.text
    assert post.call_count == 1


def test_rollback_failure_does_not_mask_original_task_failure(app, monkeypatch):
    track = Mock()
    monkeypatch.setattr(setup, '_track_task_failure', track)
    monkeypatch.setattr(db.session, 'rollback', Mock(side_effect=RuntimeError('rollback unavailable')))

    def broken_task(application):
        raise ValueError('original task failure')

    setup._scheduler_wrapper(app, broken_task)()
    track.assert_called_once_with(app, 'broken_task', 'ValueError')


def test_webhook_redirect_does_not_repeat_mutating_request(app, monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            received.append(self.path)
            self.send_response(307 if self.path == '/redirect' else 200)
            if self.path == '/redirect':
                self.send_header('Location', '/receiver')
                body = b''
            else:
                body = json.dumps({'code': 0}).encode()
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('ALERT_WEBHOOK_URL', f'http://127.0.0.1:{server.server_port}/redirect')
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    try:
        delivered = setup._post_alert_webhook(app, {'task': 'local-redirect-probe'})
        assert received == ['/redirect']
        assert delivered is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
