"""admin_auth 工具函数测试，覆盖 _cleanup_auth_failures 和持久化"""

import time
from unittest.mock import patch

import pytest

from app.utils import admin_auth
from app.utils.admin_auth import _AUTH_MAX_ENTRIES, _auth_failures, _cleanup_auth_failures


@pytest.fixture(autouse=True)
def _clear_auth_failures(clear_auth_failures):
    """将 conftest 的 clear_auth_failures 设为 autouse（仅本文件生效）。

    _auth_failures / _persist_loaded 是 admin_auth 模块级全局状态，
    本文件的测试用例之间需要互不污染，所以用 autouse 包装一层。
    实际清理逻辑统一来自 conftest.clear_auth_failures（单一来源）。

    注意：_persist_loaded 故意**不**重置，参见 conftest.clear_auth_failures 注释。
    """


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
