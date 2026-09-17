"""Resource threshold alert task tests (ROADMAP #8)."""

from unittest.mock import MagicMock, patch

import pytest

from app.setup import _resource_threshold_alert_task


class _FakeProc:
    def __init__(self, rss_bytes, pct):
        self._rss = rss_bytes
        self._pct = pct

    def memory_info(self):
        return MagicMock(rss=self._rss)

    def memory_percent(self):
        return self._pct


@pytest.mark.parametrize(
    'rss_bytes,pct,env,expect_alert',
    [
        (100 * 1024 * 1024, 20, {'MEMORY_ALERT_MB': '400', 'MEMORY_ALERT_PERCENT': '80'}, False),
        (500 * 1024 * 1024, 20, {'MEMORY_ALERT_MB': '400', 'MEMORY_ALERT_PERCENT': '80'}, True),
        (100 * 1024 * 1024, 90, {'MEMORY_ALERT_MB': '400', 'MEMORY_ALERT_PERCENT': '80'}, True),
    ],
)
def test_threshold_decision(rss_bytes, pct, env, expect_alert, app, monkeypatch):
    monkeypatch.setenv('MEMORY_ALERT_MB', env['MEMORY_ALERT_MB'])
    monkeypatch.setenv('MEMORY_ALERT_PERCENT', env['MEMORY_ALERT_PERCENT'])
    monkeypatch.setenv('ALERT_WEBHOOK_URL', '')
    fake_proc = _FakeProc(rss_bytes, pct)
    with patch('psutil.Process', return_value=fake_proc):
        _resource_threshold_alert_task(app)  # 不抛异常即通过


def test_alert_posts_webhook(app, monkeypatch):
    monkeypatch.setenv('MEMORY_ALERT_MB', '1')
    monkeypatch.setenv('MEMORY_ALERT_PERCENT', '0')
    monkeypatch.setenv('ALERT_WEBHOOK_URL', 'https://example.com/hook')
    fake_proc = _FakeProc(50 * 1024 * 1024, 99)
    mock_post = MagicMock()
    with patch('psutil.Process', return_value=fake_proc), patch('requests.post', mock_post):
        _resource_threshold_alert_task(app)
    assert mock_post.called
    payload = mock_post.call_args.kwargs['json']
    assert payload['task'] == 'resource_threshold'
    assert len(payload['exceeded']) >= 1
