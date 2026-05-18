import hashlib
from dataclasses import asdict, dataclass


@dataclass
class Book:
    """书籍数据类"""

    id: str
    title: str
    author: str
    publisher: str
    cover: str
    list_name: str
    category_id: str
    category_name: str
    rank: int
    weeks_on_list: int
    rank_last_week: str
    published_date: str
    description: str
    details: str
    publication_dt: str
    page_count: str
    language: str
    buy_links: list[dict]
    isbn13: str
    isbn10: str
    price: str
    title_zh: str | None = None
    description_zh: str | None = None
    details_zh: str | None = None

    def to_dict(self) -> dict:
        from ..utils import quick_clean_translation

        data = asdict(self)
        data['title_zh'] = quick_clean_translation(self.title_zh, 'title')
        data['description_zh'] = quick_clean_translation(self.description_zh, 'description')
        data['details_zh'] = quick_clean_translation(self.details_zh, 'details')
        return data

    @classmethod
    def _is_valid_isbn(cls, value: str) -> bool:
        """校验字符串是否为合法 ISBN-10 或 ISBN-13"""
        if not value:
            return False
        import re
        clean = re.sub(r'[\s\-]', '', value)
        if len(clean) == 13 and clean.startswith(('978', '979')) and clean.isdigit():
            return True
        if len(clean) == 10:
            prefix = clean[:9]
            suffix = clean[9]
            if prefix.isdigit() and (suffix.isdigit() or suffix.upper() == 'X'):
                return True
        return False

    @classmethod
    def from_api_response(
        cls,
        book_data: dict,
        category_id: str,
        category_name: str,
        list_name: str,
        published_date: str,
        supplement: dict,
    ) -> 'Book':
        """从API响应创建Book对象"""
        raw_isbn13 = book_data.get('primary_isbn13', '')
        raw_isbn10 = book_data.get('primary_isbn10', '')
        isbn = raw_isbn13 if cls._is_valid_isbn(raw_isbn13) else ''
        if not isbn:
            isbn = raw_isbn10 if cls._is_valid_isbn(raw_isbn10) else ''
        if not isbn:
            id_str = f'{book_data.get("title", "")}-{book_data.get("author", "")}'
            isbn = hashlib.md5(id_str.encode()).hexdigest()[:13]

        price_value = book_data.get('price')
        try:
            final_price = str(price_value) if price_value and float(price_value) > 0 else '未知'
        except (ValueError, TypeError):
            final_price = '未知'

        buy_links = [
            {'name': link.get('name', ''), 'url': link.get('url', '')}
            for link in book_data.get('buy_links', [])
            if link.get('url')
        ]

        return cls(
            id=isbn,
            title=book_data.get('title', 'Unknown Title'),
            author=book_data.get('author', 'Unknown Author'),
            publisher=book_data.get('publisher', 'Unknown Publisher'),
            cover='',
            list_name=list_name,
            category_id=category_id,
            category_name=category_name,
            rank=book_data.get('rank', 0),
            weeks_on_list=book_data.get('weeks_on_list', 0),
            rank_last_week=book_data.get('rank_last_week', '无'),
            published_date=published_date,
            description=book_data.get('description', 'No summary available.'),
            details=supplement.get('details', 'No detailed description available.'),
            publication_dt=supplement.get('publication_dt', 'Unknown'),
            page_count=str(supplement.get('page_count', 'Unknown')),
            language=supplement.get('language', 'Unknown'),
            buy_links=buy_links,
            isbn13=raw_isbn13 if cls._is_valid_isbn(raw_isbn13) else '',
            isbn10=raw_isbn10 if cls._is_valid_isbn(raw_isbn10) else '',
            price=final_price,
        )
