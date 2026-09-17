from typing import cast

from flask import current_app

from .ranking import classify_listing


def get_category_update_frequency(category_id: str) -> str:
    return cast('str', current_app.config['NYT_CATEGORY_UPDATE_FREQUENCIES'].get(category_id, 'weekly'))


_SEARCH_FIELDS = ('title', 'title_zh', 'author', 'author_zh')


def _search_field_text(book: dict, field: str) -> str:
    """安全地把检索字段归一为小写文本；None / 缺失统一当作空串。"""
    value = book.get(field)
    return '' if value is None else str(value).casefold()


def filter_books_by_search(books_data: list, search_query: str | None) -> list:
    if not books_data:
        return books_data

    query = (search_query or '').strip()
    if not query:
        return books_data

    search_lower = query.casefold()
    return [b for b in books_data if any(search_lower in _search_field_text(b, field) for field in _SEARCH_FIELDS)]


def filter_books_by_publisher(books_data: list, publisher: str) -> list:
    if not publisher or not books_data:
        return books_data
    publisher_lower = publisher.lower()
    return [b for b in books_data if publisher_lower in b.get('publisher', '').lower()]


def filter_books_by_weeks(books_data: list, weeks_filter: str) -> list:
    if not weeks_filter or not books_data:
        return books_data

    if weeks_filter == 'new':
        return [b for b in books_data if classify_listing(b.get('rank_last_week'), b.get('weeks_on_list')).is_new]
    elif weeks_filter == 'trending':
        return [b for b in books_data if 2 <= b.get('weeks_on_list', 0) <= 4]
    elif weeks_filter == 'classic':
        return [b for b in books_data if b.get('weeks_on_list', 0) >= 5]
    return books_data


def sort_books(books_data: list, sort_by: str) -> list:
    if not books_data:
        return books_data

    if sort_by == 'rank_change':

        def rank_change_key(b):
            try:
                last_week = int(b.get('rank_last_week', '0') or '0')
                current = b.get('rank', 999)
                return abs(last_week - current) if last_week > 0 else 0
            except (ValueError, TypeError):
                return 0

        return sorted(books_data, key=rank_change_key, reverse=True)

    elif sort_by == 'weeks_desc':
        return sorted(books_data, key=lambda b: b.get('weeks_on_list', 0), reverse=True)

    elif sort_by == 'weeks_asc':
        return sorted(books_data, key=lambda b: b.get('weeks_on_list', 999))

    return books_data
