"""日期辅助函数测试。"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.utils.date_helpers import format_chinese_date, parse_report_content


def test_format_chinese_date_is_locale_independent() -> None:
    assert format_chinese_date(date(2026, 7, 27)) == '2026年07月27日'


@pytest.mark.parametrize('raw', ['"broken"', '[1]', '1', 'null', 'true'])
def test_parse_report_content_rejects_non_object_json(raw: str) -> None:
    report = SimpleNamespace(content=raw, summary='keep')
    assert parse_report_content(report) is None
    assert report.content == raw
    assert report.summary == 'keep'
