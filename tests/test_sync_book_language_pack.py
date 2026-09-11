"""scripts/sync_book_language_pack.py 合并写入的回归测试。"""

from scripts.sync_book_language_pack import _merge_book


class TestMergeBook:
    def test_skips_language_marker_details(self):
        """上游 cache 里的「英文」不得被合并进权威语言包。

        回归：该函数曾无条件复制 details_zh，把 88 条「英文 / - 英文 / 小说」固化进
        static/data/book_language_pack.zh.json（其中 32 本当时在榜），页面渲染成
        「详情: 英文」。
        """
        target = {'isbn13': '9780143127550'}
        source = {
            'isbn13': '9780143127550',
            'details': 'Detailed description',
            'details_zh': '英文',
        }

        _merge_book(target, source)

        assert 'details_zh' not in target
        assert target['details'] == 'Detailed description'

    def test_keeps_real_details_zh(self):
        target = {'isbn13': '9780143127550'}
        source = {'details_zh': '最初由Viking Penguin于2014年出版。'}

        _merge_book(target, source)

        assert target['details_zh'] == '最初由Viking Penguin于2014年出版。'

    def test_does_not_overwrite_existing_values(self):
        target = {'title_zh': '已有书名', 'details_zh': '已有详情'}
        source = {'title_zh': '新书名', 'details_zh': '新详情'}

        _merge_book(target, source)

        assert target['title_zh'] == '已有书名'
        assert target['details_zh'] == '已有详情'
