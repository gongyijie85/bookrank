"""日期辅助函数测试。"""

from datetime import date

from app.utils.date_helpers import format_chinese_date


def test_format_chinese_date_is_locale_independent() -> None:
    assert format_chinese_date(date(2026, 7, 27)) == '2026年07月27日'
