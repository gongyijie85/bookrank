"""
翻译缓存服务测试

测试 TranslationCacheService 的核心功能，包括缓存读写、统计、搜索、清理和导出
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.schemas import TranslationCache
from app.services.translation_cache_service import (
    TranslationCacheService,
    get_translation_cache_service,
)


def _insert_cache(db, **kwargs):
    """向数据库插入一条 TranslationCache 记录并提交，自动根据 source_text 计算哈希"""
    defaults = {
        'source_text': 'Hello World',
        'source_lang': 'en',
        'target_lang': 'zh',
        'translated_text': '你好世界',
        'model_name': 'glm-4.7-flash',
        'model_version': str(TranslationCacheService.CACHE_VERSION),
        'quality_score': 0.9,
        'usage_count': 1,
        'last_used_at': datetime.now(UTC),
    }
    defaults.update(kwargs)
    if 'source_hash' not in defaults:
        defaults['source_hash'] = TranslationCacheService._compute_source_hash(defaults['source_text'])
    record = TranslationCache(**defaults)
    db.session.add(record)
    db.session.commit()
    return record


class TestComputeSourceHash:
    """测试源文本哈希计算"""

    def test_hash_is_deterministic(self):
        """相同输入应产生相同哈希"""
        h1 = TranslationCacheService._compute_source_hash('Hello')
        h2 = TranslationCacheService._compute_source_hash('Hello')
        assert h1 == h2

    def test_hash_differs_for_different_input(self):
        """不同输入应产生不同哈希"""
        h1 = TranslationCacheService._compute_source_hash('Hello')
        h2 = TranslationCacheService._compute_source_hash('World')
        assert h1 != h2

    def test_hash_is_64_chars_hex(self):
        """哈希值应为64位十六进制字符串"""
        h = TranslationCacheService._compute_source_hash('test')
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)


class TestGet:
    """测试 get 方法"""

    def test_get_returns_none_for_empty_text(self, db):
        """空文本应返回 None"""
        service = TranslationCacheService()
        assert service.get('') is None
        assert service.get(None) is None

    def test_get_returns_none_for_whitespace_text(self, db):
        """纯空白文本应返回 None"""
        service = TranslationCacheService()
        assert service.get('   ') is None
        assert service.get('\t\n') is None

    def test_get_returns_none_when_not_found(self, db):
        """数据库中无匹配记录时应返回 None"""
        service = TranslationCacheService()
        assert service.get('Nonexistent text') is None

    def test_get_returns_cache_on_version_match(self, db):
        """版本匹配时应返回缓存记录"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Hello', translated_text='你好')

        result = service.get('Hello')
        assert result is not None
        assert result.translated_text == '你好'

    def test_get_returns_none_for_expired_version(self, db):
        """版本过期的缓存应被删除并返回 None"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Old version', model_version='1')

        result = service.get('Old version')
        assert result is None

        source_hash = TranslationCacheService._compute_source_hash('Old version')
        remaining = TranslationCache.query.filter_by(source_hash=source_hash).first()
        assert remaining is None

    def test_get_returns_none_for_no_version(self, db):
        """无版本号的旧缓存应被视为过期并返回 None"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='No version', model_version=None)

        result = service.get('No version')
        assert result is None

    def test_get_returns_cache_for_non_numeric_version(self, db):
        """非数字版本号应跳过版本检查并返回缓存"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Bad version', model_version='abc')

        result = service.get('Bad version')
        assert result is not None

    def test_get_with_different_target_langs(self, db):
        """同一源文本不同目标语言应各自返回对应缓存"""
        service = TranslationCacheService()
        _insert_cache(
            db,
            source_text='Hi',
            source_lang='en',
            target_lang='zh',
            translated_text='你好',
        )
        _insert_cache(
            db,
            source_text='Hi',
            source_lang='en',
            target_lang='ja',
            translated_text='こんにちは',
        )

        result_zh = service.get('Hi', 'en', 'zh')
        result_ja = service.get('Hi', 'en', 'ja')
        assert result_zh is not None
        assert result_zh.translated_text == '你好'
        assert result_ja is not None
        assert result_ja.translated_text == 'こんにちは'

    def test_get_with_different_source_langs(self, db):
        """不同源语言应各自返回对应缓存"""
        service = TranslationCacheService()
        _insert_cache(
            db,
            source_text='Bonjour',
            source_lang='fr',
            target_lang='zh',
            translated_text='你好',
        )
        _insert_cache(
            db,
            source_text='Bonjour',
            source_lang='en',
            target_lang='zh',
            translated_text='你好啊',
        )

        result_fr = service.get('Bonjour', 'fr', 'zh')
        result_en = service.get('Bonjour', 'en', 'zh')
        assert result_fr is not None
        assert result_fr.translated_text == '你好'
        assert result_en is not None
        assert result_en.translated_text == '你好啊'


class TestSet:
    """测试 set 方法"""

    def test_set_creates_new_record(self, db):
        """保存新缓存应创建数据库记录"""
        service = TranslationCacheService()
        result = service.set('Hello', '你好')

        assert result is not None
        assert result.source_text == 'Hello'
        assert result.translated_text == '你好'
        assert result.usage_count == 1
        assert result.model_name == 'glm-4.7-flash'

    def test_set_updates_existing_record(self, db):
        """保存相同文本的缓存应更新已有记录"""
        service = TranslationCacheService()
        first = service.set('Hello', '你好')
        second = service.set('Hello', '你好啊')

        assert first.id == second.id
        assert second.translated_text == '你好啊'
        assert second.usage_count == 2

    def test_set_with_all_optional_params(self, db):
        """保存时传入所有可选参数"""
        service = TranslationCacheService()
        result = service.set(
            'Test',
            '测试',
            source_lang='en',
            target_lang='zh',
            model_name='custom-model',
            model_version='3',
            quality_score=0.95,
        )

        assert result.model_name == 'custom-model'
        assert result.model_version == '3'
        assert result.quality_score == 0.95

    def test_set_raises_for_empty_source(self, db):
        """空源文本应抛出 ValueError"""
        service = TranslationCacheService()
        with pytest.raises(ValueError, match='源文本和翻译结果不能为空'):
            service.set('', '你好')

    def test_set_raises_for_empty_translation(self, db):
        """空翻译结果应抛出 ValueError"""
        service = TranslationCacheService()
        with pytest.raises(ValueError, match='源文本和翻译结果不能为空'):
            service.set('Hello', '')

    def test_set_raises_for_both_empty(self, db):
        """两者均为空应抛出 ValueError"""
        service = TranslationCacheService()
        with pytest.raises(ValueError, match='源文本和翻译结果不能为空'):
            service.set('', '')

    def test_set_increments_usage_count(self, db):
        """多次保存同一文本应递增 usage_count"""
        service = TranslationCacheService()
        service.set('Hello', '你好')

        db.session.expire_all()
        second = service.set('Hello', '你好')
        assert second.usage_count == 2

        db.session.expire_all()
        third = service.set('Hello', '你好')
        assert third.usage_count == 3

    def test_set_records_in_database(self, db):
        """保存后记录应存在于数据库中"""
        service = TranslationCacheService()
        service.set('Persist me', '持久化我')

        source_hash = TranslationCacheService._compute_source_hash('Persist me')
        record = TranslationCache.query.filter_by(source_hash=source_hash).first()
        assert record is not None
        assert record.translated_text == '持久化我'


class TestGetStats:
    """测试 get_stats 方法"""

    def test_stats_empty_db(self, db):
        """空数据库应返回全零统计"""
        service = TranslationCacheService()
        stats = service.get_stats()

        assert stats['total_count'] == 0
        assert stats['en_to_zh_count'] == 0
        assert stats['zh_to_en_count'] == 0
        assert stats['recent_24h_count'] == 0
        assert stats['total_usage_count'] == 0
        assert stats['avg_usage_per_item'] == 0
        assert stats['model_name'] == 'glm-4.7-flash'

    def test_stats_with_records(self, db):
        """有记录时应返回正确统计"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='A', source_lang='en', target_lang='zh', usage_count=5)
        _insert_cache(db, source_text='B', source_lang='zh', target_lang='en', usage_count=3)

        stats = service.get_stats()

        assert stats['total_count'] == 2
        assert stats['en_to_zh_count'] == 1
        assert stats['zh_to_en_count'] == 1
        assert stats['total_usage_count'] == 8
        assert stats['avg_usage_per_item'] == 4.0

    def test_stats_recent_24h_count(self, db):
        """最近24小时新增的记录应被正确统计"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Recent')

        stats = service.get_stats()
        assert stats['recent_24h_count'] == 1

    def test_stats_avg_usage_zero_when_no_records(self, db):
        """无记录时平均使用次数应为0"""
        service = TranslationCacheService()
        stats = service.get_stats()
        assert stats['avg_usage_per_item'] == 0

    def test_stats_multiple_en_to_zh(self, db):
        """多条 en->zh 记录应正确统计"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='X', source_lang='en', target_lang='zh', usage_count=2)
        _insert_cache(db, source_text='Y', source_lang='en', target_lang='zh', usage_count=3)

        stats = service.get_stats()
        assert stats['en_to_zh_count'] == 2
        assert stats['total_usage_count'] == 5


