"""健康检查服务"""

from ..models.database import db


def check_database() -> None:
    """检查数据库连通性，失败时抛出异常"""
    db.session.execute(db.text('SELECT 1'))
