"""Sync the CIRCE title override onto the HuggingFace Space snapshot."""

from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

OVERRIDE_PY = '''"""翻译覆盖映射（ISBN → 人工校正译文字段）。"""

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
'''


def _require(needle: str, haystack: str, label: str) -> None:
    if needle not in haystack:
        raise SystemExit(f'{label} patch target not found')


def patch_book_py(source: str) -> str:
    old = (
        "        data['title_zh'] = quick_clean_translation(self.title_zh, 'title')\n"
        "        data['description_zh'] = quick_clean_translation(self.description_zh, 'description')\n"
        "        data['details_zh'] = quick_clean_translation(self.details_zh, 'details')\n"
        "        return data\n"
    )
    new = (
        "        data['title_zh'] = quick_clean_translation(self.title_zh, 'title')\n"
        "        data['description_zh'] = quick_clean_translation(self.description_zh, 'description')\n"
        "        data['details_zh'] = quick_clean_translation(self.details_zh, 'details')\n"
        "        from ..utils.translation_overrides import apply_translation_overrides\n"
        "\n"
        "        apply_translation_overrides(data)\n"
        "        return data\n"
    )
    _require(old, source, 'book.py to_dict')
    if 'apply_translation_overrides' in source:
        return source
    return source.replace(old, new, 1)


def patch_detail_service(source: str) -> str:
    if 'from ..utils.translation_overrides import' in source:
        return source
    old_import = 'from ..utils import clean_translation_text\n'
    new_import = (
        'from ..utils import clean_translation_text\n'
        'from ..utils.translation_overrides import apply_translation_overrides\n'
    )
    _require(old_import, source, 'book_detail_service import')
    source = source.replace(old_import, new_import, 1)

    old_assign = (
        "            if meta.title_zh and not book.get('title_zh'):\n"
        "                book['title_zh'] = clean_translation_text(meta.title_zh, 'title')\n"
    )
    new_assign = (
        "            if meta.title_zh and not book.get('title_zh'):\n"
        "                book['title_zh'] = clean_translation_text(meta.title_zh, 'title')\n"
        "            apply_translation_overrides(book)\n"
    )
    _require(old_assign, source, 'book_detail_service title_zh')
    return source.replace(old_assign, new_assign, 1)


def main() -> None:
    token = os.environ['HF_TOKEN']
    repo = os.environ['HF_SPACE_REPO']
    api = HfApi(token=token)

    book_src = Path(
        hf_hub_download(
            repo_id=repo, repo_type='space', filename='app/models/book.py', token=token
        )
    ).read_text(encoding='utf-8')
    detail_src = Path(
        hf_hub_download(
            repo_id=repo,
            repo_type='space',
            filename='app/services/book_detail_service.py',
            token=token,
        )
    ).read_text(encoding='utf-8')

    Path('book.py').write_text(patch_book_py(book_src), encoding='utf-8')
    Path('book_detail_service.py').write_text(patch_detail_service(detail_src), encoding='utf-8')
    Path('translation_overrides.py').write_text(OVERRIDE_PY, encoding='utf-8')

    api.create_commit(
        repo_id=repo,
        repo_type='space',
        operations=[
            CommitOperationAdd(
                path_in_repo='app/utils/translation_overrides.py',
                path_or_fileobj=Path('translation_overrides.py').read_bytes(),
            ),
            CommitOperationAdd(
                path_in_repo='app/models/book.py',
                path_or_fileobj=Path('book.py').read_bytes(),
            ),
            CommitOperationAdd(
                path_in_repo='app/services/book_detail_service.py',
                path_or_fileobj=Path('book_detail_service.py').read_bytes(),
            ),
        ],
        commit_message='fix: apply CIRCE title override (喀耳刻) on HuggingFace Space',
    )
    print('Uploaded CIRCE translation override to the Space.')


if __name__ == '__main__':
    main()
