"""
pytest 测试配置文件

提供测试所需的 fixtures 和测试环境配置
"""

import os
import sys

import pytest

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 设置测试环境变量
os.environ['FLASK_ENV'] = 'testing'

# 导入所有模型类，确保它们被 SQLAlchemy 注册
from app import create_app
from app.models.database import db as _db
from app.models.schemas import UserFavorite  # noqa: F401 — 注册模型到 SQLAlchemy
from app.services.award_book_service import AwardBookService


@pytest.fixture(scope='session')
def app():
    """
    创建测试用的 Flask 应用

    Returns:
        Flask 应用实例
    """
    from app.utils.rate_limiter import _global_rate_limiters

    _global_rate_limiters.clear()

    app = create_app('testing')
    app.config['ADMIN_SECRET'] = 'test-admin-secret'

    assert app.config['TESTING'] is True
    assert 'memory' in app.config['SQLALCHEMY_DATABASE_URI']

    yield app


@pytest.fixture(scope='session')
def client(app):
    """
    创建测试客户端

    Returns:
        Flask 测试客户端
    """
    return app.test_client()


@pytest.fixture(scope='function')
def db(app):
    """
    创建测试数据库 (SQLite 内存数据库)

    每个测试函数都会创建新的数据库表，
    确保测试之间相互隔离。

    Returns:
        数据库实例
    """
    from app.utils.rate_limiter import _global_rate_limiters

    for limiter in _global_rate_limiters.values():
        limiter._requests.clear()

    with app.app_context():
        _db.create_all()

        yield _db

        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='function')
def session(app, db):
    """
    提供数据库会话

    Returns:
        数据库会话
    """
    with app.app_context():
        yield db.session


@pytest.fixture
def app_context(app):
    """
    提供应用上下文

    Returns:
        应用上下文
    """
    with app.app_context():
        yield app


@pytest.fixture
def runner(app):
    """
    提供 CLI 测试运行器

    Returns:
        CLI 运行器
    """
    return app.test_cli_runner()


@pytest.fixture
def admin_headers():
    return {'X-Admin-Secret': 'test-admin-secret'}


@pytest.fixture
def mock_books_data():
    """
    提供模拟的图书数据

    Returns:
        模拟图书数据列表
    """
    return [
        {
            'id': '9780143127550',
            'title': 'Test Book 1',
            'author': 'Author One',
            'publisher': 'Test Publisher',
            'cover': 'https://example.com/cover1.jpg',
            'list_name': 'Hardcover Fiction',
            'category_id': 'hardcover-fiction',
            'category_name': '精装小说',
            'rank': 1,
            'weeks_on_list': 10,
            'rank_last_week': '2',
            'published_date': '2024-01-14',
            'description': 'A test book description',
            'details': 'Detailed description here',
            'publication_dt': '2023-10-01',
            'page_count': '320',
            'language': 'en',
            'buy_links': [],
            'isbn13': '9780143127550',
            'isbn10': '014312755X',
            'price': '28.00',
            'description_zh': None,
            'details_zh': None,
        },
        {
            'id': '9780062796200',
            'title': 'Test Book 2',
            'author': 'Author Two',
            'publisher': 'Another Publisher',
            'cover': 'https://example.com/cover2.jpg',
            'list_name': 'Hardcover Nonfiction',
            'category_id': 'hardcover-nonfiction',
            'category_name': '精装非虚构',
            'rank': 1,
            'weeks_on_list': 5,
            'rank_last_week': '无',
            'published_date': '2024-01-14',
            'description': 'Another test book',
            'details': 'More details',
            'publication_dt': '2023-11-15',
            'page_count': '256',
            'language': 'en',
            'buy_links': [],
            'isbn13': '9780062796200',
            'isbn10': '0062796208',
            'price': '32.50',
            'description_zh': None,
            'details_zh': None,
        },
    ]


@pytest.fixture
def mock_nyt_response():
    """
    提供模拟的 NYT API 响应

    Returns:
        模拟 NYT API 响应数据
    """
    return {
        'status': 'OK',
        'num_results': 15,
        'results': {
            'list_name': 'Hardcover Fiction',
            'list_name_encoded': 'hardcover-fiction',
            'bestsellers_date': '2024-01-13',
            'published_date': '2024-01-14',
            'books': [
                {
                    'primary_isbn13': '9780143127550',
                    'primary_isbn10': '014312755X',
                    'rank': 1,
                    'title': 'Test Book Title',
                    'author': 'Test Author',
                    'contributor': 'Test Author',
                    'description': 'A compelling story.',
                    'book_image': 'https://example.com/image.jpg',
                    'publisher': 'Test Publisher',
                    'weeks_on_list': 10,
                    'rank_last_week': '2',
                    'price': '28.00',
                    'buy_links': [{'name': 'Amazon', 'url': 'https://amazon.com'}],
                }
            ],
        },
    }


@pytest.fixture
def mock_google_books_response():
    """
    提供模拟的 Google Books API 响应

    Returns:
        模拟 Google Books API 响应数据
    """
    return {
        'isbn_13': '9780143127550',
        'isbn_10': '014312755X',
        'title': 'Test Book Title',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'publication_dt': '2023-10-01',
        'page_count': 320,
        'language': 'eng',
        'details': 'Detailed book description from Google Books.',
        'cover_url': 'https://example.com/cover.jpg',
    }


@pytest.fixture
def award_service():
    return AwardBookService()


@pytest.fixture
def sample_award(app, db):
    from app.models.schemas import Award

    award = Award(
        name='星云奖',
        name_en='Nebula Award',
        country='美国',
        description='美国科幻奇幻作家协会颁发的年度奖项',
    )
    db.session.add(award)
    db.session.commit()
    return award.id


@pytest.fixture
def sample_award_book(app, db, sample_award):
    from app.models.schemas import Award, AwardBook

    award = db.session.get(Award, sample_award)
    book = AwardBook(
        award_id=award.id,
        title='测试获奖图书',
        author='测试作者',
        year=2024,
        category='最佳长篇小说',
        isbn13='9780000000000',
        description='一本优秀的测试图书',
        cover_local_path='/covers/test_cover.jpg',
    )
    db.session.add(book)
    db.session.commit()
    return book.id


@pytest.fixture
def _seed_award(app, db):
    """为 TestAdminAwardFixEndpoints 提供最小可修复数据：1 个 Award + 1 本带 ISBN 的 AwardBook"""
    from app.models.schemas import Award, AwardBook

    award = Award(name='Test Award', description='A test award', country='US')
    db.session.add(award)
    db.session.commit()

    book = AwardBook(
        award_id=award.id,
        title='Original English Title',
        title_zh=None,
        author='Test Author',
        year=2024,
        rank=1,
        category='Fiction',
        isbn13='9780143127550',
    )
    db.session.add(book)
    db.session.commit()
    return {'award_id': award.id, 'book_id': book.id}


@pytest.fixture
def clear_auth_failures():
    """清理 admin_auth 的失败计数，避免测试间污染。

    注意：_auth_failures 是 admin_auth 模块级全局 dict，需要清理以避免
    跨测试用例状态污染。_persist_loaded 故意**不**重置，因为它是
    "持久化封禁状态是否已加载"的全局缓存标志，重置会导致后续 admin 请求
    触发 SystemConfig 重新查询（在没有 db fixture 的测试中会失败）。
    """
    from app.utils import admin_auth

    admin_auth._auth_failures.clear()
    yield
    admin_auth._auth_failures.clear()
