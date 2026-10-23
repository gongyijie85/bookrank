"""详情页的进程内数据缓存；缓存值不持有 ORM 对象或请求上下文。"""

import hashlib
import json
from collections.abc import Callable
from typing import Any, cast

from flask import current_app

from ..models.new_book import NewBook, Publisher
from ..models.schemas import Award, AwardBook
from .detail_cache import DetailCache
from .detail_cache_invalidation import has_uncommitted_cache_writes

_AWARD_FIELDS = (
    'id',
    'award_id',
    'year',
    'category',
    'rank',
    'title',
    'title_zh',
    'author',
    'description',
    'description_zh',
    'cover_original_url',
    'cover_local_path',
    'isbn13',
    'isbn10',
    'publisher',
    'publication_year',
    'details',
    'buy_links',
    'is_displayable',
)
_NEW_BOOK_FIELDS = (
    'id',
    'publisher_id',
    'title',
    'title_zh',
    'author',
    'description',
    'description_zh',
    'cover_url',
    'isbn13',
    'isbn10',
    'publication_date',
    'page_count',
    'language',
    'category',
    'price',
    'buy_links',
    'is_displayable',
)


def get_detail_cache() -> DetailCache:
    return cast('DetailCache', current_app.extensions['book_detail_cache'])


def cached_book(kind: str, book_id: int, loader: Callable[[], Any]) -> Any:
    """只存展示字段快照，每次返回独立、未绑定 session 的模型供模板读取。"""
    is_award = kind == 'award'
    fields = _AWARD_FIELDS if is_award else _NEW_BOOK_FIELDS
    relation = 'award' if is_award else 'publisher'
    related_fields = ('id', 'name', 'name_en', 'wikidata_id') if is_award else ('id', 'name', 'name_en')

    def load():
        book = loader()
        if book is None:
            return None
        values = {name: getattr(book, name, None) for name in fields}
        related = getattr(book, relation, None)
        return {
            'book': values,
            'related': {name: getattr(related, name, None) for name in related_fields} if related is not None else None,
        }

    snapshot = load() if has_uncommitted_cache_writes() else get_detail_cache().get_or_load((kind, book_id), load)
    if snapshot is None:
        return None
    model = AwardBook if is_award else NewBook
    related_model = Award if is_award else Publisher
    book = model(**snapshot['book'])
    setattr(book, relation, related_model(**snapshot['related']) if snapshot['related'] is not None else None)
    return book


def cached_bestseller(book: dict, isbn: str, enrich: Callable, merge: Callable) -> dict:
    # 排名/正文变化必须生成新键；URL、Referer 和 return_to 不参与键的生成。
    source_hash = hashlib.sha256(json.dumps(book, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def load() -> dict:
        from copy import deepcopy

        result = deepcopy(book)
        enrich(result, isbn)
        merge(result, isbn)
        return result

    if has_uncommitted_cache_writes():
        return load()
    return cast('dict', get_detail_cache().get_or_load(('bestseller', isbn, source_hash), load))
