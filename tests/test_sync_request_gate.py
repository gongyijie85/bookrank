"""同步请求闸门测试（候选 #5）"""

import time

import pytest

from app.services.sync_request_gate import SyncRequestGate


@pytest.fixture
def gate():
    return SyncRequestGate()


class TestSyncCooldown:
    def test_initial_state_not_in_cooldown(self, gate):
        assert gate.sync_cooldown_remaining() is None

    def test_record_sync_enters_cooldown(self, gate):
        gate.record_sync()
        remaining = gate.sync_cooldown_remaining()
        assert remaining is not None
        assert 0 < remaining <= 60

    def test_cooldown_expires_after_window(self, gate, monkeypatch):
        gate.record_sync()
        later = time.time() + 61
        with monkeypatch.context() as m:
            m.setattr('app.services.sync_request_gate.time.time', lambda: later)
            assert gate.sync_cooldown_remaining() is None


class TestTryAcquireSync:
    """v0.9.99: 原子检查+记录（性能评审 #8：消除冷却竞态窗口）"""

    def test_first_acquire_passes_and_records(self, gate):
        assert gate.try_acquire_sync() is None
        # 已记录：紧接着的检查命中冷却
        assert gate.sync_cooldown_remaining() is not None

    def test_second_acquire_within_cooldown_returns_remaining(self, gate):
        gate.try_acquire_sync()
        remaining = gate.try_acquire_sync()
        assert remaining is not None
        assert 0 < remaining <= 60

    def test_acquire_after_window_passes_again(self, gate, monkeypatch):
        gate.try_acquire_sync()
        later = time.time() + 61
        with monkeypatch.context() as m:
            m.setattr('app.services.sync_request_gate.time.time', lambda: later)
            assert gate.try_acquire_sync() is None

    def test_concurrent_acquires_only_one_passes(self, gate):
        """并发线程同时 acquire：仅一个通过，其余拿到剩余秒数。"""
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: gate.try_acquire_sync(), range(8)))

        passed = [r for r in results if r is None]
        blocked = [r for r in results if r is not None]
        assert len(passed) == 1
        assert len(blocked) == 7


class TestExportCooldown:
    def test_first_export_ok_then_blocked(self, gate):
        assert gate.export_cooldown_remaining('1.2.3.4') is None
        remaining = gate.export_cooldown_remaining('1.2.3.4')
        assert remaining is not None
        assert 0 < remaining <= 10

    def test_per_ip_independent(self, gate):
        assert gate.export_cooldown_remaining('1.2.3.4') is None
        assert gate.export_cooldown_remaining('5.6.7.8') is None

    def test_expired_entries_cleaned(self, gate, monkeypatch):
        gate.export_cooldown_remaining('1.2.3.4')
        later = time.time() + 11
        with monkeypatch.context() as m:
            m.setattr('app.services.sync_request_gate.time.time', lambda: later)
            gate.export_cooldown_remaining('9.9.9.9')  # 触发惰性清理
        assert '1.2.3.4' not in gate._export_last_at
        assert '9.9.9.9' in gate._export_last_at


class TestSeedStaticData:
    @pytest.mark.parametrize('testing', [False, True])
    def test_production_never_runs_automatic_seeding(self, gate, testing):
        from unittest.mock import Mock

        from flask import Flask

        app = Flask(__name__)
        app.config.update(APP_ENV='production', TESTING=testing)
        engine = Mock()
        with app.app_context():
            gate.seed_static_data(engine)
            gate.seed_static_data(engine)
        engine.ensure_static_data_seeded.assert_not_called()

    def test_seeds_once_per_gate(self):
        calls = []

        class CountingEngine:
            def ensure_static_data_seeded(self):
                calls.append(1)

        gate = SyncRequestGate()
        gate.seed_static_data(CountingEngine())
        gate.seed_static_data(CountingEngine())
        assert calls == [1]

    def test_failed_result_is_retryable_after_short_cooldown(self, gate, monkeypatch):
        now = [100.0]
        monkeypatch.setattr('app.services.sync_request_gate.time.monotonic', lambda: now[0])
        calls = []

        class EmptyEngine:
            def ensure_static_data_seeded(self):
                calls.append(1)
                return {'success': False, 'status': 'empty'}

        gate.seed_static_data(EmptyEngine())
        assert gate._seed_done is False
        gate.seed_static_data(EmptyEngine())
        assert calls == [1]
        now[0] += 61
        gate.seed_static_data(EmptyEngine())
        assert calls == [1, 1]

    def test_seed_exception_is_also_throttled_without_marking_done(self, gate, monkeypatch):
        from unittest.mock import Mock

        now = [100.0]
        monkeypatch.setattr('app.services.sync_request_gate.time.monotonic', lambda: now[0])
        engine = Mock()
        engine.ensure_static_data_seeded.side_effect = [RuntimeError('failed'), None]
        with pytest.raises(RuntimeError):
            gate.seed_static_data(engine)
        gate.seed_static_data(engine)
        assert engine.ensure_static_data_seeded.call_count == 1
        assert gate._seed_done is False
        now[0] += 61
        gate.seed_static_data(engine)
        assert engine.ensure_static_data_seeded.call_count == 2
        assert gate._seed_done is True

    def test_seed_error_propagates_and_flag_stays_false(self, gate, monkeypatch):
        now = [100.0]
        monkeypatch.setattr('app.services.sync_request_gate.time.monotonic', lambda: now[0])

        class BoomEngine:
            def ensure_static_data_seeded(self):
                raise RuntimeError('boom')

        with pytest.raises(RuntimeError):
            gate.seed_static_data(BoomEngine())

        # 失败未置位，但冷却期内不让每个业务请求再次尝试。
        calls = []

        class CountingEngine:
            def ensure_static_data_seeded(self):
                calls.append(1)

        gate.seed_static_data(CountingEngine())
        assert calls == []
        now[0] += 61
        gate.seed_static_data(CountingEngine())
        assert calls == [1]
