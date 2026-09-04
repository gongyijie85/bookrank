"""
Google Books 新书数据源

Google Books API 提供更精确的新书筛选功能。
API文档: https://developers.google.com/books/docs/v1/getting_started

查询语法说明:
- subject: 按主题分类，如 subject:fiction
- intitle: 按书名搜索
- inauthor: 按作者搜索
- isbn: 按ISBN搜索
- 日期过滤: Google Books API 不支持 publishedDate: 作为搜索字段
  需要通过下载日期范围过滤或结果后处理来筛选
"""

import logging
import time
from datetime import date, datetime, timedelta

import requests

from ...utils.error_handler import ErrorCategory, log_error
from ..publisher_data import parse_static_date
from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig, CrawlRequest

logger = logging.getLogger(__name__)


class GoogleBooksCrawler(BaseCrawler):
    """
    Google Books 新书爬虫

    使用 Google Books API 获取新书数据，支持按年份筛选。
    无 API key 时仍可使用（配额较低），有有效 Key 时配额更高。
    """

    PUBLISHER_NAME = 'Google Books'
    PUBLISHER_NAME_EN = 'Google Books'
    PUBLISHER_WEBSITE = 'https://books.google.com'
    CRAWLER_CLASS_NAME = 'GoogleBooksCrawler'
    # Google Books 系（含各出版社变体）统一走 GOOGLE_API_KEY 注入
    API_KEY_CONFIG = 'GOOGLE_API_KEY'

    BASE_URL = 'https://www.googleapis.com/books/v1/volumes'

    # "新书"窗口：只保留最近 30 天内出版的书（维护者决议，2026-08-07：
    # 出版 30 天内才算"新书"，与展示层默认窗口一致）。Google Books 没有
    # 可靠的"首次出版日期"字段，按天计算的窄窗口能显著减少把经典作品
    # 重印/新版当新书返回的误判。
    RECENCY_WINDOW_DAYS = 30

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
        self._api_key = config.api_key if config else None
        self._key_validated = False
        self._key_is_valid = False
        # 工单 #83：日期过滤分类拒绝计数器——量化"日期缺失保守拒绝"策略的
        # 漏报代价。只测量、不改变任何收录/拒绝行为；计数随同步结果字典流出，
        # 由 auto_sync 持久化到 last_auto_sync_result 摘要。
        self.date_filter_stats: dict[str, int] = {
            'traversed_total': 0,
            'rejected_no_date': 0,
            'rejected_unparseable': 0,
            'rejected_out_of_window': 0,
            'rejected_future_placeholder': 0,
            'accepted_year_only': 0,
        }

    def _validate_api_key(self) -> bool:
        """验证 API Key 是否有效，无效则自动降级为无Key模式"""
        if self._key_validated:
            return self._key_is_valid

        if not self._api_key:
            self._key_validated = True
            self._key_is_valid = False
            return False

        try:
            params: dict[str, str | int] = {'q': 'test', 'maxResults': 1, 'key': self._api_key}
            resp = self._session.get(
                self.BASE_URL,
                params=params,
                timeout=10,
            )
            if resp.status_code == 200:
                self._key_is_valid = True
                logger.info('Google Books API Key 验证通过')
            elif resp.status_code == 400:
                logger.warning('Google Books API Key 无效，降级为无Key模式')
                self._key_is_valid = False
            else:
                logger.warning(
                    'Google Books API Key 验证异常 (状态码:%s)，降级为无Key模式',
                    resp.status_code,
                )
                self._key_is_valid = False
        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'Google Books API Key 验证失败: {e}，降级为无Key模式', level='warning')
            self._key_is_valid = False

        self._key_validated = True
        return self._key_is_valid

    def _build_query_params(
        self,
        subject: str,
        max_results: int,
        start_index: int = 0,
    ) -> dict[str, str | int]:
        """构建查询参数"""
        query_parts = []
        if subject and subject != 'general':
            query_parts.append(f'subject:{subject}')

        if not query_parts:
            query_parts.append('books')

        params: dict[str, str | int] = {
            'q': ' '.join(query_parts),
            'maxResults': min(max_results, 40),
            'startIndex': start_index,
            'printType': 'books',
            'langRestrict': 'en',
        }

        if self._key_is_valid and self._api_key:
            params['key'] = self._api_key

        return params

    def _iter_new_books(self, request: CrawlRequest):
        """
        抓取新书的生成器实现

        Args:
            request: 抓取请求（category / max_books；backfill 忽略）
        """
        category = request.category
        max_books = request.max_books
        subject = category or 'fiction'
        cutoff_date = self._compute_cutoff_date()

        logger.info(
            '正在从 Google Books 获取 %s 类新书 (>= %s)...',
            subject,
            cutoff_date.isoformat(),
        )

        self._validate_api_key()

        collected = 0
        start_index = 0
        max_pages = 5

        for _page in range(max_pages):
            if collected >= max_books:
                break

            remaining = max_books - collected
            params = self._build_query_params(subject, remaining, start_index)

            response = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    time.sleep(self.config.request_delay * (attempt + 1))
                    response = self._session.get(
                        self.BASE_URL,
                        params=params,
                        timeout=self.config.timeout,
                    )

                    if response.status_code == 400 and self._key_is_valid:
                        logger.warning('API Key 可能已失效，尝试无Key模式')
                        self._key_is_valid = False
                        params.pop('key', None)
                        response = self._session.get(
                            self.BASE_URL,
                            params=params,
                            timeout=self.config.timeout,
                        )

                    if response.status_code == 429:
                        wait = 5 * (attempt + 1)
                        logger.warning('Google Books 429 限流，等待 %s 秒后重试', wait)
                        time.sleep(wait)
                        continue

                    response.raise_for_status()
                    break
                except requests.RequestException as e:
                    logger.error(
                        'Google Books API 请求失败 (尝试 %s/%s): %s', attempt + 1, self.config.max_retries + 1, e
                    )
                    if attempt >= self.config.max_retries:
                        response = None
                    else:
                        time.sleep(self.config.retry_delay * (attempt + 1))

            if response is None or response.status_code != 200:
                logger.error('Google Books API 请求最终失败，跳过本页')
                break

            data = response.json()

            items = data.get('items', [])
            if not items:
                break

            for item in items:
                if collected >= max_books:
                    break

                volume_info = item.get('volumeInfo', {})
                published_date = volume_info.get('publishedDate', '')

                category = self._classify_date_filter(published_date, cutoff_date)
                self._record_date_filter(category)
                if not category.startswith('accepted'):
                    continue

                book_info = self._parse_volume_info(volume_info, subject)
                if book_info:
                    book_info.category = self.SUBJECT_MAP.get(subject, subject)
                    yield book_info
                    collected += 1

            total_items = data.get('totalItems', 0)
            start_index += len(items)
            if start_index >= total_items:
                break

        if collected == 0:
            logger.warning(
                'Google Books 未找到 %s 之后的 %s 类书籍',
                cutoff_date.isoformat(),
                subject,
            )
        else:
            logger.info('Google Books 共获取 %s 本 %s 类新书', collected, subject)

    @classmethod
    def _compute_cutoff_date(cls) -> date:
        """计算"新书"截止日期：按 RECENCY_WINDOW_DAYS 滚动窗口。"""
        return datetime.now().date() - timedelta(days=cls.RECENCY_WINDOW_DAYS)

    @staticmethod
    def _classify_date_filter(published_date: str, cutoff_date: date) -> str:
        """对单条日期判定做分类（工单 #83 漏报测量）。

        返回值即收录/拒绝类别，与 _is_recent_book 的布尔判定完全同构：

        - accepted: 日期有效且在窗口内
        - accepted_year_only: 年份-only（如 '2026'）按当年1月1日放行，单独计数
        - rejected_no_date: 日期字段缺失
        - rejected_unparseable: 有值但解析失败
        - rejected_future_placeholder: 未来超1年的占位日期
        - rejected_out_of_window: 早于新书窗口
        """
        if not published_date:
            return 'rejected_no_date'

        parsed = parse_static_date(published_date)
        if parsed is None:
            return 'rejected_unparseable'

        today = datetime.now().date()
        # 过滤未来超过1年的占位日期（Google Books 常返回 2030-12-31 等占位值）
        if parsed > today + timedelta(days=365):
            return 'rejected_future_placeholder'
        if parsed < cutoff_date:
            return 'rejected_out_of_window'
        if published_date.strip().isdigit() and len(published_date.strip()) == 4:
            return 'accepted_year_only'
        return 'accepted'

    @staticmethod
    def _is_recent_book(published_date: str, cutoff_date: date) -> bool:
        """判断书籍是否为近期出版（排除未来占位日期、过旧书籍和日期缺失的书籍）

        日期缺失或无法解析时保守拒绝：无法确认"新"就不能当新书展示，
        宁可漏掉少数元数据不全的书，也不能把无法验证时间的书混进新书速递。
        """
        category = GoogleBooksCrawler._classify_date_filter(published_date, cutoff_date)
        return category.startswith('accepted')

    def _record_date_filter(self, category: str) -> None:
        """累计一条日期过滤判定到实例计数器（工单 #83）"""
        self.date_filter_stats['traversed_total'] += 1
        if category in self.date_filter_stats:
            self.date_filter_stats[category] += 1

    def _parse_volume_info(self, volume_info: dict, default_category: str) -> BookInfo | None:
        """解析 Google Books 卷信息"""
        try:
            title = volume_info.get('title', '')
            if not title:
                return None

            authors = volume_info.get('authors', ['Unknown Author'])
            author = authors[0] if authors else 'Unknown Author'

            description = volume_info.get('description')
            published_date = volume_info.get('publishedDate', '')
            volume_info.get('publisher', '')

            page_count = volume_info.get('pageCount')
            language = volume_info.get('language', 'en')

            isbn_13 = None
            isbn_10 = None
            industry_identifiers = volume_info.get('industryIdentifiers', [])
            for identifier in industry_identifiers:
                if identifier.get('type') == 'ISBN_13':
                    isbn_13 = identifier.get('identifier')
                elif identifier.get('type') == 'ISBN_10':
                    isbn_10 = identifier.get('identifier')

            cover_url = None
            image_links = volume_info.get('imageLinks', {})
            if image_links:
                cover_url = (
                    image_links.get('extraLarge')
                    or image_links.get('large')
                    or image_links.get('medium')
                    or image_links.get('thumbnail')
                    or image_links.get('smallThumbnail')
                )
                if cover_url and cover_url.startswith('http://'):
                    cover_url = cover_url.replace('http://', 'https://')

            publication_date = None
            if published_date:
                try:
                    if len(published_date) >= 10:
                        publication_date = datetime.strptime(published_date[:10], '%Y-%m-%d').date()
                    elif len(published_date) >= 4:
                        publication_date = datetime.strptime(published_date[:4], '%Y').date()
                except ValueError:
                    pass

            buy_links = []
            canonical_volume_link = volume_info.get('canonicalVolumeLink')
            if canonical_volume_link:
                buy_links.append(
                    {
                        'name': 'Google Books',
                        'url': canonical_volume_link,
                    }
                )

            return BookInfo(
                title=title,
                author=author,
                isbn13=isbn_13,
                isbn10=isbn_10,
                description=description,
                cover_url=cover_url,
                category=self.SUBJECT_MAP.get(default_category, default_category),
                publication_date=publication_date,
                price=None,
                page_count=page_count,
                language=language,
                buy_links=buy_links,
                source_url=canonical_volume_link or '',
            )

        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'解析 Google Books 卷信息失败: {e}', level='warning')
            return None
