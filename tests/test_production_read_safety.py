"""生产配置的公共新书读取不得通过惰性兜底写库。"""

import json
from unittest.mock import Mock

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app import create_app
from app.config import ProductionConfig
from app.models.database import db
from app.models.new_book import NewBook, Publisher
from app.services.new_book import create_new_book_modules
from app.utils.service_helpers import get_new_book_modules


@pytest.fixture
def production_app(monkeypatch, tmp_path):
    """使用真实生产工厂，数据库及文件缓存限定在本地测试空间。"""
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'synthetic-production-read-test-secret')
    monkeypatch.setattr(ProductionConfig, 'ADMIN_SECRET', 'synthetic-production-read-test-admin')
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    monkeypatch.setattr(
        ProductionConfig,
        'SQLALCHEMY_ENGINE_OPTIONS',
        {'poolclass': StaticPool, 'connect_args': {'check_same_thread': False}},
    )
    monkeypatch.setattr(ProductionConfig, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(ProductionConfig, 'IMAGE_CACHE_DIR', tmp_path / 'cache' / 'images')
    for name in ('NYT_API_KEY', 'GOOGLE_API_KEY', 'PRH_API_KEY', 'ZHIPU_API_KEY'):
        monkeypatch.setattr(ProductionConfig, name, '')
    monkeypatch.setenv('DISABLE_BACKGROUND_THREADS', 'true')
    app = create_app('production')
    assert app.config['APP_ENV'] == 'production'
    assert app.config['TESTING'] is False
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize(
    'path,user_agent',
    [
        ('/api/new-books/publishers', ''),
        ('/api/new-books', ''),
        ('/api/new-books?search=synthetic', ''),
        ('/api/new-books/search?keyword=synthetic', ''),
        ('/api/new-books/categories', ''),
        ('/api/new-books/statistics', ''),
        pytest.param('/new-books', '', id='desktop-new-books'),
        pytest.param('/new-books', 'Mozilla/5.0 (iPhone; Mobile)', id='mobile-new-books'),
    ],
)
def test_production_public_new_book_reads_do_not_seed_or_write(production_app, monkeypatch, path, user_agent):
    statements = []
    with production_app.app_context():
        modules = get_new_book_modules()
        ensure_seeded = Mock(wraps=modules.sync_engine.ensure_static_data_seeded)
        initialize = Mock(wraps=modules.publisher_manager.init_publishers)
        commit = Mock(wraps=db.session.commit)
        monkeypatch.setattr(modules.sync_engine, 'ensure_static_data_seeded', ensure_seeded)
        monkeypatch.setattr(modules.publisher_manager, 'init_publishers', initialize)
        monkeypatch.setattr(db.session, 'commit', commit)

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            for _ in range(2):
                response = production_app.test_client().get(path, headers={'User-Agent': user_agent})
                assert response.status_code == 200
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)

        assert statements and all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
        ensure_seeded.assert_not_called()
        initialize.assert_not_called()
        commit.assert_not_called()
        assert Publisher.query.count() == 0
        assert NewBook.query.count() == 0


def test_production_explicit_publisher_initialization_remains_authorized(production_app, monkeypatch):
    import app.utils.admin_auth as admin_auth

    monkeypatch.setattr(admin_auth, '_auth_failures', {})
    monkeypatch.setattr(admin_auth, '_persist_loaded', True)
    client = production_app.test_client()
    assert client.post('/api/new-books/init').status_code == 403
    token = client.get('/api/csrf-token').json['data']['csrf_token']
    response = client.post(
        '/api/new-books/init',
        headers={
            'X-Admin-Secret': production_app.config['ADMIN_SECRET'],
            'X-CSRF-Token': token,
        },
    )
    assert response.status_code == 200
    assert response.json['data']['created_count'] > 0
    with production_app.app_context():
        assert Publisher.query.count() == response.json['data']['created_count']


def test_production_explicit_static_import_remains_available(production_app, tmp_path):
    (tmp_path / 'penguin_random_house_books.json').write_text(
        json.dumps([{'title': 'Synthetic imported title', 'author': 'Synthetic author', 'isbn13': '9780306406157'}]),
        encoding='utf-8',
    )
    with production_app.app_context():
        modules = create_new_book_modules(language_pack_path=tmp_path / 'language-pack.json')
        result = modules.sync_engine.seed_from_static_data(tmp_path)
        assert result['success'] is True
        assert result['added'] == 1
        assert NewBook.query.one().title == 'Synthetic imported title'