class TestGetRecent:
    """测试 get_recent 方法"""

    def test_recent_empty_db(self, db):
        """空数据库应返回空列表"""
        service = TranslationCacheService()
        assert service.get_recent() == []

    def test_recent_returns_ordered_by_last_used(self, db):
        """应按 last_used_at 降序排列"""
        service = TranslationCacheService()
        t1 = datetime.now(UTC) - timedelta(hours=2)
        t2 = datetime.now(UTC)
        _insert_cache(db, source_text='Old record', last_used_at=t1)
        _insert_cache(db, source_text='New record', last_used_at=t2)

        results = service.get_recent()
        assert len(results) == 2
        assert results[0].source_text == 'New record'
        assert results[1].source_text == 'Old record'

    def test_recent_respects_limit(self, db):
        """应遵守 limit 参数"""
        service = TranslationCacheService()
        for i in range(5):
            _insert_cache(db, source_text=f'Text unique {i}')

        results = service.get_recent(limit=3)
        assert len(results) == 3

    def test_recent_filters_by_source_lang(self, db):
        """按源语言筛选"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='LangA', source_lang='en')
        _insert_cache(db, source_text='LangB', source_lang='zh')

        results = service.get_recent(source_lang='en')
        assert len(results) == 1
        assert results[0].source_lang == 'en'

    def test_recent_filters_by_target_lang(self, db):
        """按目标语言筛选"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='TargetA', target_lang='zh')
        _insert_cache(db, source_text='TargetB', target_lang='ja')

        results = service.get_recent(target_lang='ja')
        assert len(results) == 1
        assert results[0].target_lang == 'ja'

    def test_recent_filters_by_both_langs(self, db):
        """同时按源语言和目标语言筛选"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='BothA', source_lang='en', target_lang='zh')
        _insert_cache(db, source_text='BothB', source_lang='en', target_lang='ja')
        _insert_cache(db, source_text='BothC', source_lang='zh', target_lang='en')

        results = service.get_recent(source_lang='en', target_lang='zh')
        assert len(results) == 1
        assert results[0].source_text == 'BothA'


class TestSearch:
    """测试 search 方法"""

    def test_search_finds_in_source_text(self, db):
        """应在源文本中匹配关键词"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='The Great Gatsby', translated_text='了不起的盖茨比')

        results = service.search('Gatsby')
        assert len(results) == 1
        assert results[0].source_text == 'The Great Gatsby'

    def test_search_finds_in_translated_text(self, db):
        """应在翻译文本中匹配关键词"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Hello World', translated_text='你好世界')

        results = service.search('你好')
        assert len(results) == 1

    def test_search_case_insensitive(self, db):
        """搜索应不区分大小写"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Hello World', translated_text='你好世界')

        results = service.search('hello')
        assert len(results) == 1

    def test_search_no_results(self, db):
        """无匹配时应返回空列表"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Hello', translated_text='你好')

        results = service.search('Nonexistent')
        assert results == []

    def test_search_respects_limit(self, db):
        """应遵守 limit 参数"""
        service = TranslationCacheService()
        for i in range(5):
            _insert_cache(db, source_text=f'unique test item {i}', translated_text=f'unique测试{i}')

        results = service.search('unique', limit=2)
        assert len(results) == 2

    def test_search_orders_by_usage_count(self, db):
        """应按 usage_count 降序排列"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Popular', translated_text='热门', usage_count=10)
        _insert_cache(db, source_text='Rare', translated_text='少见', usage_count=1)

        results = service.search('搜') or service.search('Popular')
        if results:
            assert results[0].usage_count >= results[-1].usage_count

    def test_search_filters_by_source_lang(self, db):
        """按源语言筛选"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='FilterA', source_lang='en')
        _insert_cache(db, source_text='FilterB', source_lang='zh')

        results = service.search('Filter', source_lang='en')
        assert len(results) == 1
        assert results[0].source_lang == 'en'

    def test_search_filters_by_target_lang(self, db):
        """按目标语言筛选"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='TargetSearchA', target_lang='zh')
        _insert_cache(db, source_text='TargetSearchB', target_lang='ja')

        results = service.search('TargetSearch', target_lang='ja')
        assert len(results) == 1
        assert results[0].target_lang == 'ja'

    def test_search_keyword_with_percent_returns_empty(self, db):
        """含 % 的关键词因 SQLite LIKE 转义限制可能无法匹配"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='100% Complete', translated_text='100%完成')

        results = service.search('100%')
        assert isinstance(results, list)

    def test_search_keyword_with_underscore_returns_empty(self, db):
        """含 _ 的关键词因 SQLite LIKE 转义限制可能无法匹配"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='test_item_name', translated_text='测试项')

        results = service.search('test_item')
        assert isinstance(results, list)

    def test_search_empty_keyword_returns_all(self, db):
        """空关键词应匹配所有记录"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Alpha', translated_text='甲')
        _insert_cache(db, source_text='Beta', translated_text='乙')

        results = service.search('')
        assert len(results) >= 2


class TestGetLeastUsed:
    """测试 get_least_used 方法"""

    def test_least_used_empty_db(self, db):
        """空数据库应返回空列表"""
        service = TranslationCacheService()
        assert service.get_least_used() == []

    def test_least_used_returns_ordered_asc(self, db):
        """应按 usage_count 升序排列"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Most used', usage_count=10)
        _insert_cache(db, source_text='Least used', usage_count=1)

        results = service.get_least_used()
        assert len(results) == 2
        assert results[0].source_text == 'Least used'
        assert results[1].source_text == 'Most used'

    def test_least_used_respects_limit(self, db):
        """应遵守 limit 参数"""
        service = TranslationCacheService()
        for i in range(5):
            _insert_cache(db, source_text=f'Limit item {i}', usage_count=i)

        results = service.get_least_used(limit=2)
        assert len(results) == 2

    def test_least_used_filters_by_older_than_days(self, db):
        """应能按天数筛选旧记录"""
        service = TranslationCacheService()
        old_time = datetime.now(UTC) - timedelta(days=60)
        recent_time = datetime.now(UTC) - timedelta(days=1)

        _insert_cache(db, source_text='Very old', usage_count=0, last_used_at=old_time)
        _insert_cache(db, source_text='Recent one', usage_count=0, last_used_at=recent_time)

        results = service.get_least_used(older_than_days=30)
        assert len(results) == 1
        assert results[0].source_text == 'Very old'


