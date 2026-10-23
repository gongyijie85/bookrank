from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.workflow_http import Reply, run_request, truncate_issue


@pytest.mark.parametrize('gate', ['lint', 'lint-frontend', 'typecheck', 'i18n-catalog', 'test', 'dependency-audit'])
def test_production_deploy_waits_for_each_quality_gate(gate):
    workflow = yaml.safe_load(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))
    jobs = workflow['jobs']
    assert gate in jobs
    assert gate in jobs['deploy']['needs']


def test_dependency_audit_failure_cannot_be_bypassed_by_production_deploy():
    workflow = yaml.safe_load(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))
    audit = workflow['jobs']['dependency-audit']
    deploy = workflow['jobs']['deploy']
    assert 'dependency-audit' in deploy['needs']
    assert audit.get('continue-on-error', False) is False
    assert all(step.get('continue-on-error', False) is False for step in audit['steps'])
    # This condition retains GitHub's implicit success() requirement for every needed job.
    assert deploy['if'] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"


@pytest.mark.parametrize('workflow', ['recover-hf-space.yml', 'harden-hf-space.yml'])
def test_space_recovery_checks_business_readiness(workflow, monkeypatch, tmp_path):
    import re
    import shlex
    import sys

    from scripts import workflow_http

    text = Path('.github/workflows', workflow).read_text(encoding='utf-8')
    assert 'actions/checkout@' in text
    assert '--policy read --path /health/ready' in text
    assert '"${SPACE_URL}/health/ready" -o /dev/null' not in text
    command = re.search(r'python3 scripts/workflow_http.py (.*?); then', text, re.DOTALL)
    assert command is not None
    args = shlex.split(command.group(1).replace('\\\n', ''))
    args[args.index('--report') + 1] = str(tmp_path / 'readiness.json')
    monkeypatch.setenv('BASE_URL', 'https://example.invalid')
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['workflow_http', *args])
    monkeypatch.setattr(workflow_http, 'run_request', lambda *a, **k: workflow_http.Result('succeeded', 1))
    assert workflow_http.main() == 0


def test_skipped_sync_is_reported_without_claiming_completion():
    result = run_request(
        'https://example.invalid/api/cron/trigger-new-books-sync',
        policy='submit',
        transport=lambda *args, **kwargs: Reply(0, 200, b'{"success":true,"data":{"status":"skipped"}}'),
    )
    assert result.state == 'skipped'
    assert result.exit_code == 0


def test_read_first_timeout_then_success():
    calls = []
    replies = iter([Reply(28, 0), Reply(0, 200, b'{"success": true,"status":"ready"}')])
    sleeps = []

    def transport(*args, **kwargs):
        calls.append(kwargs)
        return next(replies)

    result = run_request('https://example.invalid/health/ready', transport=transport, sleep=sleeps.append)
    assert result.state == 'succeeded'
    assert result.attempts == 2
    assert sleeps == [5]


def test_read_exhausted_retries():
    result = run_request(
        'https://example.invalid/health/ready', transport=lambda *a, **k: Reply(28, 0), sleep=lambda n: None
    )
    assert result.state == 'failed'
    assert result.attempts == 3
    assert result.transport_code == 28


def test_side_effecting_get_response_lost_does_not_resubmit():
    calls = []

    def executed_then_lost(*args, **kwargs):
        calls.append('backend executed')
        return Reply(28, 0)

    result = run_request(
        'https://example.invalid/api/cron/trigger-new-books-sync', policy='submit', transport=executed_then_lost
    )
    assert calls == ['backend executed']
    assert result.state == 'pending_verification'
    assert result.attempts == 1


def test_batch_response_lost_reuses_identical_body_and_id():
    body = b'{"batch_id":"harpercollins:fixed", "records":[]}'
    calls = []

    def import_batch(*args, **kwargs):
        calls.append(kwargs['body'])
        if len(calls) == 1:
            return Reply(28, 0)
        return Reply(0, 200, b'{"success":true,"data":{"status":"duplicate","batch_id":"harpercollins:fixed"}}')

    result = run_request(
        'https://example.invalid/api/new-books/import-batch',
        policy='batch',
        method='POST',
        body=body,
        transport=import_batch,
        sleep=lambda n: None,
    )
    assert result.state == 'succeeded'
    assert calls == [body, body]


