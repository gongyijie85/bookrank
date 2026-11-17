"""美国国会图书馆（Library of Congress）新书数据源。

LOC 的 `/books/?fo=json` 是官方公开的 JSON 接口（其 robots.txt 只禁 /search、
/cgi-bin 等路径），按出版日期倒序返回带 ISBN、简介、封面的在版条目，可以作为
没有 API key、也没有配额的兜底新书源。

替代关系：Open Library 唯一能给出「新书 + ISBN」的 /search.json 被它自己的
robots.txt 禁止（Disallow: /search），/subjects 只剩多年以前的热门书，因此
Open Library 在同步列表里保持停用，由本爬虫承担免费的「新书」来源。
"""

import logging
import re
from datetime import date, datetime

from ...utils.error_handler import ErrorCategory, log_error
from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig, CrawlRequest

logger = logging.getLogger(__name__)

_HTML_TAG = re.compile(r'<[^>]+>')
_NON_DIGIT = re.compile(r'[^0-9Xx]')


class LibraryOfCongressCrawler(BaseCrawler):
    """国会图书馆图书 API 爬虫（无 API key、无配额）。"""

    PUBLISHER_NAME = '美国国会图书馆'
    PUBLISHER_NAME_EN = 'Library of Congress'
    PUBLISHER_WEBSITE = 'https://www.loc.gov'
    CRAWLER_CLASS_NAME = 'LibraryOfCongressCrawler'

    #: robots.txt 里写明 Crawl-Delay: 5，请求间隔不得低于此值
    REQUEST_DELAY = 5.0

    BASE_URL = 'https://www.loc.gov/books/'
    RECENCY_YEARS = 2

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        self.config.request_delay = self.REQUEST_DELAY
        self.config.max_pages = 1  # 一次请求最多返回 100 条，够一轮同步用

    def _iter_new_books(self, request: CrawlRequest):
        """按出版日期倒序取近期在版图书。"""
        max_books = request.max_books
        current_year = datetime.now().year
        min_year = current_year - self.RECENCY_YEARS
        max_year = current_year + 1  # 上界挡掉出版社排期里过分久远的年份
        limit = min(max_books * 2, 100)

        url = f'{self.BASE_URL}?fo=json&dates={min_year}/{max_year}&c={limit}&sb=date_desc'
        logger.info('正在从 Library of Congress 获取 %s-%s 年新书...', min_year, max_year)

        response = self._make_request(url)
        if not response:
            logger.error('无法获取 Library of Congress 数据: %s', url)
            return

        try:
            payload = response.json()
        except ValueError as error:
            log_error(ErrorCategory.CRAWLER, f'解析 Library of Congress 响应失败: {error}')
            return

        results = payload.get('results') or []
        count = 0
        for record in results:
            if count >= max_books:
                break
            book = self._parse_record(record)
            if book is None:
                continue
            yield book
            count += 1

    def _parse_record(self, record: dict) -> BookInfo | None:
        """解析单条 LOC 记录；没有 ISBN 的记录不入库。"""
        try:
            title = (record.get('title') or '').strip()
            if not title:
                return None

            item = record.get('item') or {}
            isbn13, isbn10 = self._pick_isbn(item.get('isbn') or [])
            if not isbn13 and not isbn10:
                # 下游按 ISBN 去重/补全，27% 左右有 ISBN，其余跳过而不是塞脏数据
                return None

            contributors = [name for name in (record.get('contributor') or []) if name]
            author = ', '.join(contributors[:3]) or 'Unknown Author'

            descriptions = record.get('description') or []
            description = self._clean_html(descriptions[0]) if descriptions else None

            covers = record.get('image_url') or []
            cover_url = covers[0] if covers else None

            subjects = [subject for subject in (record.get('subject') or []) if subject]
            languages = record.get('language') or []

            return BookInfo(
                title=title,
                author=author,
                isbn13=isbn13,
                isbn10=isbn10,
                description=description,
                cover_url=cover_url,
                category=subjects[0] if subjects else '新书',
                publication_date=self._parse_date(record.get('date')),
                language=languages[0] if languages else 'English',
                buy_links=self._build_buy_links(isbn13, isbn10),
                source_url=record.get('id') or record.get('url'),
            )
        except Exception as error:
            log_error(ErrorCategory.CRAWLER, f'解析 LOC 记录失败: {error}', level='warning')
            return None

    @staticmethod
    def _pick_isbn(raw_isbns: list) -> tuple[str | None, str | None]:
        for raw in raw_isbns:
            digits = _NON_DIGIT.sub('', str(raw))
            if len(digits) == 13:
                return digits, None
            if len(digits) == 10:
                return None, digits.upper()
        return None, None

    @staticmethod
    def _clean_html(text: str, limit: int = 2000) -> str | None:
        plain = _HTML_TAG.sub(' ', text)
        plain = ' '.join(plain.split())
        return plain[:limit] or None

    @staticmethod
    def _parse_date(raw: str | None) -> date | None:
        if not raw:
            return None
        for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
            try:
                parsed = datetime.strptime(raw.strip(), fmt)
            except (ValueError, TypeError):
                continue
            return parsed.date()
        return None

    @staticmethod
    def _build_buy_links(isbn13: str | None, isbn10: str | None) -> list[dict[str, str]]:
        if not isbn13:
            return []
        return [
            {'name': 'Amazon', 'url': f'https://www.amazon.com/s?k={isbn13}'},
            {'name': 'Barnes & Noble', 'url': f'https://www.barnesandnoble.com/s/{isbn13}'},
        ]
