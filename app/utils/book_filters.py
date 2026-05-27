import logging

logger = logging.getLogger(__name__)


def filter_books_by_search(books_data: list, search_query: str) -> list:
    if not search_query or not books_data:
        return books_data

    search_lower = search_query.lower()
    return [
        b
        for b in books_data
        if search_lower in b.get('title', '').lower() or search_lower in b.get('author', '').lower()
    ]


def filter_books_by_publisher(books_data: list, publisher: str) -> list:
    if not publisher or not books_data:
        return books_data
    publisher_lower = publisher.lower()
    return [b for b in books_data if publisher_lower in b.get('publisher', '').lower()]


def filter_books_by_weeks(books_data: list, weeks_filter: str) -> list:
    if not weeks_filter or not books_data:
        return books_data

    if weeks_filter == 'new':
        return [b for b in books_data if b.get('weeks_on_list', 0) <= 1]
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
