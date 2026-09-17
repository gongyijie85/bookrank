"""书名卷号标记的提取（展示用）。

背景：卡片标题限 3 行截断（`static/css/browse.css` 的 `.browse-card-title`
`-webkit-line-clamp`），长书名的**尾部**会被裁掉 —— 而卷号恰恰总在尾部
（实测 100 本样本中 55 本书名带 `#NNN`）。同系列各卷因此显示为完全相同的
标题，观感上像站点在重复渲染同一本书。

另有一层：`title_zh` 经常**不含**卷号（同一系列的 7 卷中文名只有 4 种，
且差异仅来自翻译漂移）。所以卷号必须从英文字段提取后单独渲染，
不能依赖中文标题自带。

本模块只负责纯文本拆解，渲染由 `templates/_macros.html` 负责。
"""

from __future__ import annotations

import pytest

from app.utils.book_titles import split_volume_marker


class TestHashNumberMarker:
    """`#NNN` —— 实测最常见的形态（100 本样本中 55 本）。"""

    def test_splits_zero_padded_marker_off_the_end(self) -> None:
        stem, marker = split_volume_marker(
            "The Emperor's Caretaker: I'm Too Happy Living as a Lady-in-Waiting to Leave the Palace #030"
        )
        assert marker == '#030'
        assert stem == ("The Emperor's Caretaker: I'm Too Happy Living as a Lady-in-Waiting to Leave the Palace")

    def test_preserves_zero_padding_for_series_ordering(self) -> None:
        """`#030` 与 `#036` 必须逐字保留，否则又分不清卷次。"""
        _, first = split_volume_marker('Some Long Manga Title #030')
        _, second = split_volume_marker('Some Long Manga Title #036')
        assert first == '#030'
        assert second == '#036'

    def test_tolerates_space_after_hash_and_normalises_it(self) -> None:
        stem, marker = split_volume_marker('Some Title # 42')
        assert marker == '#42'
        assert stem == 'Some Title'

    def test_chinese_title_with_hash_marker_is_supported(self) -> None:
        stem, marker = split_volume_marker('你有过恋爱经历，而我没有：我们的约会故事#052')
        assert marker == '#052'
        assert stem == '你有过恋爱经历，而我没有：我们的约会故事'


class TestVolumeWordMarker:
    """`Volume N` / `Vol. N` —— 实测 2 本；只在**尾部**才算卷号。"""

    def test_trailing_volume_number(self) -> None:
        stem, marker = split_volume_marker('Tsubasa Volume 2')
        assert marker == 'Volume 2'
        assert stem == 'Tsubasa'

    def test_trailing_abbreviated_volume_number(self) -> None:
        stem, marker = split_volume_marker('Some Series Vol. 3')
        assert marker == 'Vol. 3'
        assert stem == 'Some Series'

    def test_mid_title_volume_is_not_a_volume_suffix(self) -> None:
        """`Tsubasa Volume 2 The Golden Duo` 的卷号在中间 —— 剥掉会破坏书名。"""
        stem, marker = split_volume_marker('Tsubasa Volume 2 The Golden Duo')
        assert marker == ''
        assert stem == 'Tsubasa Volume 2 The Golden Duo'


class TestChineseVolumeMarker:
    """`第N卷/册/部` —— 实测 3 本。"""

    def test_trailing_arabic_numeral(self) -> None:
        stem, marker = split_volume_marker('地狱使者复刻版第1卷')
        assert marker == '第1卷'
        assert stem == '地狱使者复刻版'

    def test_trailing_chinese_numeral(self) -> None:
        stem, marker = split_volume_marker('某系列第三册')
        assert marker == '第三册'
        assert stem == '某系列'

    def test_mid_title_chinese_volume_is_not_a_suffix(self) -> None:
        """`足球小将 第二卷：黄金搭档` 的卷号在中间，后面还有副标题。"""
        stem, marker = split_volume_marker('足球小将 第二卷：黄金搭档')
        assert marker == ''
        assert stem == '足球小将 第二卷：黄金搭档'


class TestNoMarker:
    @pytest.mark.parametrize(
        'title',
        [
            'Dune',
            'Mischief and Monsters',
            'Tu caballo',
            'The Subtle Art of Not Giving a F*ck Tenth Anniversary Edition',
        ],
    )
    def test_plain_title_is_returned_unchanged(self, title: str) -> None:
        stem, marker = split_volume_marker(title)
        assert marker == ''
        assert stem == title

    def test_leading_hash_number_is_not_a_volume_marker(self) -> None:
        """`#1 Bestseller ...` 是营销前缀，不是卷号，不能剥。"""
        stem, marker = split_volume_marker('#1 Bestseller in Contemporary Romance')
        assert marker == ''
        assert stem == '#1 Bestseller in Contemporary Romance'


class TestEdgeCases:
    @pytest.mark.parametrize('value', ['', '   ', None])
    def test_empty_input_yields_empty_pair(self, value: str | None) -> None:
        assert split_volume_marker(value) == ('', '')

    def test_stem_is_stripped_of_trailing_whitespace(self) -> None:
        stem, marker = split_volume_marker('Some Title   #07')
        assert marker == '#07'
        assert stem == 'Some Title'

    def test_bare_marker_without_stem_keeps_title_intact(self) -> None:
        """整串只是个 `#07` 时，不能把书名清空。"""
        stem, marker = split_volume_marker('#07')
        assert marker == ''
        assert stem == '#07'
