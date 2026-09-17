"""``scripts/backfill_inflated_translations.py`` 的回归测试。

覆盖三件事：

1. **识别**：注水行（长度暴涨 / 上下文元信息泄漏 / details 字段）被找出来；
2. **不误伤**：长但忠实的译文、以及正常译文（en 123 → zh 115）一条都不能命中
   —— 这是本脚本最大的风险（宁可漏清，不能错清，清空是不可逆的）；
3. **写入语义**：dry-run 不写任何东西，``--apply`` 才写；清空后该列是 NULL
   （不是空字符串），且 DB / 语言包 / 翻译缓存三层一起清。

长度关系全部由 ``_en`` / ``_zh`` 按精确字符数构造，故用例里的「倍数」可复现。
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from sqlalchemy import text

from app.models.schemas import APICache, BookMetadata, TranslationCache
from app.services.translation_cache_service import TranslationCacheService
from scripts.backfill_inflated_translations import (
    EnglishSource,
    apply_clears,
    find_inflated_rows,
    main,
    scrub_pack_document,
)

AUTHOR = 'Test Author'

ISBN_INFLATED = '9781419788109'
ISBN_LEAK = '9781501191234'
ISBN_DETAILS = '9780593135204'
ISBN_NORMAL = '9780062796200'
ISBN_FAITHFUL = '9780143127550'
ISBN_DECOY = '9781984821234'
ISBN_MISSING = '9781668031575'


def _en(text: str, total: int) -> str:
    """把英文原文补到精确字符数（补一句中性英文，必要时截断）。"""
    filler = ' It is a story about people and the choices they make.'
    while len(text) < total:
        text += filler
    return text[:total]


def _zh(text: str, total: int) -> str:
    """把中文补到精确字符数（与 test_translation_inflation_guard._pad 同法）。"""
    assert len(text) <= total, f'{len(text)} > {total}'
    return text + '的' * (total - len(text))


#: 生产实测的注水样本：英文 73 字符 → 中文 311 字符（4.26 倍）
EN_SHORT = _en('Greg Heffley is back at school and a new kid outshines him at everything.', 73)
ZH_INFLATED = _zh('《超棒又友善的孩子》（AWESOME FRIENDLY KID）由杰夫·金尼创作，描写格雷格与新同学之间的较量。', 311)

#: 翻译时喂给模型的图书上下文（出版社 / 榜单 / 系列都不该出现在译文里）
CONTEXT = {
    'publisher': 'Amulet',
    'list_name': "Children's & Young Adult Series",
    'category_name': '儿童与青少年',
    'series': 'Diary of a Wimpy Kid',
}

#: 长度正常但把出版社写进译文 —— 只能靠元信息泄漏规则判出来
EN_LEAK = _en(
    'Two estranged sisters meet again at their childhood home after their father dies, '
    'and the funeral forces them to reopen a case the whole town agreed to forget.',
    230,
)
ZH_LEAK = _zh('本书由 Scribner 出版，讲述一对疏远的姐妹在父亲去世后重逢，并重新面对家族旧事的故事。', 210)
CONTEXT_LEAK = {'publisher': 'Scribner'}

#: details 字段的注水样本（该字段没有英文原文可用，只能按长度比率判）
EN_DETAILS = _en('First published in 2014 by Viking Penguin, this novel was an instant bestseller.', 73)
ZH_DETAILS = _zh('最初由维京企鹅出版社于二〇一四年出版，该书当年即登上畅销榜，并获得了多项年度图书提名。', 300)

#: 正常译文：中文比英文短（实测中位数约 0.42 倍），必须一条都不命中
EN_NORMAL = _en(
    'A retired detective returns to the small town where he grew up to investigate a case that everyone else gave up on.',
    123,
)
ZH_NORMAL = _zh(
    '一位退休侦探回到他从小长大的海边小镇，只为调查一桩所有人都已经放弃的旧案。随着线索一点点浮现，'
    '他不得不重新审视自己当年离开这里的原因，以及那段被时间掩埋的往事。',
    115,
)

#: 长但忠实的译文：285 字符，仍是英文原文（300）的 0.95 倍 —— 长度本身不是罪证
EN_LONG = _en(
    'A sweeping family saga following three generations of a fishing village through war, '
    'migration and the slow return of the tide, told through the eyes of the youngest daughter.',
    300,
)
ZH_FAITHFUL = _zh(
    '这是一部跨越三代人的家族史诗。故事发生在一个靠海的小渔村，从战乱讲到迁徙，再讲到潮水缓慢地退回原来的位置；'
    '一切由家中最小的女儿讲述，她记得每个人离开时的样子。',
    285,
)


def _add_book(
    db,
    isbn: str,
    *,
    title: str = 'Test Book',
    description_zh: str | None = None,
    details: str | None = None,
    details_zh: str | None = None,
) -> str:
    db.session.add(
        BookMetadata(
            isbn=isbn,
            title=title,
            author=AUTHOR,
            details=details,
            description_zh=description_zh,
            details_zh=details_zh,
        )
    )
    db.session.commit()
    return isbn


def _source_hash(text: str) -> str:
    return TranslationCacheService._compute_source_hash(text)


def _add_cache_row(db, source_text: str, translated_text: str) -> None:
    db.session.add(
        TranslationCache(
            source_hash=_source_hash(source_text),
            source_text=source_text,
            source_lang='en',
            target_lang='zh',
            translated_text=translated_text,
        )
    )
    db.session.commit()


def _write_pack(tmp_path, books: dict) -> object:
    pack = tmp_path / 'book_language_pack.zh.json'
    pack.write_text(json.dumps({'version': 4, 'books': books}, ensure_ascii=False, indent=2), encoding='utf-8')
    return pack


def _read_pack(pack) -> dict:
    return json.loads(pack.read_text(encoding='utf-8'))


def _hit(isbn: str, field_name: str, translated: str):
    """构造一条 Hit，用于单独验证语言包清理逻辑。"""
    from scripts.backfill_inflated_translations import Hit

    return Hit(
        isbn=isbn,
        title='Test Book',
        field_name=field_name,
        source_text=EN_SHORT,
        translated=translated,
        origin='test',
    )


class TestFindInflatedRows:
    """识别注水行，且不误伤正常译文。"""

    def test_fixture_lengths_match_production(self):
        """锁住样本长度：比率类用例全靠这几个数字成立。"""
        assert len(EN_SHORT) == 73
        assert len(ZH_INFLATED) == 311
        assert len(EN_NORMAL) == 123
        assert len(ZH_NORMAL) == 115

    def test_detects_length_inflated_description(self, db):
        _add_book(db, ISBN_INFLATED, title='AWESOME FRIENDLY KID', description_zh=ZH_INFLATED)

        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        assert [hit.field_name for hit in hits] == ['description_zh']
        assert hits[0].isbn == ISBN_INFLATED
        assert hits[0].translated == ZH_INFLATED
        assert hits[0].ratio > 4
        assert (stats.scanned, stats.hits, stats.unresolved) == (1, 1, 0)

    def test_detects_metadata_leak_without_length_blowup(self, db):
        """长度只差 0.91 倍，但译文里出现了出版社 —— 必须靠元信息规则判出来。"""
        _add_book(db, ISBN_LEAK, description_zh=ZH_LEAK)
        assert len(ZH_LEAK) <= len(EN_LEAK) * 1.5, '本用例验证的是元信息路径，不是长度路径'

        hits, _stats = find_inflated_rows(db.session, {ISBN_LEAK: EnglishSource(EN_LEAK, CONTEXT_LEAK)})

        assert [hit.field_name for hit in hits] == ['description_zh']

    def test_context_from_the_source_is_actually_passed_through(self, db):
        """同一段译文，不带上下文就判不出来 —— 证明脚本把元信息传进了判定。"""
        _add_book(db, ISBN_LEAK, description_zh=ZH_LEAK)

        hits, _stats = find_inflated_rows(db.session, {ISBN_LEAK: EnglishSource(EN_LEAK)})

        assert hits == []

    def test_detects_inflated_details(self, db):
        """details 没有英文原文可用，只按长度比率判；元信息不参与判定。"""
        _add_book(db, ISBN_DETAILS, details=EN_DETAILS, details_zh=ZH_DETAILS)

        hits, _stats = find_inflated_rows(db.session, {})

        assert [hit.field_name for hit in hits] == ['details_zh']
        assert hits[0].source_text == EN_DETAILS

    def test_normal_translation_is_not_flagged(self, db):
        """正常译文（en 123 → zh 115）：中文比英文短，一条都不能命中。"""
        _add_book(db, ISBN_NORMAL, description_zh=ZH_NORMAL)

        hits, stats = find_inflated_rows(db.session, {ISBN_NORMAL: EnglishSource(EN_NORMAL, CONTEXT)})

        assert hits == [], '正常译文被误判 —— 这是本脚本最不可接受的失败'
        assert (stats.scanned, stats.unresolved) == (1, 0), '该行必须真的被扫描过，不能是靠跳过而「没命中」'

    def test_long_but_faithful_translation_is_not_flagged(self, db):
        """长译文不是罪证：285 字符、0.95 倍，判注水会把大量正常长简介清掉。"""
        _add_book(db, ISBN_FAITHFUL, description_zh=ZH_FAITHFUL)

        hits, stats = find_inflated_rows(db.session, {ISBN_FAITHFUL: EnglishSource(EN_LONG, CONTEXT)})

        assert hits == [], '长但忠实的译文被误判'
        assert stats.scanned == 1

    def test_short_source_is_exempt_from_the_ratio_rule(self, db):
        """短简介比率不稳定：中文 110 字符（3.9 倍）但未达绝对长度下限，不判注水。"""
        source = 'A New York Times bestseller.'
        _add_book(db, ISBN_DECOY, description_zh=_zh('纽约时报畅销书。', 110))

        hits, _stats = find_inflated_rows(db.session, {ISBN_DECOY: EnglishSource(source, CONTEXT)})

        assert hits == []

    def test_row_without_english_source_is_counted_unresolved(self, db):
        """找不到英文原文的行只计入 unresolved 并跳过，不做任何猜测。"""
        _add_book(db, ISBN_MISSING, description_zh=ZH_NORMAL)

        hits, stats = find_inflated_rows(db.session, {})

        assert hits == []
        assert (stats.scanned, stats.hits, stats.unresolved) == (1, 0, 1)

    def test_scan_writes_nothing(self, db):
        """dry-run 的安全性：扫描本身只读，跑完 DB 必须原样。"""
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        _add_book(db, ISBN_NORMAL, description_zh=ZH_NORMAL)

        find_inflated_rows(
            db.session,
            {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT), ISBN_NORMAL: EnglishSource(EN_NORMAL, CONTEXT)},
        )

        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_INFLATED).description_zh == ZH_INFLATED
        assert db.session.get(BookMetadata, ISBN_NORMAL).description_zh == ZH_NORMAL

    def test_only_null_rows_are_skipped(self, db):
        """已经清空（NULL）的行不再参与统计，避免重复计数。"""
        _add_book(db, ISBN_INFLATED, description_zh=None)

        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        assert hits == []
        assert stats.scanned == 0


class TestApplyClears:
    """写入语义：NULL 而不是空字符串；三层一起清。"""

    def test_cleared_column_is_null_not_empty_string(self, db):
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        apply_clears(db.session, hits, stats, pack_path=None, clear_pack=False, clear_cache=False)

        assert stats.cleared_db == 1
        assert stats.failures == 0
        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_INFLATED).description_zh is None
        null_rows = db.session.execute(
            text('SELECT COUNT(*) FROM book_metadata WHERE isbn = :isbn AND description_zh IS NULL'),
            {'isbn': ISBN_INFLATED},
        ).scalar()
        assert null_rows == 1, '必须是 NULL —— 空字符串会重新进入渲染与回填路径'

    def test_removes_matching_pack_field_only(self, db, tmp_path):
        """语言包里的同值坏值删掉，同一本书的其它字段保留。"""
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        pack = _write_pack(tmp_path, {ISBN_INFLATED: {'title_zh': '超棒又友善的孩子', 'description_zh': ZH_INFLATED}})
        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        apply_clears(db.session, hits, stats, pack_path=pack)

        entry = _read_pack(pack)['books'][ISBN_INFLATED]
        assert 'description_zh' not in entry
        assert entry['title_zh'] == '超棒又友善的孩子'
        assert stats.cleared_pack == 1
        assert stats.pack_mismatch == 0

    def test_keeps_pack_value_that_differs_from_db(self, db, tmp_path):
        """语言包里的值与 DB 不一致 —— 可能已被人工修正，不能删。"""
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        pack = _write_pack(tmp_path, {ISBN_INFLATED: {'description_zh': '人工修正过的简介'}})
        before = pack.read_bytes()
        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        apply_clears(db.session, hits, stats, pack_path=pack)

        assert _read_pack(pack)['books'][ISBN_INFLATED]['description_zh'] == '人工修正过的简介'
        assert pack.read_bytes() == before, '没有可删的条目就不该写回语言包'
        assert (stats.cleared_pack, stats.pack_mismatch) == (0, 1)

    def test_deletes_only_the_matching_translation_cache_row(self, db):
        """缓存按英文原文哈希精确删除，不能顺手清空整张表。"""
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        _add_cache_row(db, EN_SHORT, ZH_INFLATED)
        _add_cache_row(db, 'An unrelated blurb.', '一条无关的译文。')
        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        apply_clears(db.session, hits, stats, pack_path=None, clear_pack=False)

        assert stats.cleared_cache == 1
        remaining = db.session.query(TranslationCache).all()
        assert [row.source_text for row in remaining] == ['An unrelated blurb.']

    def test_only_db_mode_leaves_pack_and_cache_alone(self, db, tmp_path):
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        _add_cache_row(db, EN_SHORT, ZH_INFLATED)
        pack = _write_pack(tmp_path, {ISBN_INFLATED: {'description_zh': ZH_INFLATED}})
        before = pack.read_bytes()
        hits, stats = find_inflated_rows(db.session, {ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT)})

        apply_clears(db.session, hits, stats, pack_path=pack, clear_pack=False, clear_cache=False)

        assert stats.cleared_db == 1
        assert (stats.cleared_pack, stats.cleared_cache) == (0, 0)
        assert pack.read_bytes() == before
        assert db.session.query(TranslationCache).count() == 1

    def test_good_rows_are_never_touched(self, db):
        """真正的防线：一次清理只动注水行，正常/忠实译文必须原封不动。"""
        _add_book(db, ISBN_INFLATED, description_zh=ZH_INFLATED)
        _add_book(db, ISBN_NORMAL, description_zh=ZH_NORMAL)
        _add_book(db, ISBN_FAITHFUL, description_zh=ZH_FAITHFUL)
        sources = {
            ISBN_INFLATED: EnglishSource(EN_SHORT, CONTEXT),
            ISBN_NORMAL: EnglishSource(EN_NORMAL, CONTEXT),
            ISBN_FAITHFUL: EnglishSource(EN_LONG, CONTEXT),
        }
        hits, stats = find_inflated_rows(db.session, sources)
        assert stats.scanned == 3

        apply_clears(db.session, hits, stats, pack_path=None, clear_pack=False, clear_cache=False)

        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_INFLATED).description_zh is None
        assert db.session.get(BookMetadata, ISBN_NORMAL).description_zh == ZH_NORMAL
        assert db.session.get(BookMetadata, ISBN_FAITHFUL).description_zh == ZH_FAITHFUL


class TestScrubPackDocument:
    def test_removes_entry_when_it_becomes_empty(self):
        doc = {'books': {ISBN_INFLATED: {'description_zh': ZH_INFLATED}}}

        removed, mismatch = scrub_pack_document(
            doc,
            [_hit(ISBN_INFLATED, 'description_zh', ZH_INFLATED)],
        )

        assert (removed, mismatch) == (1, 0)
        assert doc['books'] == {}

    def test_ignores_unknown_isbn_and_non_dict_entry(self):
        doc = {'books': {'9780000000000': {'description_zh': ZH_INFLATED}, ISBN_LEAK: 'not-a-dict'}}

        removed, mismatch = scrub_pack_document(
            doc,
            [_hit(ISBN_INFLATED, 'description_zh', ZH_INFLATED), _hit(ISBN_LEAK, 'description_zh', ZH_INFLATED)],
        )

        assert (removed, mismatch) == (0, 0)
        assert doc['books']['9780000000000']['description_zh'] == ZH_INFLATED

    def test_missing_field_is_not_counted_as_mismatch(self):
        doc = {'books': {ISBN_INFLATED: {'title_zh': '只有书名'}}}

        removed, mismatch = scrub_pack_document(doc, [_hit(ISBN_INFLATED, 'description_zh', ZH_INFLATED)])

        assert (removed, mismatch) == (0, 0)

    def test_non_dict_books_returns_zero(self):
        assert scrub_pack_document({'books': []}, [_hit(ISBN_INFLATED, 'description_zh', ZH_INFLATED)]) == (0, 0)
        assert scrub_pack_document({}, [_hit(ISBN_INFLATED, 'description_zh', ZH_INFLATED)]) == (0, 0)


class TestMainCli:
    """端到端：CLI 的 dry-run / --apply / --only-db 三种走法。"""

    @staticmethod
    def _seed(db, *, with_cache: bool = True) -> None:
        """英文原文只存在于 api_cache 的 NYT 响应里 —— 与线上一致。"""
        _add_book(db, ISBN_INFLATED, title='AWESOME FRIENDLY KID', description_zh=ZH_INFLATED)
        payload = {
            'results': {
                'list_name': "Children's & Young Adult Series",
                'books': [
                    {
                        'primary_isbn13': ISBN_INFLATED,
                        'title': 'AWESOME FRIENDLY KID',
                        'description': EN_SHORT,
                        'publisher': 'Amulet',
                    }
                ],
            }
        }
        db.session.add(
            APICache(
                api_source='nyt',
                request_key='lists/current/childrens-middle-grade.json',
                request_hash='hash-inflated',
                response_data=json.dumps(payload),
            )
        )
        db.session.commit()
        if with_cache:
            _add_cache_row(db, EN_SHORT, ZH_INFLATED)

    @staticmethod
    def _run(app, tmp_path, *extra: str) -> tuple[int, object]:
        pack = _write_pack(tmp_path, {ISBN_INFLATED: {'description_zh': ZH_INFLATED}})
        cache_dir = tmp_path / 'cache'
        static_dir = tmp_path / 'static'
        cache_dir.mkdir(exist_ok=True)
        static_dir.mkdir(exist_ok=True)
        argv = [
            '--pack',
            str(pack),
            '--cache-dir',
            str(cache_dir),
            '--static-data-dir',
            str(static_dir),
            *extra,
        ]
        with patch('app.create_app', return_value=app):
            return main(argv), pack

    def test_dry_run_exits_2_and_writes_nothing(self, db, app, tmp_path):
        self._seed(db)

        code, pack = self._run(app, tmp_path)

        assert code == 2, 'dry-run 发现命中时应返回 2（便于 CI 判定）'
        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_INFLATED).description_zh == ZH_INFLATED
        assert db.session.query(TranslationCache).count() == 1
        assert _read_pack(pack)['books'][ISBN_INFLATED]['description_zh'] == ZH_INFLATED

    def test_apply_clears_all_three_layers(self, db, app, tmp_path):
        self._seed(db)

        code, pack = self._run(app, tmp_path, '--apply')

        assert code == 0
        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_INFLATED).description_zh is None
        assert db.session.query(TranslationCache).count() == 0
        assert ISBN_INFLATED not in _read_pack(pack)['books'], '语言包条目只剩坏值时应整条删除'

    def test_apply_only_db_keeps_pack_and_cache(self, db, app, tmp_path):
        self._seed(db)

        code, pack = self._run(app, tmp_path, '--apply', '--only-db')

        assert code == 0
        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_INFLATED).description_zh is None
        assert db.session.query(TranslationCache).count() == 1
        assert _read_pack(pack)['books'][ISBN_INFLATED]['description_zh'] == ZH_INFLATED

    def test_nothing_to_do_exits_0(self, db, app, tmp_path):
        """没有命中时返回 0，且不碰语言包。"""
        _add_book(db, ISBN_NORMAL, description_zh=ZH_NORMAL)
        db.session.commit()

        code, pack = self._run(app, tmp_path)

        assert code == 0
        db.session.expire_all()
        assert db.session.get(BookMetadata, ISBN_NORMAL).description_zh == ZH_NORMAL
        assert _read_pack(pack)['books'][ISBN_INFLATED]['description_zh'] == ZH_INFLATED

    def test_does_not_leak_the_disabled_scheduler_flag(self, db, app, tmp_path, monkeypatch):
        """回归：main() 曾把 DISABLE_BACKGROUND_THREADS=true 永久留在环境里。

        app/setup.py:240 依此跳过调度器初始化，于是 test_setup_extended 的 5 个
        「应当建调度器 / 应当加任务」的用例在同进程内全红。脚本必须复原原值。
        """
        monkeypatch.delenv('DISABLE_BACKGROUND_THREADS', raising=False)
        self._seed(db)

        self._run(app, tmp_path)

        assert 'DISABLE_BACKGROUND_THREADS' not in os.environ, '未设置过就必须复原为「未设置」'

    def test_restores_a_preexisting_scheduler_flag_value(self, db, app, tmp_path, monkeypatch):
        monkeypatch.setenv('DISABLE_BACKGROUND_THREADS', 'false')
        self._seed(db)

        self._run(app, tmp_path, '--apply')

        assert os.environ['DISABLE_BACKGROUND_THREADS'] == 'false', '调用者原有的值不能被覆盖掉'
