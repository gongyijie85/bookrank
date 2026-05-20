from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()


def init_db(app):
    """初始化数据库"""
    db.init_app(app)
    migrate.init_app(app, db)

    if app.config.get('APP_ENV') == 'production':
        return

    with app.app_context():
        db.create_all()