def test_exhausted_batch_unknown_is_not_confirmed_failure():
    result = run_request(
        'https://example.invalid/api/new-books/import-batch',
        policy='batch',
        method='POST',
        body=b'{"batch_id":"fixed"}',
        transport=lambda *a, **k: Reply(28, 0),
        sleep=lambda n: None,
    )
    assert result.state == 'pending_verification'
    assert result.attempts == 3


@pytest.mark.parametrize('reply', [Reply(0, 401), Reply(0, 403), Reply(0, 409), Reply(0, 200, b'{"success":false}')])
def test_auth_http_and_business_failure_not_retried(reply):
    result = run_request('https://example.invalid/api/test', transport=lambda *a, **k: reply)
    assert result.state == 'failed'
    assert result.attempts == 1


def test_unsafe_http_server_failure_remains_pending():
    result = run_request(
        'https://example.invalid/api/cron/task', policy='submit', transport=lambda *a, **k: Reply(0, 504)
    )
    assert result.state == 'pending_verification'
    assert result.http_status == 504


def test_budget_caps_timeout_and_avoids_backoff_past_deadline():
    times = iter([0, 0, 2])
    timeouts = []

    def timeout(*args, **kwargs):
        timeouts.append(kwargs['timeout'])
        return Reply(28, 0)

    result = run_request(
        'https://example.invalid/health/ready', budget=3, timeout=20, clock=lambda: next(times), transport=timeout
    )
    assert result.state == 'failed'
    assert result.attempts == 1
    assert timeouts == [3]


def test_alert_transport_failure_not_reported_delivered():
    result = run_request(
        'https://example.invalid/notify', policy='notify', method='POST', transport=lambda *a, **k: Reply(28, 0)
    )
    assert result.state == 'not_delivered'
    assert result.exit_code == 0
    assert result.attempts == 1


def test_unconfigured_alert_reports_not_sent_without_network():
    result = run_request('', policy='notify', transport=lambda *a, **k: pytest.fail('must not call network'))
    assert result.state == 'not_configured'
    assert result.exit_code == 0


def test_issue_body_bounded_with_artifact_link():
    result = truncate_issue('x' * 80000, 'https://github.com/example/actions/runs/1')
    assert len(result.encode('utf-8')) <= 12000
    assert 'actions/runs/1' in result
    assert '完整日志' in result


def test_curl_timeout_is_classified_and_stderr_not_exposed(monkeypatch):
    from scripts.workflow_http import curl_transport

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('curl', 1, stderr=b'secret')

    monkeypatch.setattr(subprocess, 'run', timeout)
    reply = curl_transport('https://example.invalid', timeout=1, method='GET', headers={}, body=None)
    assert reply == Reply(28, 0)


def test_workflows_use_explicit_submit_policy_and_no_direct_data_push():
    for name in ['trigger-new-books-sync.yml', 'trigger-award-cover-sync.yml', 'trigger-weekly-report.yml']:
        text = Path('.github/workflows', name).read_text(encoding='utf-8')
        assert '--policy submit' in text
        assert 'HTTP_CODE=$(curl' not in text
        assert 'cancel-in-progress: false' in text
    pipeline = Path('.github/workflows/site-crawl-pipeline.yml').read_text(encoding='utf-8')
    assert '--policy batch' in pipeline
    assert 'always() &&' in pipeline
    update = Path('.github/workflows/update-books.yml').read_text(encoding='utf-8')
    assert 'git push' not in update
    assert 'contents: read' in update


def test_submit_acknowledgement_means_accepted_not_task_complete():
    result = run_request(
        'https://example.invalid/api/cron/task',
        policy='submit',
        transport=lambda *a, **k: Reply(0, 200, b'{"success":true,"data":{"status":"started"}}'),
    )
    assert result.state == 'accepted'
    assert result.exit_code == 0


