"""翻译覆盖映射（ISBN → 人工校正译文字段）。

Book / AwardBook 序列化共用；放在 utils 层避免模型层反向依赖服务层。
"""

from typing import Any

TRANSLATION_OVERRIDES: dict[str, dict[str, Any]] = {
    '9780316556323': {
        'title_zh': '喀耳刻',
    }
}


def apply_translation_overrides(data: dict[str, Any]) -> None:
    """按 ISBN 将人工校正译文覆盖进序列化字典（只覆盖已有键，不新增键）。"""
    isbn = data.get('isbn13') or data.get('isbn10')
    overrides = TRANSLATION_OVERRIDES.get(isbn) if isbn else None
    if not overrides:
        return
    for key, value in overrides.items():
        if value and key in data:
            data[key] = value