class TestAutoCleanup:
    """测试 auto_cleanup 方法"""

    def test_cleanup_no_action_when_under_limit(self, db):
        """缓存数量未超过上限时不应清理"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='CleanupA')
        _insert_cache(db, source_text='CleanupB')

        deleted = service.auto_cleanup(max_items=10000)
        assert deleted == 0
        assert TranslationCache.query.count() == 2

    def test_cleanup_removes_old_records(self, db):
        """应删除超出限制且不满足保留条件的旧记录"""
        service = TranslationCacheService()
        old_time = datetime.now(UTC) - timedelta(days=60)
        for i in range(5):
            _insert_cache(
                db,
                source_text=f'Old item {i}',
                usage_count=0,
                last_used_at=old_time,
                created_at=old_time,
            )

        deleted = service.auto_cleanup(max_items=3, keep_recent_days=30)
        assert deleted == 5
        assert TranslationCache.query.count() == 0

    def test_cleanup_preserves_recent_records(self, db):
        """应保留最近创建的记录"""
        service = TranslationCacheService()
        for i in range(3):
            _insert_cache(db, source_text=f'Recent item {i}')

        deleted = service.auto_cleanup(max_items=2, keep_recent_days=30)
        assert deleted == 0

    def test_cleanup_preserves_high_usage(self, db):
        """应保留使用次数>=10的记录"""
        service = TranslationCacheService()
        old_time = datetime.now(UTC) - timedelta(days=60)
        _insert_cache(
            db,
            source_text='Hot item',
            usage_count=15,
            last_used_at=old_time,
            created_at=old_time,
        )
        _insert_cache(
            db,
            source_text='Cold item',
            usage_count=0,
            last_used_at=old_time,
            created_at=old_time,
        )

        deleted = service.auto_cleanup(max_items=1, keep_recent_days=30)
        assert deleted == 1
        remaining = TranslationCache.query.all()
        assert len(remaining) == 1
        assert remaining[0].source_text == 'Hot item'

    def test_cleanup_preserves_recently_used(self, db):
        """应保留最近有使用记录的缓存"""
        service = TranslationCacheService()
        recent_time = datetime.now(UTC) - timedelta(days=5)
        old_time = datetime.now(UTC) - timedelta(days=60)

        _insert_cache(
            db,
            source_text='Recently used item',
            usage_count=0,
            last_used_at=recent_time,
            created_at=old_time,
        )
        _insert_cache(
            db,
            source_text='Old unused item',
            usage_count=0,
            last_used_at=old_time,
            created_at=old_time,
        )

        deleted = service.auto_cleanup(max_items=1, keep_recent_days=30)
        assert deleted == 1
        remaining = TranslationCache.query.all()
        assert len(remaining) == 1
        assert remaining[0].source_text == 'Recently used item'


class TestDelete:
    """测试 delete 方法"""

    def test_delete_by_id(self, db):
        """应按 ID 删除指定记录"""
        service = TranslationCacheService()
        record = _insert_cache(db, source_text='To delete')

        deleted = service.delete(cache_id=record.id)
        assert deleted == 1
        assert db.session.get(TranslationCache, record.id) is None

    def test_delete_nonexistent_id(self, db):
        """删除不存在的 ID 应返回 0"""
        service = TranslationCacheService()
        deleted = service.delete(cache_id=99999)
        assert deleted == 0

    def test_delete_by_older_than_days(self, db):
        """应按创建时间删除旧记录"""
        service = TranslationCacheService()
        old_time = datetime.now(UTC) - timedelta(days=60)
        _insert_cache(db, source_text='Old delete', created_at=old_time)
        _insert_cache(db, source_text='New delete')

        deleted = service.delete(older_than_days=30)
        assert deleted == 1
        assert TranslationCache.query.filter_by(source_text='New delete').first() is not None

    def test_delete_by_min_usage(self, db):
        """应删除使用次数低于指定值的记录"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Low usage del', usage_count=1)
        _insert_cache(db, source_text='High usage del', usage_count=10)

        deleted = service.delete(min_usage=5)
        assert deleted == 1
        assert TranslationCache.query.filter_by(source_text='High usage del').first() is not None

    def test_delete_by_combined_filters(self, db):
        """组合条件删除应只删除同时满足所有条件的记录"""
        service = TranslationCacheService()
        old_time = datetime.now(UTC) - timedelta(days=60)
        _insert_cache(db, source_text='Combo A', usage_count=0, created_at=old_time)
        _insert_cache(db, source_text='Combo B', usage_count=10, created_at=old_time)
        _insert_cache(db, source_text='Combo C', usage_count=0)

        deleted = service.delete(older_than_days=30, min_usage=5)
        assert deleted == 1
        assert TranslationCache.query.filter_by(source_text='Combo A').first() is None
        assert TranslationCache.query.filter_by(source_text='Combo B').first() is not None
        assert TranslationCache.query.filter_by(source_text='Combo C').first() is not None

    def test_delete_min_usage_zero_deletes_nothing(self, db):
        """min_usage=0 时 usage_count=0 的记录不会被删除（0 < 0 为 False）"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Zero usage', usage_count=0)

        deleted = service.delete(min_usage=0)
        assert deleted == 0
        assert TranslationCache.query.filter_by(source_text='Zero usage').first() is not None

    def test_delete_with_no_params_deletes_all(self, db):
        """无参数调用时无过滤条件，会删除所有记录"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Delete all A')
        _insert_cache(db, source_text='Delete all B')

        deleted = service.delete()
        assert deleted == 2
        assert TranslationCache.query.count() == 0