@pytest.mark.parametrize(
    'body',
    [b'', b'{}', b'<html>gateway</html>', b'null', b'{"success":1}', b'{"success":true,"status":"not_ready"}'],
)
def test_readiness_requires_a_business_acknowledgement(body):
    result = run_request('https://example.invalid/health/ready', transport=lambda *a, **k: Reply(0, 200, body))
    assert result.state == 'failed'
    assert result.exit_code == 1


@pytest.mark.parametrize('status', ['already_running', 'running'])
def test_existing_background_task_is_reported_as_running(status):
    body = json.dumps({'success': True, 'data': {'status': status}}).encode()
    result = run_request(
        'https://example.invalid/api/cron/task', policy='submit', transport=lambda *a, **k: Reply(0, 200, body)
    )
    assert result.state == 'running'
    assert result.exit_code == 0
    assert result.attempts == 1


@pytest.mark.parametrize('status', ['failed', 'partial', 'error'])
def test_submit_cannot_accept_an_explicit_failed_task(status):
    body = json.dumps({'success': True, 'data': {'status': status}}).encode()
    result = run_request(
        'https://example.invalid/api/cron/task', policy='submit', transport=lambda *a, **k: Reply(0, 200, body)
    )
    assert result.state == 'failed'
    assert result.exit_code == 1


def test_submit_requires_explicit_completion_before_reporting_succeeded():
    result = run_request(
        'https://example.invalid/api/cron/task',
        policy='submit',
        transport=lambda *a, **k: Reply(0, 200, b'{"success":true,"data":{"status":"completed"}}'),
    )
    assert result.state == 'succeeded'
    assert result.reason == 'backend_task_completed'


@pytest.mark.parametrize('success', [True, False])
def test_submit_preserves_backend_pending_without_resubmission(success):
    calls = []

    def pending_backend(*args, **kwargs):
        calls.append(kwargs)
        return Reply(0, 200, json.dumps({'success': success, 'data': {'status': 'pending_verification'}}).encode())

    result = run_request('https://example.invalid/api/cron/task', policy='submit', transport=pending_backend)
    assert result.state == 'pending_verification'
    assert result.exit_code == 2
    assert result.attempts == 1
    assert len(calls) == 1


def test_alert_business_failure_not_delivered():
    result = run_request(
        'https://example.invalid/notify',
        policy='notify',
        method='POST',
        transport=lambda *a, **k: Reply(0, 200, b'{"code":19002,"msg":"signature rejected"}'),
    )
    assert result.state == 'not_delivered'


def test_later_rejection_does_not_resolve_lost_batch_acknowledgement():
    replies = iter([Reply(28, 0), Reply(0, 401)])
    result = run_request(
        'https://example.invalid/api/new-books/import-batch',
        policy='batch',
        method='POST',
        body=b'{"batch_id":"fixed"}',
        transport=lambda *a, **k: next(replies),
        sleep=lambda n: None,
    )
    assert result.state == 'pending_verification'


def test_lost_import_acknowledgement_resolves_using_real_persisted_receipt(app, client, db):
    import json

    from app.models.new_book import BatchImportReceipt, NewBook, Publisher
    from tests.test_batch_import import _valid_batch

    app.config['BATCH_IMPORT_SECRET'] = 'workflow-test-import'
    publisher = Publisher(
        name='HarperCollins',
        name_en='HarperCollins',
        crawler_class='HarperCollinsGoogleCrawler',
        is_active=True,
        site_import_enabled=True,
        site_display_primary=True,
    )
    db.session.add(publisher)
    db.session.commit()
    body = json.dumps(_valid_batch()).encode('utf-8')
    calls = []

    def transport(url, **kwargs):
        calls.append(kwargs['body'])
        response = client.post(
            '/api/new-books/import-batch',
            data=kwargs['body'],
            content_type='application/json',
            headers={'Authorization': 'Bearer workflow-test-import'},
        )
        assert response.status_code == 200
        if len(calls) == 1:
            assert response.get_json()['data']['status'] == 'applied'
            return Reply(28, 0)
        assert response.get_json()['data']['status'] == 'duplicate'
        return Reply(0, response.status_code, response.data)

    result = run_request(
        'https://example.invalid/api/new-books/import-batch',
        policy='batch',
        method='POST',
        body=body,
        transport=transport,
        sleep=lambda n: None,
    )
    assert result.state == 'succeeded'
    assert calls == [body, body]
    assert NewBook.query.filter_by(isbn13='9780063417113').count() == 1
    assert BatchImportReceipt.query.count() == 1


