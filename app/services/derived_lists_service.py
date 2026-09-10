"""派生榜单：在 NYT 13 个分类榜之上做二次加工，不引入新数据源。

- 跨榜现象级：同一本书进入 >= 2 个分类榜
- 厂牌榜：按出版社聚合的上榜成绩
- 遗珠榜：获过国际奖项、但当前不在任何 NYT 榜上的书

全部为纯函数，输入是调用方已经取好的数据，便于单测与复用。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..utils.book_keys import book_match_key

UNKNOWN_PUBLISHERS = {'', 'unknown', 'unknown publisher', '未知'}
# 与首页一致：本地封面缓存未就绪时 cover 是占位图，此时应回退到 NYT 原始封面 URL
COVER_PLACEHOLDER = '/static/default-cover.png'

# 只做五大集团本名的包含式归并，不猜测子品牌归属：
# NYT 的 publisher 字段混用集团名与 imprint 名（如 "Penguin Random House Hybrid"），
# 归并子品牌需要人工核对的映射表，未核对前宁可分开列。
_GROUP_NAMES: tuple[tuple[str, str], ...] = (
    ('penguin random house', 'Penguin Random House'),
    ('harpercollins', 'HarperCollins'),
    ('harper collins', 'HarperCollins'),
    ('macmillan', 'Macmillan'),
    ('simon & schuster', 'Simon & Schuster'),
    ('simon schuster', 'Simon & Schuster'),
    ('hachette', 'Hachette'),
)


@dataclass
class CrossListEntry:
    """跨榜现象级条目"""

    title: str
    author: str
    category_count: int
    best_rank: int
    total_weeks: int
    title_zh: str = ''
    publisher: str = ''
    cover: str = ''
    isbn13: str = ''
    listings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'title': self.title,
            'title_zh': self.title_zh,
            'author': self.author,
            'publisher': self.publisher,
            'cover': self.cover,
            'isbn13': self.isbn13,
            'category_count': self.category_count,
            'best_rank': self.best_rank,
            'total_weeks': self.total_weeks,
            'listings': self.listings,
        }


@dataclass
class PublisherEntry:
    """厂牌榜条目"""

    name: str
    book_count: int
    category_count: int
    best_rank: int
    total_weeks: int
    books: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'book_count': self.book_count,
            'category_count': self.category_count,
            'best_rank': self.best_rank,
            'total_weeks': self.total_weeks,
            'books': self.books,
        }


@dataclass
class OverlookedEntry:
    """遗珠榜条目"""

    id: int
    title: str
    author: str
    latest_year: int
    award_count: int
    title_zh: str = ''
    publisher: str = ''
    isbn13: str = ''
    cover_local_path: str = ''
    cover_original_url: str = ''
    awards: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'title_zh': self.title_zh,
            'author': self.author,
            'publisher': self.publisher,
            'isbn13': self.isbn13,
            'cover_local_path': self.cover_local_path,
            'cover_original_url': self.cover_original_url,
            'latest_year': self.latest_year,
            'award_count': self.award_count,
            'awards': self.awards,
        }


def normalize_publisher(raw: object) -> str:
    """把 NYT 的 publisher 署名归一为可聚合的厂牌名；无法识别时返回空串。"""
    text = str(raw or '').strip()
    if text.lower() in UNKNOWN_PUBLISHERS:
        return ''
    # 去掉尾部的版本/渠道标注，如 "Penguin Random House (Hybrid)"
    text = text.split('(')[0].strip()
    lowered = text.lower().replace('&', ' and ')
    for needle, group in _GROUP_NAMES:
        if needle.replace('&', ' and ') in lowered:
            return group
    return text


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _cover_of(book: Mapping[str, Any]) -> str:
    """取可用封面：本地缓存封面优先，占位图视为无封面并回退到 NYT 原始 URL。"""
    cover = str(book.get('cover') or '')
    if cover and cover != COVER_PLACEHOLDER:
        return cover
    return str(book.get('_original_cover') or '')


def _collect_listings(books_by_category: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    """按 match_key 聚合每本书在各分类榜的上榜记录。

    同一分类内同一本书可能有多条（不同版本），只保留名次最好的一条。
    """
    aggregated: dict[str, dict[str, Any]] = {}
    for category_id, books in books_by_category.items():
        for book in books:
            key = book_match_key(book.get('title'), book.get('author'))
            if not key:
                continue
            rank = _as_int(book.get('rank'), 999) or 999
            weeks = max(0, _as_int(book.get('weeks_on_list')))
            entry = aggregated.setdefault(
                key,
                {
                    'title': str(book.get('title') or ''),
                    'title_zh': str(book.get('title_zh') or ''),
                    'author': str(book.get('author') or ''),
                    'publisher': str(book.get('publisher') or ''),
                    'cover': _cover_of(book),
                    'isbn13': str(book.get('isbn13') or ''),
                    'best_rank': rank,
                    'total_weeks': 0,
                    'by_category': {},
                },
            )
            if not entry['title_zh'] and book.get('title_zh'):
                entry['title_zh'] = str(book['title_zh'])
            if not entry['cover']:
                entry['cover'] = _cover_of(book)
            previous = entry['by_category'].get(category_id)
            if previous is None or rank < int(previous['rank']):
                entry['by_category'][category_id] = {
                    'category_id': category_id,
                    'category_name': str(book.get('category_name') or category_id),
                    'rank': rank,
                    'weeks_on_list': weeks,
                }
            entry['best_rank'] = min(int(entry['best_rank']), rank)
    for entry in aggregated.values():
        entry['total_weeks'] = sum(int(item['weeks_on_list']) for item in entry['by_category'].values())
    return aggregated


def _to_entry(record: dict[str, Any], listings: list[dict[str, Any]]) -> CrossListEntry:
    """把聚合记录 + 已排序的各分类上榜明细组装成条目"""
    return CrossListEntry(
        title=str(record['title']),
        title_zh=str(record['title_zh']),
        author=str(record['author']),
        publisher=str(record['publisher']),
        cover=str(record['cover']),
        isbn13=str(record['isbn13']),
        best_rank=int(record['best_rank']),
        total_weeks=int(record['total_weeks']),
        category_count=len(listings),
        listings=listings,
    )


def build_cross_list_entries(
    books_by_category: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    min_categories: int = 2,
    limit: int | None = None,
) -> list[CrossListEntry]:
    """跨榜现象级：同时出现在多个 NYT 分类榜的书。"""
    entries: list[CrossListEntry] = []
    for record in _collect_listings(books_by_category).values():
        listings = sorted(record['by_category'].values(), key=lambda item: int(item['rank']))
        if len(listings) < min_categories:
            continue
        entries.append(_to_entry(record, listings))
    entries.sort(key=lambda e: (-e.category_count, e.best_rank, -e.total_weeks, e.title.lower()))
    return entries[:limit] if limit else entries


def build_longevity_entries(
    books_by_category: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    limit: int | None = 20,
) -> list[CrossListEntry]:
    """长销常青榜：按各分类榜合计在榜周数排序，含只守着一个分类榜的书。

    注意口径是"当前在榜累计周数"，不是本年度累计；真正的年度榜要靠 list_snapshots
    积累若干周之后才能算。
    """
    entries = [
        _to_entry(record, sorted(record['by_category'].values(), key=lambda item: int(item['rank'])))
        for record in _collect_listings(books_by_category).values()
    ]
    ranked = [entry for entry in entries if entry.total_weeks > 0]
    ranked.sort(key=lambda e: (-e.total_weeks, e.best_rank, e.title.lower()))
    return ranked[:limit] if limit else ranked


def build_publisher_entries(
    books_by_category: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    limit: int | None = None,
) -> list[PublisherEntry]:
    """厂牌榜：按出版社聚合的上榜本数、覆盖分类数与最好名次。"""
    buckets: dict[str, dict[str, Any]] = {}
    for key, record in _collect_listings(books_by_category).items():
        group = normalize_publisher(record['publisher'])
        if not group:
            continue
        bucket = buckets.setdefault(
            group, {'keys': set(), 'categories': set(), 'best_rank': 999, 'weeks': 0, 'books': []}
        )
        bucket['keys'].add(key)
        bucket['categories'].update(record['by_category'])
        bucket['best_rank'] = min(bucket['best_rank'], int(record['best_rank']))
        bucket['weeks'] += int(record['total_weeks'])
        bucket['books'].append(
            {
                'title': record['title'],
                'title_zh': record['title_zh'],
                'author': record['author'],
                'cover': record['cover'],
                'best_rank': int(record['best_rank']),
                'isbn13': record['isbn13'],
            }
        )

    entries: list[PublisherEntry] = []
    for name, bucket in buckets.items():
        books = sorted(bucket['books'], key=lambda b: (int(b['best_rank']), str(b['title']).lower()))
        entries.append(
            PublisherEntry(
                name=name,
                book_count=len(bucket['keys']),
                category_count=len(bucket['categories']),
                best_rank=int(bucket['best_rank']),
                total_weeks=int(bucket['weeks']),
                books=books,
            )
        )
    entries.sort(key=lambda e: (-e.book_count, e.best_rank, -e.category_count, e.name.lower()))
    return entries[:limit] if limit else entries


def build_overlooked_entries(
    award_books: Sequence[Mapping[str, Any]],
    books_by_category: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    limit: int | None = None,
) -> list[OverlookedEntry]:
    """遗珠榜：获过奖、但当前不在任何 NYT 分类榜上的书。

    同样按归一化书名 + 作者判定"在榜"，因为获奖版本的 ISBN 通常与在榜版本不同。
    """
    listed_keys = set(_collect_listings(books_by_category))
    grouped: dict[str, dict[str, Any]] = {}
    for book in award_books:
        key = book_match_key(book.get('title'), book.get('author'))
        if not key or key in listed_keys:
            continue
        year = _as_int(book.get('year'))
        record = grouped.setdefault(
            key,
            {
                'id': _as_int(book.get('id')),
                'title': str(book.get('title') or ''),
                'title_zh': str(book.get('title_zh') or ''),
                'author': str(book.get('author') or ''),
                'publisher': str(book.get('publisher') or ''),
                'isbn13': str(book.get('isbn13') or ''),
                'cover_local_path': str(book.get('cover_local_path') or ''),
                'cover_original_url': str(book.get('cover_original_url') or ''),
                'latest_year': year,
                'awards': [],
            },
        )
        record['latest_year'] = max(int(record['latest_year']), year)
        record['awards'].append(
            {
                'award_name': str(book.get('award_name') or ''),
                'award_name_en': str(book.get('award_name_en') or ''),
                'year': year,
                'category': str(book.get('category') or ''),
            }
        )

    entries: list[OverlookedEntry] = []
    for record in grouped.values():
        awards = sorted(record['awards'], key=lambda a: (-int(a['year']), str(a['award_name'])))
        entries.append(
            OverlookedEntry(
                id=int(record['id']),
                title=record['title'],
                title_zh=record['title_zh'],
                author=record['author'],
                publisher=record['publisher'],
                isbn13=record['isbn13'],
                cover_local_path=record['cover_local_path'],
                cover_original_url=record['cover_original_url'],
                latest_year=int(record['latest_year']),
                award_count=len(awards),
                awards=awards,
            )
        )
    entries.sort(key=lambda e: (-e.latest_year, -e.award_count, e.title.lower()))
    return entries[:limit] if limit else entries
