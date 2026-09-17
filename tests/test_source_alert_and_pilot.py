"""Issues #139 source alert issues and #140 pilot gates / rollback drill."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.models.new_book import Publisher
from app.models.schemas import SystemConfig
from app.services import pilot_gate_service, source_alert_service, source_control_service, source_health_service


def _clear_evidence(db, source_id: str) -> None:
    SystemConfig.query.filter_by(key=f'pilot_evidence:{source_id}').delete()
    db.session.commit()


class FakeGithubIssues:
    def __init__(self) -> None:
        self.issues: list[dict[str, Any]] = []
        self.comments: list[tuple[int, str]] = []
        self.closed: list[int] = []
        self._next = 1000

    def find_open_by_title(self, title: str) -> dict[str, Any] | None:
        for issue in self.issues:
            if issue['title'] == title and issue['state'] == 'open':
                return issue
        return None

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        issue = {
            'number': self._next,
            'title': title,
            'body': body,
            'state': 'open',
            'labels': labels or [],
        }
        self._next += 1
        self.issues.append(issue)
        return issue

    def update_issue(self, number: int, body: str) -> None:
        for issue in self.issues:
            if issue['number'] == number:
                issue['body'] = body
                return
        raise KeyError(number)

    def add_comment(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def close_issue(self, number: int, comment: str | None = None) -> None:
        for issue in self.issues:
            if issue['number'] == number:
                issue['state'] = 'closed'
                self.closed.append(number)
                if comment:
                    self.comments.append((number, comment))
                return
        raise KeyError(number)


@pytest.fixture
def harper(app, db):
    pub = Publisher.query.filter_by(name_en='HarperCollins').first()
    if pub is None:
        pub = Publisher(
            name='哈珀柯林斯',
            name_en='HarperCollins',
            crawler_class='HarperCollinsGoogleCrawler',
            is_active=True,
        )
        db.session.add(pub)
        db.session.commit()
    pub.source_status = 'healthy'
    pub.consecutive_failures = 0
    pub.consecutive_successes = 0
    pub.last_success_batch_id = 'harpercollins:keep-me'
    pub.site_import_enabled = True
    pub.site_display_primary = False
    pub.fallback_google_enabled = True
    db.session.commit()
    return pub


@pytest.fixture
def fake_gh(monkeypatch):
    client = FakeGithubIssues()
    monkeypatch.setattr(source_alert_service, 'get_github_client', lambda: client)
    # 性能#7 后 GitHub 告警走后台线程；测试同步直调保持断言语义
    monkeypatch.setattr(source_health_service, '_dispatch_alert_async', source_health_service._run_alert_job)
    return client


def test_degraded_opens_stable_title_issue(app, db, harper, fake_gh):
    for _ in range(3):
        source_health_service.record_plan_failure(
            'harpercollins',
            error_code='EXPIRED',
            error_summary='batch expired',
        )
    assert len(fake_gh.issues) == 1
    issue = fake_gh.issues[0]
    assert issue['title'] == '[source-degraded] harpercollins'
    assert issue['state'] == 'open'
    assert 'EXPIRED' in issue['body']
    assert 'harpercollins:keep-me' in issue['body']
    assert 'BATCH_IMPORT_SECRET' not in issue['body']


def test_still_degraded_updates_not_spam_new_issues(app, db, harper, fake_gh):
    for _ in range(3):
        source_health_service.record_plan_failure('harpercollins', error_code='E1', error_summary='a')
    for _ in range(2):
        source_health_service.record_plan_failure('harpercollins', error_code='E2', error_summary='b')
    assert len(fake_gh.issues) == 1
    assert fake_gh.issues[0]['body'].count('E2') >= 1 or 'E2' in fake_gh.issues[0]['body']


def test_recover_to_healthy_closes_issue(app, db, harper, fake_gh):
    for _ in range(3):
        source_health_service.record_plan_failure('harpercollins', error_code='E', error_summary='x')
    number = fake_gh.issues[0]['number']
    source_health_service.record_plan_success('harpercollins', batch_id='b1')
    source_health_service.record_plan_success('harpercollins', batch_id='b2')
    assert number in fake_gh.closed
    assert fake_gh.issues[0]['state'] == 'closed'
    assert any('恢复' in c[1] or 'recover' in c[1].lower() or 'healthy' in c[1].lower() for c in fake_gh.comments)


def test_disabled_not_auto_closed_by_success(app, db, harper, fake_gh):
    # open an alert manually while disabled
    title = source_alert_service.alert_title('harpercollins')
    issue = fake_gh.create_issue(title, 'disabled alert')
    harper.source_status = 'disabled'
    db.session.commit()
    source_health_service.record_plan_success('harpercollins', batch_id='bx')
    source_health_service.record_plan_success('harpercollins', batch_id='by')
    assert issue['state'] == 'open'
    assert issue['number'] not in fake_gh.closed


class TestAlertAsyncDispatch:
    """性能#7：GitHub 告警改后台派发，导入请求线程不等外部 API"""

    @pytest.fixture
    def captured_submit(self, monkeypatch):
        """捕获 submit_background_task 提交的 worker（不执行），并注入 fake GitHub client。"""
        from app.utils import service_helpers

        submitted: list = []

        def _fake_submit(fn, *args, **kwargs):
            submitted.append(fn)

        monkeypatch.setattr(service_helpers, 'submit_background_task', _fake_submit)
        client = FakeGithubIssues()
        monkeypatch.setattr(source_alert_service, 'get_github_client', lambda: client)
        return submitted, client

    def test_degraded_alert_runs_only_in_background(self, app, db, harper, captured_submit):
        """降级告警不在请求线程同步执行（导入 P99 不受 GitHub 抖动影响）。"""
        submitted, gh = captured_submit

        for _ in range(3):
            source_health_service.record_plan_failure('harpercollins', error_code='E', error_summary='x')

        # 前 2 次失败状态仍 healthy 不派发；第 3 次降级派发 1 个后台任务
        assert len(submitted) == 1
        # 请求线程返回时告警尚未触达 GitHub
        assert gh.issues == []

        # 后台任务执行：重查 publisher 后建 issue（不依赖派发时的 ORM 对象）
        submitted[0]()
        assert len(gh.issues) == 1
        assert gh.issues[0]['title'] == '[source-degraded] harpercollins'

    def test_recovered_alert_closes_in_background(self, app, db, harper, captured_submit):
        """恢复 healthy 的关闭告警同样后台执行，且以执行时刻状态为准。"""
        submitted, gh = captured_submit

        for _ in range(3):
            source_health_service.record_plan_failure('harpercollins', error_code='E', error_summary='x')
        submitted[0]()  # 后台建 issue
        number = gh.issues[0]['number']
        assert gh.issues[0]['state'] == 'open'

        source_health_service.record_plan_success('harpercollins', batch_id='b1')
        source_health_service.record_plan_success('harpercollins', batch_id='b2')
        # 第一次 success：degraded → recovering，不派发；第二次：→ healthy，派发关闭
        assert len(submitted) == 2

        submitted[1]()
        assert number in gh.closed
        assert gh.issues[0]['state'] == 'closed'

    def test_recovered_worker_skips_when_status_flipped_back(self, app, db, harper, captured_submit):
        """派发与执行之间状态又翻回 degraded 时，陈旧的关闭任务被守卫挡下。"""
        submitted, gh = captured_submit

        for _ in range(3):
            source_health_service.record_plan_failure('harpercollins', error_code='E', error_summary='x')
        submitted[0]()
        assert gh.issues[0]['state'] == 'open'

        source_health_service.record_plan_success('harpercollins', batch_id='b1')
        source_health_service.record_plan_success('harpercollins', batch_id='b2')
        assert len(submitted) == 2

        # 执行前状态又翻回 degraded（3 次新失败）
        for _ in range(3):
            source_health_service.record_plan_failure('harpercollins', error_code='E2', error_summary='y')
        submitted[1]()  # 陈旧的 recovered 任务：healthy 守卫不通过 → 不关闭

        assert gh.issues[0]['state'] == 'open'
        assert gh.closed == []


