"""新书查询模块测试

由 tests/test_new_book_service.py 拆分而来（门面坍塌重构）：
针对 NewBookQueryService 的列表、搜索、详情、分类与统计查询。
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.new_book.query_service import NewBookQueryService
from app.services.publisher_data import (
    CATEGORY_EN_TO_ZH,
    canonicalize_category,
    category_alias_in_set,
)


@pytest.fixture
def query_service():
    """创建查询模块实例：翻译管道用 mock 隔离（查询路径只做语言包补齐）"""
    return NewBookQueryService(MagicMock())


def _seed_publisher(db) -> Publisher:
    pm = __import__('app.services.new_book.publisher_manager', fromlist=['PublisherManager'])
    pm.PublisherManager().init_publishers()
    publisher = Publisher.query.first()
    assert publisher is not None
    return publisher


_FROZEN_AT = datetime(2026, 9, 30, 0, 5, tzinfo=UTC)


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _FROZEN_AT.replace(tzinfo=None)
        return _FROZEN_AT.astimezone(tz)


def _freeze_query_clock(monkeypatch):
    import app.services.new_book.query_service as query_module

    monkeypatch.setattr(query_module, 'datetime', _FrozenDateTime)


def _add_publisher(db, name, *, site_display_primary=True):
    publisher = Publisher(
        name=name,
        name_en=name,
        crawler_class='FixtureCrawler',
        site_display_primary=site_display_primary,
    )
    db.session.add(publisher)
    db.session.flush()
    return publisher


def _add_book(
    db,
    publisher,
    isbn,
    *,
    title,
    publication_date,
    created_at,
    category='Fiction',
    is_displayable=True,
    batch_id=None,
):
    book = NewBook(
        publisher_id=publisher.id,
        title=title,
        author='Author',
        isbn13=isbn,
        category=category,
        publication_date=publication_date,
        created_at=created_at,
        is_displayable=is_displayable,
        last_import_batch_id=batch_id,
    )
    db.session.add(book)
    return book


def _isbn_set(books):
    return {book.isbn13 for book in books}


class TestNewBookQueryService:
    def test_get_new_books(self, query_service, db):
        """测试获取新书列表"""
        publisher = _seed_publisher(db)
        test_book = NewBook(
            publisher_id=publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            isbn10='0000000001',
            description='Test description',
            cover_url='https://example.com/cover.jpg',
            category='Fiction',
            publication_date=datetime.now(UTC),
            is_displayable=True,
        )
        db.session.add(test_book)
        db.session.commit()

        books, total = query_service.get_new_books(days=30)

        assert total >= 1
        assert len(books) >= 1

    def test_get_new_books_filters_by_publication_date(self, query_service, db):
        """新书时间范围应按出版日期过滤，而不是按同步入库时间过滤"""
        publisher = _seed_publisher(db)

        today = datetime.now(UTC).date()
        now = datetime.now(UTC)
        rows = [
            NewBook(
                publisher_id=publisher.id,
                title='Recent Publication',
                author='Author',
                isbn13='9780000000101',
                category='Fiction',
                publication_date=today - timedelta(days=5),
                created_at=now - timedelta(days=120),
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='Old Publication Synced Today',
                author='Author',
                isbn13='9780000000102',
                category='Fiction',
                publication_date=today - timedelta(days=120),
                created_at=now,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='Future Publication',
                author='Author',
                isbn13='9780000000103',
                category='Fiction',
                publication_date=today + timedelta(days=30),
                created_at=now,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='No Date Recent Sync',
                author='Author',
                isbn13='9780000000104',
                category='Fiction',
                publication_date=None,
                created_at=now,
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='No Date Recently Discovered',
                author='Author',
                isbn13='9780000000105',
                category='Fiction',
                publication_date=None,
                created_at=now - timedelta(days=5),
                is_displayable=True,
            ),
            NewBook(
                publisher_id=publisher.id,
                title='No Date Outside Window',
                author='Author',
                isbn13='9780000000106',
                category='Fiction',
                publication_date=None,
                created_at=now - timedelta(days=31),
                is_displayable=True,
            ),
        ]
        db.session.add_all(rows)
        db.session.commit()

        books, total = query_service.get_new_books(days=30)

        titles = {book.title for book in books}
        assert total == 3
        assert titles == {'Recent Publication', 'No Date Recent Sync', 'No Date Recently Discovered'}

        no_date_book = next(book for book in books if book.title == 'No Date Recently Discovered')
        assert no_date_book.publication_date is None
        assert no_date_book.created_at.date() == (today - timedelta(days=5))

    def test_search_books_honors_publication_window(self, query_service, db):
        """搜索也应遵守当前新书出版时间范围"""
        publisher = _seed_publisher(db)

        today = datetime.now(UTC).date()
        db.session.add_all(
            [
                NewBook(
                    publisher_id=publisher.id,
                    title='Window Match',
                    author='Author',
                    isbn13='9780000000111',
                    publication_date=today - timedelta(days=3),
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Window Match Old',
                    author='Author',
                    isbn13='9780000000112',
                    publication_date=today - timedelta(days=80),
                    is_displayable=True,
                ),
            ]
        )
        db.session.commit()

        books, total = query_service.search_books('Window Match', days=30)

        assert total == 1
        assert books[0].title == 'Window Match'

    def test_get_book(self, query_service, db):
        """测试获取单本书籍详情"""
        publisher = _seed_publisher(db)
        test_book = NewBook(
            publisher_id=publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            isbn10='0000000001',
            description='Test description',
            cover_url='https://example.com/cover.jpg',
            category='Fiction',
            publication_date=datetime.now(UTC),
            is_displayable=True,
        )
        db.session.add(test_book)
        db.session.commit()

        result = query_service.get_book(test_book.id)

        assert result is not None
        assert result.id == test_book.id
        assert result.title == 'Test Book'

    def test_search_books(self, query_service, db):
        """测试搜索书籍"""
        publisher = _seed_publisher(db)
        test_book = NewBook(
            publisher_id=publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            isbn10='0000000001',
            description='Test description',
            cover_url='https://example.com/cover.jpg',
            category='Fiction',
            publication_date=datetime.now(UTC),
            is_displayable=True,
        )
        db.session.add(test_book)
        db.session.commit()

        books, total = query_service.search_books('Test')

        assert total >= 1
        assert len(books) >= 1

    def test_get_categories(self, query_service, db):
        """测试获取所有分类（audit08：英文原始值归并为规范中文选项）"""
        publisher = _seed_publisher(db)
        test_book = NewBook(
            publisher_id=publisher.id,
            title='Test Book',
            author='Test Author',
            isbn13='9780000000001',
            isbn10='0000000001',
            description='Test description',
            cover_url='https://example.com/cover.jpg',
            category='Fiction',
            publication_date=datetime.now(UTC),
            is_displayable=True,
        )
        db.session.add(test_book)
        db.session.commit()

        categories = query_service.get_categories()

        assert len(categories) >= 1
        # 'Fiction' 与 '小说' 归并为同一规范选项 '小说'（audit08 同义项归一）
        assert any(cat['name'] == '小说' for cat in categories)

    def test_get_categories_groups_synonym_aliases(self, query_service, db):
        """audit08：'Biography' 与 'Biography & Autobiography' 归并到 '传记' 并累计计数"""
        publisher = _seed_publisher(db)
        db.session.add_all(
            [
                NewBook(
                    publisher_id=publisher.id,
                    title='Bio A',
                    author='A',
                    isbn13='9780000000201',
                    category='Biography',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Bio B',
                    author='B',
                    isbn13='9780000000202',
                    category='Biography & Autobiography',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Bio C',
                    author='C',
                    isbn13='9780000000203',
                    category='传记',
                    is_displayable=True,
                ),
            ]
        )
        db.session.commit()

        categories = query_service.get_categories()
        bio = next(cat for cat in categories if cat['name'] == '传记')
        assert bio['count'] == 3

    def test_category_filter_matches_alias_group(self, query_service, db):
        """audit08：按规范分类 '传记' 过滤时，命中所有原始别名（无数据丢失）"""
        publisher = _seed_publisher(db)
        db.session.add_all(
            [
                NewBook(
                    publisher_id=publisher.id,
                    title='Bio A',
                    author='A',
                    isbn13='9780000000211',
                    category='Biography',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Bio B',
                    author='B',
                    isbn13='9780000000212',
                    category='Biography & Autobiography',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Bio C',
                    author='C',
                    isbn13='9780000000213',
                    category='传记',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='Other',
                    author='D',
                    isbn13='9780000000214',
                    category='Fiction',
                    is_displayable=True,
                ),
            ]
        )
        db.session.commit()

        # 规范中文键
        books, total = query_service.get_new_books(category='传记', days=365)
        assert total == 3
        assert {b.title for b in books} == {'Bio A', 'Bio B', 'Bio C'}

        # 旧的原生英文 URL 仍命中同一别名组
        books_en, total_en = query_service.get_new_books(category='Biography & Autobiography', days=365)
        assert total_en == 3

    def test_category_alias_expansion_covers_outside_new_four(self):
        """audit08 数据丢失回归：未进"新增四词"但早已入库的英文键也要展开原值+规范值。

        'Health & Fitness' 与 'General'/'general' 不在 browse 提交新增的那组同义词里，
        靠 CATEGORY_EN_TO_ZH 派生别名组后，仍必须各自命中自己 + 规范中文显示键。
        """
        hf = category_alias_in_set('Health & Fitness')
        assert '健康养生' in hf
        assert 'Health & Fitness' in hf
        # 规范键本身同样展开到同一组
        assert category_alias_in_set('健康养生') == hf

        gen = category_alias_in_set('General')
        assert '综合' in gen
        assert 'General' in gen
        assert 'general' in gen

    def test_category_alias_expansion_every_known_en_key_includes_original_and_canonical(self):
        """audit08 数据丢失回归：对每个已知英文键，别名展开必须同时含原值 + 规范显示键。"""
        for en, zh in CATEGORY_EN_TO_ZH.items():
            expanded = set(category_alias_in_set(en))
            assert en in expanded, f'{en!r} 的别名展开丢失原值'
            assert zh in expanded, f'{en!r} 的别名展开丢失规范显示键 {zh!r}'
            # 规范中文键展开后与英文键一致（同一组），保证中文/英文 URL 命中同一批记录
            assert set(category_alias_in_set(zh)) == expanded, f'{zh!r} 与 {en!r} 别名组不一致'

    def test_unknown_raw_category_stays_queryable(self):
        """audit08：未知原生标签不进别名表，展开结果仅含自身，保证旧 URL 仍精确命中。"""
        assert category_alias_in_set('Some Unknown Shelf') == ['Some Unknown Shelf']
        assert canonicalize_category('Some Unknown Shelf') == 'Some Unknown Shelf'
        # 已知英文键会归一为规范中文显示键
        assert canonicalize_category('Health & Fitness') == '健康养生'
        assert canonicalize_category('general') == '综合'

    def test_get_categories_groups_and_sorts_popular_first(self, query_service, db):
        """audit08：归并后按计数降序排列（热门分类在前），且不丢新四词之外的英文原始值。"""
        publisher = _seed_publisher(db)
        db.session.add_all(
            [
                NewBook(
                    publisher_id=publisher.id,
                    title='H1',
                    author='A',
                    isbn13='9780000000301',
                    category='Health & Fitness',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='H2',
                    author='A',
                    isbn13='9780000000302',
                    category='健康养生',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='H3',
                    author='A',
                    isbn13='9780000000303',
                    category='Health & Fitness',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='G1',
                    author='A',
                    isbn13='9780000000304',
                    category='General',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='G2',
                    author='A',
                    isbn13='9780000000305',
                    category='general',
                    is_displayable=True,
                ),
                NewBook(
                    publisher_id=publisher.id,
                    title='F1',
                    author='A',
                    isbn13='9780000000306',
                    category='Fiction',
                    is_displayable=True,
                ),
            ]
        )
        db.session.commit()

        categories = query_service.get_categories()
        by_name = {c['name']: c['count'] for c in categories}
        assert by_name['健康养生'] == 3
        assert by_name['综合'] == 2
        assert by_name['小说'] == 1

        # 计数从高到低：健康养生(3) > 综合(2) > 小说(1)
        counts = [c['count'] for c in categories]
        assert counts == sorted(counts, reverse=True)

        # 旧英文 URL 过滤命中原记录，未发生数据丢失
        books, total = query_service.get_new_books(category='Health & Fitness', days=365)
        assert total == 3
        books_gen, total_gen = query_service.get_new_books(category='general', days=365)
        assert total_gen == 2

    def test_get_statistics(self, query_service, db):
        """测试获取统计数据"""
        _seed_publisher(db)

        stats = query_service.get_statistics()

        assert isinstance(stats, dict)
        assert 'total_books' in stats
        assert 'total_publishers' in stats
        assert 'active_publishers' in stats
        assert 'recent_books_7d' in stats
        assert 'top_categories' in stats

    @pytest.mark.parametrize(
        ('status', 'expected'),
        [
            (
                'all',
                {
                    '9780000000401',
                    '9780000000402',
                    '9780000000403',
                    '9780000000404',
                    '9780000000405',
                    '9780000000406',
                },
            ),
            ('published', {'9780000000401', '9780000000402'}),
            ('upcoming', {'9780000000403', '9780000000404'}),
            ('pending', {'9780000000405', '9780000000406'}),
        ],
    )
    def test_publication_status_exact_sets_inside_window(self, query_service, db, monkeypatch, status, expected):
        """四种 publication_status 在默认 30 天窗口内命中精确 ISBN 集。"""
        _freeze_query_clock(monkeypatch)
        publisher = _add_publisher(db, 'Status Press')
        today = _FROZEN_AT.date()
        stamped = datetime(2026, 9, 1, tzinfo=UTC)
        specs = [
            ('9780000000401', today, stamped),
            ('9780000000402', today - timedelta(days=30), stamped),
            ('9780000000403', today + timedelta(days=1), stamped),
            ('9780000000404', today + timedelta(days=14), stamped),
            ('9780000000405', None, datetime(2026, 8, 31, tzinfo=UTC)),
            ('9780000000406', None, datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)),
        ]
        for isbn, published_on, created_at in specs:
            _add_book(
                db,
                publisher,
                isbn,
                title=f'Title {isbn}',
                publication_date=published_on,
                created_at=created_at,
            )
        db.session.commit()

        books, total = query_service.get_new_books(publication_status=status)
        assert _isbn_set(books) == expected
        assert total == len(expected)

    def test_publication_status_excludes_rows_outside_list_window(self, query_service, db, monkeypatch):
        """列表窗口仍排除过旧已出版和超过预告 14 天的书。"""
        _freeze_query_clock(monkeypatch)
        publisher = _add_publisher(db, 'Window Press')
        today = _FROZEN_AT.date()
        created_at = datetime(2026, 9, 1, tzinfo=UTC)
        _add_book(
            db,
            publisher,
            '9780000000411',
            title='In published',
            publication_date=today,
            created_at=created_at,
        )
        _add_book(
            db,
            publisher,
            '9780000000412',
            title='In upcoming',
            publication_date=today + timedelta(days=14),
            created_at=created_at,
        )
        _add_book(
            db,
            publisher,
            '9780000000413',
            title='Old published',
            publication_date=today - timedelta(days=31),
            created_at=created_at,
        )
        _add_book(
            db,
            publisher,
            '9780000000414',
            title='Far upcoming',
            publication_date=today + timedelta(days=15),
            created_at=created_at,
        )
        db.session.commit()

        all_books, all_total = query_service.get_new_books(publication_status='all')
        assert all_total == 2
        assert _isbn_set(all_books) == {'9780000000411', '9780000000412'}

        published, published_total = query_service.get_new_books(publication_status='published')
        assert published_total == 1
        assert _isbn_set(published) == {'9780000000411'}

        upcoming, upcoming_total = query_service.get_new_books(publication_status='upcoming')
        assert upcoming_total == 1
        assert _isbn_set(upcoming) == {'9780000000412'}

    def test_pending_created_at_cutoff_is_half_open(self, query_service, db, monkeypatch):
        """待确认出版日的发现时间是 [cutoff 零点, 次日零点)。"""
        _freeze_query_clock(monkeypatch)
        publisher = _add_publisher(db, 'Pending Press')
        edges = [
            ('9780000000420', datetime(2026, 8, 30, 23, 59, 59, tzinfo=UTC)),
            ('9780000000421', datetime(2026, 8, 31, 0, 0, 0, tzinfo=UTC)),
            ('9780000000422', datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)),
            ('9780000000423', datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)),
        ]
        for isbn, created_at in edges:
            _add_book(
                db,
                publisher,
                isbn,
                title='Pending',
                publication_date=None,
                created_at=created_at,
            )
        db.session.commit()

        books, total = query_service.get_new_books(publication_status='pending')
        assert total == 2
        assert _isbn_set(books) == {'9780000000421', '9780000000422'}

    def test_search_status_days_none_keeps_dates_explicit_days_restricts(self, query_service, db, monkeypatch):
        """搜索 days 默认不限日期；传入 days 后使用同一出版窗口。"""
        _freeze_query_clock(monkeypatch)
        publisher = _add_publisher(db, 'Search Press')
        today = _FROZEN_AT.date()
        created_at = datetime(2026, 9, 15, tzinfo=UTC)
        _add_book(
            db,
            publisher,
            '9780000000431',
            title='Probe Old',
            publication_date=today - timedelta(days=400),
            created_at=created_at,
        )
        _add_book(
            db,
            publisher,
            '9780000000432',
            title='Probe Future',
            publication_date=today + timedelta(days=200),
            created_at=created_at,
        )
        _add_book(
            db,
            publisher,
            '9780000000433',
            title='Probe Current',
            publication_date=today,
            created_at=created_at,
        )
        _add_book(
            db,
            publisher,
            '9780000000434',
            title='Probe Pending',
            publication_date=None,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        db.session.commit()

        published, published_total = query_service.search_books('Probe', publication_status='published')
        assert published_total == 2
        assert _isbn_set(published) == {'9780000000431', '9780000000433'}

        upcoming, upcoming_total = query_service.search_books('Probe', publication_status='upcoming')
        assert upcoming_total == 1
        assert _isbn_set(upcoming) == {'9780000000432'}

        pending, pending_total = query_service.search_books('Probe', publication_status='pending')
        assert pending_total == 1
        assert _isbn_set(pending) == {'9780000000434'}

        limited, limited_total = query_service.search_books('Probe', days=30, publication_status='published')
        assert limited_total == 1
        assert _isbn_set(limited) == {'9780000000433'}

        far, far_total = query_service.search_books('Probe', days=30, publication_status='upcoming')
        assert far_total == 0
        assert far == []

    def test_status_scope_filters_before_pagination(self, query_service, db, monkeypatch):
        """范围条件与状态在分页前生效，total 是全量而不是当前页。"""
        _freeze_query_clock(monkeypatch)
        primary = _add_publisher(db, 'Primary Press', site_display_primary=True)
        other = _add_publisher(db, 'Other Press')
        hidden = _add_publisher(db, 'Hidden Press', site_display_primary=False)
        today = _FROZEN_AT.date()
        created_at = datetime(2026, 9, 20, tzinfo=UTC)
        rows = [
            (primary, '9780000000441', 'Health & Fitness', today, True, None),
            (primary, '9780000000442', '健康养生', today - timedelta(days=1), True, None),
            (primary, '9780000000443', 'Health & Fitness', today - timedelta(days=2), True, None),
            (primary, '9780000000444', 'Health & Fitness', None, True, None),
            (primary, '9780000000445', 'Health & Fitness', today, False, None),
            (other, '9780000000446', 'Health & Fitness', today, True, None),
            (hidden, '9780000000447', 'Health & Fitness', today, True, 'site-batch'),
            (primary, '9780000000448', 'Fiction', today, True, None),
        ]
        for publisher, isbn, category, published_on, displayable, batch_id in rows:
            _add_book(
                db,
                publisher,
                isbn,
                title='Combo Shelf',
                category=category,
                publication_date=published_on,
                created_at=created_at,
                is_displayable=displayable,
                batch_id=batch_id,
            )
        db.session.commit()

        page1, total = query_service.get_new_books(
            publisher_id=primary.id,
            category='Health & Fitness',
            publication_status='published',
            page=1,
            per_page=2,
        )
        page2, total_page2 = query_service.get_new_books(
            publisher_id=primary.id,
            category='健康养生',
            publication_status='published',
            page=2,
            per_page=2,
        )
        assert total == 3
        assert total_page2 == 3
        assert len(page1) == 2
        assert len(page2) == 1
        assert _isbn_set(page1) == {'9780000000441', '9780000000442'}
        assert _isbn_set(page1) | _isbn_set(page2) == {
            '9780000000441',
            '9780000000442',
            '9780000000443',
        }

        searched, search_total = query_service.search_books(
            'Combo Shelf',
            publisher_id=primary.id,
            category='健康养生',
            publication_status='published',
            page=1,
            per_page=2,
        )
        assert search_total == 3
        assert len(searched) == 2
        assert _isbn_set(searched) == {'9780000000441', '9780000000442'}
        query_service._translation_pipeline._hydrate_language_pack.assert_called()