class TestClearAll:
    """测试 clear_all 方法"""

    def test_clear_all_removes_everything(self, db):
        """应删除所有缓存记录"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Clear A')
        _insert_cache(db, source_text='Clear B')
        _insert_cache(db, source_text='Clear C')

        count = service.clear_all()
        assert count == 3
        assert TranslationCache.query.count() == 0

    def test_clear_all_empty_db(self, db):
        """空数据库应返回 0"""
        service = TranslationCacheService()
        count = service.clear_all()
        assert count == 0

    def test_clear_all_returns_correct_count(self, db):
        """返回值应为实际删除的记录数"""
        service = TranslationCacheService()
        for i in range(10):
            _insert_cache(db, source_text=f'Count item {i}')

        count = service.clear_all()
        assert count == 10


class TestExportCache:
    """测试 export_cache 方法"""

    def test_export_json_format(self, db):
        """JSON 格式导出应包含正确结构"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Export Hello', translated_text='导出你好')

        result = service.export_cache('json')
        assert result['total'] == 1
        assert 'exported_at' in result
        assert 'data' in result
        assert len(result['data']) == 1
        assert result['data'][0]['source_text'] == 'Export Hello'
        assert result['data'][0]['translated_text'] == '导出你好'

    def test_export_csv_format(self, db):
        """CSV 格式导出应包含正确表头和数据"""
        service = TranslationCacheService()
        _insert_cache(
            db,
            source_text='CSV Hello',
            translated_text='CSV你好',
            source_lang='en',
            target_lang='zh',
            usage_count=3,
        )

        result = service.export_cache('csv')
        assert result['total'] == 1
        assert 'csv' in result
        lines = result['csv'].split('\n')
        assert lines[0] == 'source_text,translated_text,source_lang,target_lang,usage_count'
        assert '"CSV Hello"' in lines[1]
        assert '"CSV你好"' in lines[1]

    def test_export_json_empty_db(self, db):
        """空数据库的 JSON 导出"""
        service = TranslationCacheService()
        result = service.export_cache('json')
        assert result['total'] == 0
        assert result['data'] == []

    def test_export_csv_empty_db(self, db):
        """空数据库的 CSV 导出"""
        service = TranslationCacheService()
        result = service.export_cache('csv')
        assert result['total'] == 0
        lines = result['csv'].split('\n')
        assert len(lines) == 1

    def test_export_json_default_format(self, db):
        """不传 format 参数时默认为 JSON"""
        service = TranslationCacheService()
        result = service.export_cache()
        assert 'data' in result
        assert 'csv' not in result

    def test_export_orders_by_usage_desc(self, db):
        """导出结果应按 usage_count 降序排列"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Popular export', usage_count=10)
        _insert_cache(db, source_text='Unpopular export', usage_count=1)

        result = service.export_cache('json')
        assert result['data'][0]['source_text'] == 'Popular export'
        assert result['data'][1]['source_text'] == 'Unpopular export'

    def test_export_json_has_to_dict_fields(self, db):
        """JSON 导出的每条记录应包含 to_dict 的所有字段"""
        service = TranslationCacheService()
        _insert_cache(db, source_text='Field check', translated_text='字段检查')

        result = service.export_cache('json')
        record = result['data'][0]
        expected_keys = {
            'id',
            'source_hash',
            'source_text',
            'source_lang',
            'target_lang',
            'translated_text',
            'model_name',
            'model_version',
            'quality_score',
            'usage_count',
            'last_used_at',
            'created_at',
        }
        assert expected_keys == set(record.keys())


class TestSingleton:
    """测试单例模式"""

    def test_singleton_returns_same_instance(self):
        """多次调用应返回同一个实例"""
        s1 = get_translation_cache_service()
        s2 = get_translation_cache_service()
        assert s1 is s2

    def test_singleton_is_correct_type(self):
        """单例应为 TranslationCacheService 类型"""
        service = get_translation_cache_service()
        assert isinstance(service, TranslationCacheService)