def test_lost_cron_reply_replayed_with_same_key_returns_completed_without_executing_again(
    app,
    client,
    db,
    monkeypatch,
):
    from datetime import date
    from types import SimpleNamespace
    from unittest.mock import Mock

    monkeypatch.setitem(app.config, 'CRON_SECRET', 'isolated-workflow-cron')
    report = SimpleNamespace(
        id=72,
        report_date=date(2026, 10, 21),
        week_start=date(2026, 10, 19),
        week_end=date(2026, 10, 25),
        title='Isolated workflow report',
    )
    generate = Mock(return_value=report)
    monkeypatch.setattr('app.tasks.weekly_report_task.generate_weekly_report', generate)
    calls = []

    def transport(url, **kwargs):
        calls.append(kwargs['headers']['X-Idempotency-Key'])
        response = client.get('/api/cron/trigger-weekly-report', headers=kwargs['headers'])
        assert response.status_code == 200
        if len(calls) == 1:
            assert response.get_json()['data']['status'] == 'completed'
            return Reply(28, 0)
        assert response.get_json()['data']['replayed'] is True
        return Reply(0, response.status_code, response.data)

    arguments = {
        'policy': 'submit',
        'headers': {'Authorization': 'Bearer isolated-workflow-cron', 'X-Idempotency-Key': 'stable-workflow-run'},
        'transport': transport,
    }
    first = run_request('https://example.invalid/api/cron/trigger-weekly-report', **arguments)
    assert first.state == 'pending_verification'
    assert calls == ['stable-workflow-run']
    replay = run_request('https://example.invalid/api/cron/trigger-weekly-report', **arguments)
    assert replay.state == 'succeeded'
    assert replay.reason == 'backend_task_completed'
    assert calls == ['stable-workflow-run', 'stable-workflow-run']
    generate.assert_called_once()


@pytest.mark.parametrize('body', [b'', b'{}', b'<html>gateway</html>'])
def test_submit_without_valid_acknowledgement_remains_pending(body):
    result = run_request(
        'https://example.invalid/api/cron/task', policy='submit', transport=lambda *a, **k: Reply(0, 200, body)
    )
    assert result.state == 'pending_verification'


def test_unmatched_batch_receipt_does_not_resolve_unknown_outcome():
    result = run_request(
        'https://example.invalid/api/new-books/import-batch',
        policy='batch',
        method='POST',
        body=b'{"batch_id":"fixed"}',
        transport=lambda *a, **k: Reply(0, 200, b'{"success":true,"data":{"status":"duplicate","batch_id":"other"}}'),
    )
    assert result.state == 'pending_verification'


def test_cli_missing_alert_writes_explicit_delivery_status(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from scripts import workflow_http

    summary = tmp_path / 'summary.md'
    report = tmp_path / 'alert.json'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))
    monkeypatch.delenv('WORKFLOW_TEST_SECRET', raising=False)
    monkeypatch.setattr(
        sys,
        'argv',
        ['workflow_http', '--policy', 'notify', '--secret-env', 'WORKFLOW_TEST_SECRET', '--report', str(report)],
    )
    assert workflow_http.main() == 0
    assert json.loads(report.read_text(encoding='utf-8'))['state'] == 'not_configured'
    assert '告警未送达' in summary.read_text(encoding='utf-8')
    assert 'not_configured' in capsys.readouterr().out