def test_pilot_gates_require_volume_and_success_rate(app, db, harper):
    _clear_evidence(db, 'harpercollins')
    # only 5 runs
    for i in range(5):
        pilot_gate_service.record_evidence_run(
            'harpercollins',
            success=True,
            batch_id=f'b{i}',
            at=datetime.now(UTC) - timedelta(days=i),
        )
    report = pilot_gate_service.evaluate_gates('harpercollins')
    assert report['passed'] is False
    assert any('10' in r or '运行' in r for r in report['failures'])


def test_pilot_gates_pass_with_enough_history(app, db, harper):
    _clear_evidence(db, 'harpercollins')
    pilot_gate_service.set_compliance_go('harpercollins', True, actor='test')
    base = datetime.now(UTC)
    for i in range(14):
        pilot_gate_service.record_evidence_run(
            'harpercollins',
            success=True,
            batch_id=f'ok{i}',
            at=base - timedelta(days=13 - i),
        )
    # one failure only (still >=80% success)
    pilot_gate_service.record_evidence_run(
        'harpercollins',
        success=False,
        batch_id='fail1',
        error_code='EXPIRED',
        at=base - timedelta(hours=12),
    )
    report = pilot_gate_service.evaluate_gates('harpercollins')
    assert report['metrics']['planned_runs'] >= 10
    assert report['metrics']['success_rate'] >= 0.8
    assert report['passed'] is True


