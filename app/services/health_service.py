"""只读健康检查；不迁移、不播种、不访问外部 API。"""

from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from flask import current_app

from ..models.database import db


class SchemaNotReady(RuntimeError):
    """数据库未完成当前发布要求的迁移。"""


@lru_cache(maxsize=1)
def _schema_heads() -> frozenset[str]:
    migrations = Path(__file__).resolve().parents[2] / 'migrations'
    return frozenset(ScriptDirectory(str(migrations)).get_heads())


def check_database() -> None:
    """快速探测连接；生产另校验版本，不扫描业务数据。"""
    db.session.execute(db.text('SELECT 1'))
    if current_app.config.get('APP_ENV') == 'production':
        try:
            versions = frozenset(db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalars())
        except Exception as exc:
            db.session.rollback()
            raise SchemaNotReady('schema_version_unavailable') from exc
        if versions != _schema_heads():
            raise SchemaNotReady('schema_version_mismatch')
