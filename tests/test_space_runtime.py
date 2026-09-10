"""HuggingFace Space 运行时开关与首屏阻塞防护测试。"""

from unittest.mock import Mock

import run as run_module
from app.utils.space_runtime import is_space_runtime


def test_is_space_runtime_reads_hf_injected_variable(monkeypatch):
    monkeypatch.delenv('SPACE_ID', raising=False)
    assert is_space_runtime() is False

    monkeypatch.setenv('SPACE_ID', 'Elvis85/bookrank')
    assert is_space_runtime() is True


def _fake_db_with_existing_version(monkeypatch):
    fake_db = Mock()
    fake_db.session.execute.return_value.fetchone.return_value = ('headrev',)
    monkeypatch.setattr(run_module, 'db', fake_db)
    return fake_db


def test_run_migrations_skips_upgrade_on_space(monkeypatch):
    monkeypatch.setenv('SPACE_ID', 'Elvis85/bookrank')
    upgrade = Mock()
    monkeypatch.setattr('flask_migrate.upgrade', upgrade)
    _fake_db_with_existing_version(monkeypatch)

    assert run_module._run_migrations() is True
    upgrade.assert_not_called()


def test_run_migrations_upgrades_off_space(monkeypatch):
    monkeypatch.delenv('SPACE_ID', raising=False)
    upgrade = Mock()
    monkeypatch.setattr('flask_migrate.upgrade', upgrade)
    _fake_db_with_existing_version(monkeypatch)

    assert run_module._run_migrations() is True
    upgrade.assert_called_once_with()