def test_display_primary_requires_compliance_and_gates(app, db, harper):
    _clear_evidence(db, 'harpercollins')
    pilot_gate_service.set_compliance_go('harpercollins', False, actor='test')
    allowed, reason = pilot_gate_service.can_enable_display_primary('harpercollins')
    assert allowed is False
    assert '合规' in reason or 'GO' in reason or 'compliance' in reason.lower()

    pilot_gate_service.set_compliance_go('harpercollins', True, actor='test')
    base = datetime.now(UTC)
    for i in range(14):
        pilot_gate_service.record_evidence_run(
            'harpercollins',
            success=True,
            batch_id=f'g{i}',
            at=base - timedelta(days=13 - i),
        )
    # still need drill
    allowed_mid, reason_mid = pilot_gate_service.can_enable_display_primary('harpercollins')
    assert allowed_mid is False
    pilot_gate_service.run_rollback_drill('harpercollins', actor='test')
    allowed2, _ = pilot_gate_service.can_enable_display_primary('harpercollins')
    assert allowed2 is True


def test_rollback_drill_no_redeploy(app, db, harper):
    source_control_service.set_flags(
        'harpercollins',
        site_import_enabled=True,
        site_display_primary=True,
        fallback_google_enabled=True,
        actor='drill',
    )
    result = pilot_gate_service.run_rollback_drill('harpercollins', actor='drill')
    assert result['passed'] is True
    flags = source_control_service.get_flags('harpercollins')
    # drill restores import on, display remains off until gates re-enabled explicitly
    assert flags['site_display_primary'] is False
    assert flags['fallback_google_enabled'] is True
    assert flags['site_import_enabled'] is True
    evidence = pilot_gate_service.get_evidence_bundle('harpercollins')
    assert evidence['last_drill'] is not None


def test_admin_pilot_endpoints(client, app, db, harper):
    from app.utils import admin_auth

    admin_auth._auth_failures.clear()
    app.config['ADMIN_SECRET'] = 'admin-test-secret'
    headers = {'X-Admin-Secret': 'admin-test-secret'}

    r = client.get('/api/admin/new-books/pilot/harpercollins/evidence', headers=headers)
    assert r.status_code == 200
    assert 'evidence' in r.get_json()['data']

    r2 = client.get('/api/admin/new-books/pilot/harpercollins/gates', headers=headers)
    assert r2.status_code == 200
    assert 'passed' in r2.get_json()['data']

    r3 = client.post(
        '/api/admin/new-books/pilot/harpercollins/rollback-drill',
        headers=headers,
        json={'actor': 'tester'},
    )
    assert r3.status_code == 200
    assert r3.get_json()['data']['passed'] is True
