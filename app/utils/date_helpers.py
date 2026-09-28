import json
from datetime import date, datetime


def format_chinese_date(value: date) -> str:
    """Format a date with Chinese separators without relying on the OS locale.

    ``strftime`` delegates formatting to the platform C runtime. On Windows,
    literal Chinese characters in a format string can fail when the active
    locale uses a non-Unicode code page, so build this display value directly.
    """
    return f'{value.year:04d}年{value.month:02d}月{value.day:02d}日'


def validate_date(date_str: str) -> tuple:
    if not date_str or len(date_str) != 10 or date_str[4] != '-' or date_str[7] != '-':
        return False, '日期格式错误', None
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        current_date = datetime.now().date()
        if date_obj.year < 2020 or date_obj > current_date:
            return False, '无效的日期范围', None
        return True, None, date_obj
    except ValueError:
        return False, '日期格式错误', None


def parse_report_content(report) -> dict | None:
    """解析周报 content。只接受 JSON 对象；其它合法 JSON 视为缺失。

    若内容的顶层为字符串、数组或数字，那些值不是字段映射。调用方若拿去
    ``dict()`` / ``.get()`` 会抛错，一条这样的报告就能让周报列表整页失败。
    这里返回 None，展示层按「总量未知」处理，不把缺失写成 0，也不改存储列。
    """
    if not report or not report.content:
        return None
    try:
        content = json.loads(report.content) if isinstance(report.content, str) else report.content
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(content, dict):
        return None
    return content
