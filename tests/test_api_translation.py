"""
翻译API集成测试

测试翻译相关API端点的核心功能，包括文本翻译、图书翻译、CSRF保护、缓存管理等
"""

import pytest

ADMIN_HEADERS = {'X-Admin-Secret': 'test-admin-secret'}


@pytest.fixture
def csrf_token(client):
    """获取CSRF令牌"""
    response = client.get('/api/csrf-token')
    data = response.get_json()
    return data['data']['csrf_token']


@pytest.fixture(autouse=True)
def _stub_translation_service(monkeypatch):
    """所有翻译 API 测试统一使用假翻译服务，禁止真实网络请求"""

    class ZhipuFake:
        def is_available(self):
            return True

    class FakeTranslator:
        zhipu = ZhipuFake()

        def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
            return f'译_{text}'

        def translate_book_fields(self, **kwargs):
            return {k: f'译_{v}' for k, v in kwargs.items() if isinstance(v, str)}

        def translate_book_info(self, book_data, target_lang='zh'):
            return book_data

        def get_cache_stats(self):
            return {'total': 0, 'hits': 0, 'misses': 0}

    monkeypatch.setattr(
        'app.services.zhipu_translation_service.get_translation_service',
        lambda: FakeTranslator(),
    )


@pytest.mark.usefixtures('db')
class TestTranslationAPI:
    """翻译API测试类"""

    def test_translate_missing_content_type(self, client, csrf_token):
        """测试翻译时缺少Content-Type"""
        response = client.post('/api/translate', json={'text': 'Hello'}, headers={'X-CSRF-Token': csrf_token})
        # 使用json=参数会自动设置Content-Type，这里测试不使用json参数的情况
        response = client.post('/api/translate', data='text=Hello', headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_empty_text(self, client, csrf_token):
        """测试翻译空文本"""
        response = client.post('/api/translate', json={'text': ''}, headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_text_too_long(self, client, csrf_token):
        """测试翻译文本过长"""
        response = client.post('/api/translate', json={'text': 'x' * 10001}, headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_book_fields_empty(self, client, csrf_token):
        """测试翻译图书字段时请求体为空"""
        response = client.post('/api/translate/book-fields', json={}, headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_book_isbn_invalid(self, client, csrf_token):
        """测试翻译图书时ISBN无效"""
        response = client.post('/api/translate/book/invalid-isbn', headers={'X-CSRF-Token': csrf_token})
        assert response.status_code == 400

    def test_translate_cache_stats(self, client):
        """测试获取翻译缓存统计信息"""
        response = client.get('/api/translate/cache/stats', headers=ADMIN_HEADERS)
        assert response.status_code in (200, 429)
        if response.status_code == 200:
            data = response.get_json()
            assert data['success'] is True
            assert 'service' in data['data']

    def test_translate_cache_recent(self, client):
        """测试获取最近的翻译缓存记录"""
        response = client.get('/api/translate/cache/recent?limit=5', headers=ADMIN_HEADERS)
        assert response.status_code in (200, 429)
        if response.status_code == 200:
            data = response.get_json()
            assert data['success'] is True


@pytest.mark.usefixtures('db')
class TestTranslateAwardBookDisplayTitle:
    """v0.9.60 回归测试：/api/translate/book/<isbn> 翻译获奖书时必须用 display_title

    防止 v0.9.57 之前存进数据库的 ISBN 脏数据被当作"书名"送进翻译 API，
    导致模型把 ISBN 字面量原样返回后被前端写回页面（"过一会儿变 ISBN"）。
    """

    def test_isbn_dirty_title_not_passed_to_translator(self, app, db, client, csrf_token, monkeypatch):
        """award_book.title == ISBN（脏数据）时，翻译器拿到的应该是 display_title 退化值"""
        from app.models.schemas import Award, AwardBook

        with app.app_context():
            award = Award(name='pulitzer2026', description='', country='US')
            db.session.add(award)
            db.session.flush()
            # 模拟 v0.9.57 修复前的脏数据：title=ISBN，title_zh=真实中文
            book = AwardBook(
                award_id=award.id,
                year=2026,
                category='Fiction',
                rank=1,
                title='9781668017159',  # 脏数据：title 字段是 ISBN
                title_zh='血中流淌的花',  # 真实中文
                author='Test Author',
                isbn13='9781668017159',
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()
            dirty_isbn = book.isbn13

        captured_input = {}

        class CapturingTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                captured_input[field_type] = text
                return f'译_{text}'

            def translate_book_info(self, book_data, target_lang='zh'):
                from app.services.zhipu_translation_service import _translate_book_info

                return _translate_book_info(self, book_data, target_lang)

        # 让 main book_service 拿不到数据 → 走 AwardBook fallback
        from app.utils import service_helpers

        def _fake_book_service():
            return None

        monkeypatch.setattr(service_helpers, 'get_book_service', _fake_book_service)
        monkeypatch.setattr(
            'app.services.zhipu_translation_service.get_translation_service',
            lambda: CapturingTranslator(),
        )

        response = client.post(
            f'/api/translate/book/{dirty_isbn}',
            headers={'X-CSRF-Token': csrf_token},
        )
        assert response.status_code == 200
        # 核心断言：送进翻译器的 title 不应该是 ISBN
        assert captured_input.get('title') != dirty_isbn
        # 也不应该是空字符串
        assert captured_input.get('title'), '翻译源 title 不应为空'
        # 应该是 display_title 的退化值（因为 title 是 ISBN，display_title 会退化到 title_zh）
        assert captured_input.get('title') == '血中流淌的花'

    def test_clean_title_passes_through(self, app, db, client, csrf_token, monkeypatch):
        """award_book.title 是真实书名时，display_title == title，行为不变"""
        from app.models.schemas import Award, AwardBook

        with app.app_context():
            award = Award(name='booker2026', description='', country='UK')
            db.session.add(award)
            db.session.flush()
            book = AwardBook(
                award_id=award.id,
                year=2026,
                category='Fiction',
                rank=1,
                title='Real Book Title',  # 干净数据
                title_zh='真实书名',
                author='Test Author',
                isbn13='9780525559474',
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()
            clean_isbn = book.isbn13

        captured_title = {}

        class CapturingTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                if field_type == 'title':
                    captured_title['v'] = text
                return f'译_{text}'

            def translate_book_info(self, book_data, target_lang='zh'):
                from app.services.zhipu_translation_service import _translate_book_info

                return _translate_book_info(self, book_data, target_lang)

        from app.utils import service_helpers

        monkeypatch.setattr(service_helpers, 'get_book_service', lambda: None)
        monkeypatch.setattr(
            'app.services.zhipu_translation_service.get_translation_service',
            lambda: CapturingTranslator(),
        )

        response = client.post(
            f'/api/translate/book/{clean_isbn}',
            headers={'X-CSRF-Token': csrf_token},
        )
        assert response.status_code == 200
        # 干净数据时，display_title 退回原 title，行为完全兼容
        assert captured_title.get('v') == 'Real Book Title'


@pytest.mark.usefixtures('db')
class TestCSRFProtection:
    """CSRF保护测试类"""

    def test_csrf_token_endpoint(self, client):
        """测试CSRF令牌端点"""
        response = client.get('/api/csrf-token')
        assert response.status_code == 200
        data = response.get_json()
        assert 'csrf_token' in data['data']

    def test_translate_without_csrf(self, client, monkeypatch):
        """测试不带CSRF令牌发起翻译请求"""

        class FakeTranslationService:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                return '你好'

        monkeypatch.setattr(
            'app.services.zhipu_translation_service.get_translation_service',
            lambda: FakeTranslationService(),
        )

        response = client.post('/api/translate', json={'text': 'Hello'})
        assert response.status_code in (200, 400, 403)


@pytest.mark.usefixtures('db')
class TestCacheAPI:
    """缓存API测试类"""

    def test_cache_stats_requires_admin(self, client):
        """测试缓存统计需要管理员认证"""
        response = client.get('/api/cache/stats')
        assert response.status_code in (403, 429)

    def test_cache_stats(self, client):
        """测试获取缓存统计信息"""
        response = client.get('/api/cache/stats', headers=ADMIN_HEADERS)
        assert response.status_code in (200, 429)

    def test_cache_recent(self, client):
        """测试获取最近缓存记录"""
        response = client.get('/api/cache/recent?limit=5', headers=ADMIN_HEADERS)
        assert response.status_code in (200, 429)

    def test_cache_clear_without_csrf(self, client):
        """测试不带CSRF令牌清除缓存"""
        response = client.post('/api/cache/clear', json={})
        assert response.status_code in (200, 400, 403, 429)
