"""
Open Library 新书数据源

Open Library 提供免费的图书数据API，可以获取新出版图书信息。
这是一个更稳定可靠的替代方案，用于替代直接爬取出版社网站。
"""

import logging
from datetime import datetime

from ...utils.error_handler import ErrorCategory, log_error
from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig, CrawlRequest

logger = logging.getLogger(__name__)


class OpenLibraryCrawler(BaseCrawler):
    """
    Open Library 新书爬虫

    使用 Open Library API 获取新书数据，稳定可靠。
    API文档: https://openlibrary.org/developers/api
    """

    PUBLISHER_NAME = 'Open Library'
    PUBLISHER_NAME_EN = 'Open Library'
    PUBLISHER_WEBSITE = 'https://openlibrary.org'
    CRAWLER_CLASS_NAME = 'OpenLibraryCrawler'

    BASE_URL = 'https://openlibrary.org'

    SUBJECT_MAP = {
        'fiction': '小说',
        'nonfiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'thriller': '惊悚',
        'science_fiction': '科幻',
        'fantasy': '奇幻',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young_adult': '青少年',
        'poetry': '诗歌',
        'drama': '戏剧',
        'comics': '漫画',
        'art': '艺术',
        'science': '科学',
        'business': '商业',
        'self_help': '自助',
    }

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 0.5

    def _iter_new_books(self, request: CrawlRequest):
        """
        获取新书列表的生成器实现

        Args:
            request: 抓取请求（category / max_books；backfill 忽略）
        """
        category = request.category
        max_books = request.max_books
        subject = category or 'fiction'
        limit = min(max_books * 2, 100)  # 多获取一些以便过滤

        url = f'{self.BASE_URL}/subjects/{subject}.json?limit={limit}'
        logger.info(f'📚 正在从 Open Library 获取 {subject} 类新书...')

        current_year = datetime.now().year
        min_year = current_year - 2  # 默认近2年

        response = self._make_request(url)
        if not response:
            logger.error(f'❌ 无法获取 Open Library 数据: {url}')
            return

        try:
            data = response.json()
            works = data.get('works', [])

            count = 0
            for work in works:
                if count >= max_books:
                    break

                # 获取出版年份
                publish_year = work.get('first_publish_year')
                if publish_year:
                    try:
                        year = int(publish_year)
                        # 只返回近期出版的书
                        if year < min_year:
                            continue
                    except (ValueError, TypeError):
                        pass

                book_info = self._parse_work(work, subject)
                if book_info:
                    # 标记为新书
                    book_info.category = f'📅 {publish_year}年出版' + (
                        f' - {self.SUBJECT_MAP.get(subject, subject)}'
                        if subject in self.SUBJECT_MAP
                        else f' - {subject}'
                    )
                    yield book_info
                    count += 1

        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'解析 Open Library 数据失败: {e}')

    def _parse_work(self, work: dict, default_category: str) -> BookInfo | None:
        """解析单个书籍数据"""
        try:
            title = work.get('title', 'Unknown Title')
            author_name = work.get('author_name', ['Unknown Author'])[0]

            cover_id = work.get('cover_id')
            cover_url = None
            if cover_id:
                cover_url = f'https://covers.openlibrary.org/b/id/{cover_id}-M.jpg'

            isbn = work.get('isbn', [])
            isbn13 = None
            isbn10 = None
            if isbn:
                first_isbn = isbn[0]
                if len(first_isbn) == 13:
                    isbn13 = first_isbn
                elif len(first_isbn) == 10:
                    isbn10 = first_isbn

            publish_year = work.get('first_publish_year')
            if publish_year:
                try:
                    publication_date = datetime(int(publish_year), 1, 1).date()
                except (ValueError, TypeError):
                    publication_date = None
            else:
                publication_date = None

            subject_name = self.SUBJECT_MAP.get(default_category, default_category)

            return BookInfo(
                title=title,
                author=author_name,
                isbn13=isbn13,
                isbn10=isbn10,
                description=None,
                cover_url=cover_url,
                category=subject_name,
                publication_date=publication_date,
                price=None,
                page_count=None,
                language='English',
                buy_links=self._generate_buy_links(isbn13, isbn10, title),
                source_url=f'{self.BASE_URL}/works/{work.get("key", "")}',
            )

        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'解析书籍数据失败: {e}', level='warning')
            return None

    def _generate_buy_links(self, isbn13: str | None, isbn10: str | None, title: str) -> list[dict[str, str]]:
        """生成购买链接"""
        links = []

        if isbn13:
            links.append(
                {
                    'name': 'Amazon',
                    'url': f'https://www.amazon.com/s?k={isbn13}',
                }
            )
            links.append(
                {
                    'name': 'Barnes & Noble',
                    'url': f'https://www.barnesandnoble.com/s/{isbn13}',
                }
            )

        return links
