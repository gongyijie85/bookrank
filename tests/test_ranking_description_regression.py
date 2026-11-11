"""Known incorrect ranking descriptions are corrected only when the old value matches."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.book_language_pack import BookLanguagePack

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / 'tests/fixtures/ranking-description-regressions-20261111.json').read_text(encoding='utf-8'))
RECOVERED = json.loads(
    (ROOT / 'tests/fixtures/ranking-description-recovered-20261111.json').read_text(encoding='utf-8')
)


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['isbn'])
def test_reviewed_ranking_description_replaces_only_known_bad_text(case):
    pack = BookLanguagePack(ROOT / 'static/data/book_language_pack.zh.json')
    book = {'isbn13': case['isbn'], 'description_zh': case['old_description_zh']}
    with (
        patch.object(pack, 'get_book_metadata_translations', return_value={}),
        patch.object(pack, '_apply_exact_text_cache'),
    ):
        pack.hydrate_books([book])
        assert book['description_zh'] == case['expected_description_zh']
        book['description_zh'] = '其他已存在的中文简介。'
        pack.hydrate_books([book])
        assert book['description_zh'] == '其他已存在的中文简介。'


@pytest.mark.parametrize('case', RECOVERED, ids=lambda case: case['isbn'])
def test_ranking_description_can_be_filled_from_verified_source_when_nyt_has_no_summary(case):
    pack = BookLanguagePack(ROOT / 'static/data/book_language_pack.zh.json')
    book = {'isbn13': case['isbn'], 'description': '', 'description_zh': None}
    with (
        patch.object(pack, 'get_book_metadata_translations', return_value={}),
        patch.object(pack, '_apply_exact_text_cache'),
    ):
        pack.hydrate_books([book])
    assert book['description'] == ''
    assert book['description_zh'] == case['description_zh']
