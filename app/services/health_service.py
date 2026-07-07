"""健康检查服务"""

import logging

from ..models.database import db

logger = logging.getLogger(__name__)


class HealthService:
    """健康检查服务：封装基础设施探测逻辑"""

    @staticmethod
    def check_database() -> None:
        """检查数据库连通性，失败时抛出异常"""
        db.session.execute(db.text('SELECT 1'))
