"""admin_auth 工具函数测试，覆盖 _cleanup_auth_failures 和持久化"""

import json
import time
from unittest.mock import patch

from app.utils import admin_auth
from app.utils.admin_auth import _AUTH_MAX_ENTRIES, _auth_failures, _cleanup_auth_failures


class TestCleanupAuthFailures:
    def test_no_cleanup_when_under_limit(self):
        # 添加少量记录
        _auth_failures['1.1.1.1'] = {'count': 1, 'blocked_until': 0}
        _auth_failures['2.2.2.2'] = {'count': 2, 'blocked_until': 0}
        before = len(_auth_failures)
        _cleanup_auth_failures(time.time())
        # 未达上限,不应清理
        assert len(_auth_failures) == before

    def test_cleans_expired_when_over_limit(self):
        # 模拟超过上限的情况
        now = time.time()
        # 添加已过期条目
        for i in range(_AUTH_MAX_ENTRIES + 5):
            _auth_failures[f'10.0.0.{i}'] = {'count': 5, 'blocked_until': now - 100}
        # 加几个仍在封禁中的
        for i in range(3):
            _auth_failures[f'20.0.0.{i}'] = {'count': 5, 'blocked_until': now + 1000}

        before = len(_auth_failures)
        assert before > _AUTH_MAX_ENTRIES

        _cleanup_auth_failures(now)

        # 已过期的应该被清理
        assert len(_auth_failures) < before
        # 仍在封禁中的保留
        for i in range(3):
            assert f'20.0.0.{i}' in _auth_failures

    def test_no_op_when_empty(self):
        _cleanup_auth_failures(time.time())
        assert len(_auth_failures) == 0


class TestLoadPersistedFailures:
    def test_skips_when_already_loaded(self):
        admin_auth._persist_loaded = True
        # 不应触发任何 DB 调用
        with patch('app.models.schemas.SystemConfig') as mock_sc:
            admin_auth._load_persisted_failures()
            mock_sc.get_value.assert_not_called()

    def test_loads_active_blocks_from_persisted(self, app):
        """从 SystemConfig 加载尚未过期的封禁状态

        不显式声明 db fixture 以保持与基线行为一致（依赖 session app
        的 create_all 副作用，在测试顺序敏感时不稳定）。这是预先存在的
        测试设计——不在本次重构范围内修改。
        """
        import json

        with app.app_context():
            from app.models import db
            from app.models.schemas import SystemConfig

            now = time.time()
            payload = {
                '1.1.1.1': {'count': 5, 'blocked_until': now + 1000},  # 仍封禁
                '2.2.2.2': {'count': 5, 'blocked_until': now - 1000},  # 已过期
                '3.3.3.3': {'count': 1, 'blocked_until': 0},  # 仍有失败计数
            }
            SystemConfig.set_value('admin_auth_failures', json.dumps(payload))
            db.session.commit()

            admin_auth._persist_loaded = False
            _auth_failures.clear()
            admin_auth._load_persisted_failures()

            # 1.1.1.1 应该被加载（仍封禁中）
            assert '1.1.1.1' in _auth_failures
            # 3.3.3.3 也应该被加载（count > 0）
            assert '3.3.3.3' in _auth_failures


class TestPersistSubThresholdFailures:
    """安全审计 Low #9：未达封禁阈值的失败计数必须能跨重启存活。

    原实现只在达到 5 次阈值时才落盘，且仅写 blocked_until > now 的条目，
    于是 1~4 次的中间计数在重启/重新部署后清零，5 次封禁阈值永远无法触发
    ——攻击者只需要在被封禁前让应用重启一次即可。
    """

    def _read_persisted(self, app) -> dict:
        with app.app_context():
            from app.models.schemas import SystemConfig

            raw = SystemConfig.get_value('admin_auth_failures')
            return json.loads(raw) if raw else {}

    def test_persists_failures_below_block_threshold(self, app, db):
        _auth_failures['9.9.9.9'] = {'count': 2, 'blocked_until': 0, 'last_failure': time.time()}

        with app.app_context():
            admin_auth._persist_failures()

        saved = self._read_persisted(app)
        assert '9.9.9.9' in saved, '未达阈值的失败计数也必须落盘'
        assert saved['9.9.9.9']['count'] == 2

    def test_drops_stale_failures_past_retention(self, app, db):
        stale = time.time() - (admin_auth._AUTH_FAILURE_RETENTION_SECONDS + 60)
        _auth_failures['8.8.8.8'] = {'count': 2, 'blocked_until': 0, 'last_failure': stale}

        with app.app_context():
            admin_auth._persist_failures()

        assert '8.8.8.8' not in self._read_persisted(app), '超过保留时长的历史失败不应复活'

    def test_restart_restores_sub_threshold_counts(self, app, db):
        """模拟重启：count=4（未封禁）必须能恢复，否则阈值永远无法达成。"""
        _auth_failures['7.7.7.7'] = {'count': 4, 'blocked_until': 0, 'last_failure': time.time()}

        with app.app_context():
            admin_auth._persist_failures()

            # 模拟进程重启：内存状态清零、持久化标记复位
            _auth_failures.clear()
            admin_auth._persist_loaded = False
            admin_auth._load_persisted_failures()

        assert _auth_failures['7.7.7.7']['count'] == 4
        assert _auth_failures['7.7.7.7']['blocked_until'] == 0

    def test_legacy_snapshot_without_last_failure_still_loads(self, app, db):
        """改造前写入的快照没有 last_failure 字段，升级后必须仍能加载。"""
        with app.app_context():
            from app.models import db as _db
            from app.models.schemas import SystemConfig

            SystemConfig.set_value('admin_auth_failures', json.dumps({'6.6.6.6': {'count': 1, 'blocked_until': 0}}))
            _db.session.commit()

            _auth_failures.clear()
            admin_auth._persist_loaded = False
            admin_auth._load_persisted_failures()

        assert _auth_failures['6.6.6.6']['count'] == 1
