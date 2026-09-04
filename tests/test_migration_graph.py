"""Regression checks for the Alembic revision graph."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_exactly_one_head():
    """Production upgrades must never be ambiguous."""
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ['add_perf_indexes']
