"""Crawler drift detector tests (ROADMAP #2; pure-function)."""

from app.services.crawler_drift_detector import detect_drift, drift_report


def _obs(name, status):
    return {'publisher': name, 'status': status}


class TestDetectDrift:
    def test_empty_results(self):
        assert detect_drift([]) == []

    def test_healthy_no_candidates(self):
        results = [_obs('A', 'success'), _obs('B', 'success')]
        assert detect_drift(results) == []

    def test_single_failure_not_flagged(self):
        results = [_obs('A', 'success'), _obs('A', 'timeout')]
        assert detect_drift(results) == []

    def test_two_failures_flagged(self):
        results = [_obs('A', 'empty'), _obs('A', 'timeout')]
        cands = detect_drift(results)
        assert len(cands) == 1
        assert cands[0].publisher == 'A'
        assert any('2/2' in r for r in cands[0].reasons)

    def test_mixed_publishers(self):
        results = [
            _obs('A', 'empty'),
            _obs('A', 'request_failed'),
            _obs('B', 'success'),
            _obs('B', 'success'),
        ]
        cands = detect_drift(results)
        assert [c.publisher for c in cands] == ['A']

    def test_last_empty_single_flagged(self):
        results = [_obs('A', 'success'), _obs('A', 'empty')]
        cands = detect_drift(results)
        assert len(cands) == 1
        assert '空结果' in cands[0].reasons[0]

    def test_last_empty_not_flagged_when_wrong_position(self):
        results = [_obs('A', 'empty'), _obs('A', 'success')]
        assert detect_drift(results) == []


class TestDriftReport:
    def test_no_result_configured(self, app, db):
        from app.models.schemas import SystemConfig

        SystemConfig.set_value('last_auto_sync_result', '')
        db.session.commit()
        report = drift_report()
        assert report['drifted'] == []
        assert report['total_publishers'] == 0
