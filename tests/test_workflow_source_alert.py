"""Workflow source-alert acknowledgements must distinguish delivery from no-op."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import source_alert_service, source_health_service


@pytest.mark.parametrize(
    'status, configured, issue, expected',
    [
        ('degraded', False, {'number': 0}, 'not_configured'),
        ('degraded', True, {'number': 42}, 'delivered'),
        ('degraded', True, {'number': 0}, 'not_delivered'),
        ('degraded', True, {'number': True}, 'not_delivered'),
        ('healthy', True, None, 'not_required'),
        ('healthy', False, None, 'not_configured'),
        ('disabled', True, None, 'not_required'),
    ],
)
def test_source_alert_http_success_reports_actual_delivery(
    app, client, admin_headers, monkeypatch, status, configured, issue, expected
):
    monkeypatch.setitem(app.config, 'ADMIN_SECRET', 'test-admin-secret')
    publisher = SimpleNamespace(source_status=status, last_success_batch_id=None)
    monkeypatch.setattr(source_health_service, 'publisher_for_source', lambda source: publisher)
    monkeypatch.setattr(
        source_alert_service,
        'get_github_client',
        lambda: Mock() if configured else source_alert_service.NullGithubClient(),
    )
    sync = Mock(return_value=issue)
    close = Mock()
    monkeypatch.setattr(source_alert_service, 'sync_degraded_alert', sync)
    monkeypatch.setattr(source_alert_service, 'close_degraded_alert', close)
    response = client.post('/api/admin/new-books/source-alert/sync/harpercollins', headers=admin_headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['delivery'] == expected
    if status == 'degraded':
        sync.assert_called_once_with('harpercollins', publisher)
    else:
        sync.assert_not_called()
