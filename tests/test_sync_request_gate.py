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
    def test_seeds_once_per_gate(self):
        calls = []

        class CountingEngine:
            def ensure_static_data_seeded(self):
                calls.append(1)

        gate = SyncRequestGate()
        gate.seed_static_data(CountingEngine())
        gate.seed_static_data(CountingEngine())
        assert calls == [1]

    def test_seed_error_propagates_and_flag_stays_false(self, gate):
        class BoomEngine:
            def ensure_static_data_seeded(self):
                raise RuntimeError('boom')

        with pytest.raises(RuntimeError):
            gate.seed_static_data(BoomEngine())

        # 失败未置位：下次仍会重试
        calls = []

        class CountingEngine:
            def ensure_static_data_seeded(self):
                calls.append(1)

        gate.seed_static_data(CountingEngine())
        assert calls == [1]
