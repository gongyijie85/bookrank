"""Regression checks for the Alembic revision graph."""

import subprocess
import sys
import textwrap
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_exactly_one_head():
    """Production upgrades must never be ambiguous."""
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ['add_list_snapshots']


def test_migration_keeps_translation_logger_enabled():
    """A production migration must not suppress later translation failures."""
    script = textwrap.dedent(
        """
        import logging

        from flask import Flask
        from flask_migrate import Migrate, stamp
        from flask_sqlalchemy import SQLAlchemy

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        database = SQLAlchemy(app)
        Migrate(app, database)
        logger = logging.getLogger('app.services.zhipu_translation_service')
        logger.disabled = False

        with app.app_context():
            stamp()

        assert not logger.disabled, 'migration disabled the translation logger'
        logger.warning('translation diagnostic survives migration')
        """
    )
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert 'translation diagnostic survives migration' in result.stderr