def test_cli_acknowledgement_lost_records_pending_and_does_not_print_credentials(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from scripts import workflow_http

    report = tmp_path / 'submission.json'
    monkeypatch.setenv('BASE_URL', 'https://example.invalid')
    monkeypatch.setenv('WORKFLOW_TEST_SECRET', 'private-do-not-log')
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    monkeypatch.setattr(
        workflow_http, 'run_request', lambda *a, **k: workflow_http.Result('pending_verification', 1, transport_code=28)
    )
    monkeypatch.setattr(
        sys,
        'argv',
        ['workflow_http', '--policy', 'submit', '--secret-env', 'WORKFLOW_TEST_SECRET', '--report', str(report)],
    )
    assert workflow_http.main() == 2
    assert json.loads(report.read_text(encoding='utf-8'))['state'] == 'pending_verification'
    assert 'private-do-not-log' not in capsys.readouterr().out


def test_cli_submit_reuses_idempotency_key_across_attempts_but_not_different_runs(tmp_path, monkeypatch):
    import sys

    from scripts import workflow_http

    captured = []

    def submit(*args, **kwargs):
        captured.append(kwargs['headers']['X-Idempotency-Key'])
        return workflow_http.Result('accepted', 1)

    monkeypatch.setenv('GITHUB_REPOSITORY', 'example/bookrank')
    monkeypatch.setenv('GITHUB_RUN_ID', '1234')
    monkeypatch.setenv('BASE_URL', 'https://example.invalid')
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    monkeypatch.setattr(workflow_http, 'run_request', submit)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'workflow_http',
            '--policy',
            'submit',
            '--path',
            '/api/cron/trigger-new-books-sync',
            '--report',
            str(tmp_path / 'submit.json'),
        ],
    )
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    assert workflow_http.main() == 0
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    assert workflow_http.main() == 0
    monkeypatch.setenv('GITHUB_RUN_ID', '1235')
    assert workflow_http.main() == 0
    assert captured[0] == captured[1]
    assert captured[0] != captured[2]
    assert len(captured[0]) <= 200


@pytest.mark.parametrize(
    'status, body',
    [
        (200, b'<html>gateway failure</html>'),
        (200, b'not json'),
        (200, b'{}'),
        (200, b'[]'),
        (200, b'null'),
        (200, b'{"code":false}'),
        (200, b'{"StatusCode":false}'),
        (200, b'{"code":"0"}'),
        (200, b'{"success":1}'),
        (204, b''),
    ],
)
def test_notify_unrecognized_receipt_is_not_delivery(status, body):
    result = run_request(
        'https://example.invalid/notify',
        policy='notify',
        method='POST',
        transport=lambda *a, **k: Reply(0, status, body),
    )
    assert result.state == 'not_delivered'
    assert result.exit_code == 0
    assert result.attempts == 1


@pytest.mark.parametrize(
    'body', [b'{"success":true}', b'{"code":0,"msg":"success"}', b'{"StatusCode":0,"StatusMessage":"success"}']
)
def test_notify_explicit_supported_receipt_confirms_delivery(body):
    result = run_request(
        'https://example.invalid/notify', policy='notify', method='POST', transport=lambda *a, **k: Reply(0, 200, body)
    )
    assert result.state == 'succeeded'


@pytest.mark.parametrize(
    'delivery, expected',
    [
        ('not_configured', 'not_configured'),
        ('not_required', 'not_required'),
        ('not_delivered', 'not_delivered'),
        ('delivered', 'succeeded'),
    ],
)
def test_notify_api_success_respects_explicit_delivery_status(delivery, expected):
    import json

    body = json.dumps({'success': True, 'data': {'delivery': delivery}}).encode()
    result = run_request(
        'https://example.invalid/api/admin/new-books/source-alert/sync/harpercollins',
        policy='notify',
        method='POST',
        transport=lambda *a, **k: Reply(0, 200, body),
    )
    assert result.state == expected
    assert result.exit_code == 0


def test_monitor_delivery_step_conclusion_cannot_be_overridden_to_success():
    monitor = Path('.github/workflows/production-monitor.yml').read_text(encoding='utf-8')
    assert 'continue-on-error: true' not in monitor
    assert 'failure/success | timed_out/success | cancelled/success)' in monitor
