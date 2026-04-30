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
from datetime import datetime
from typing import Any

import requests

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class GoogleBooksCrawler(BaseCrawler):
    """
    Google Books 新书爬虫

    使用 Google Books API 获取新书数据，支持按年份筛选。
    无 API key 时仍可使用（配额较低），有有效 Key 时配额更高。
    """

    PUBLISHER_NAME = "Google Books"
    PUBLISHER_NAME_EN = "Google Books"
    PUBLISHER_WEBSITE = "https://books.google.com"
    CRAWLER_CLASS_NAME = "GoogleBooksCrawler"

    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

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

    def _validate_api_key(self) -> bool:
        """验证 API Key 是否有效，无效则自动降级为无Key模式"""
        if self._key_validated:
            return self._key_is_valid

        if not self._api_key:
            self._key_validated = True
            self._key_is_valid = False
            return False

        try:
            resp = self._session.get(
                self.BASE_URL,
                params={"q": "test", "maxResults": 1, "key": self._api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                self._key_is_valid = True
                logger.info("Google Books API Key 验证通过")
            elif resp.status_code == 400:
                logger.warning("Google Books API Key 无效，降级为无Key模式")
                self._key_is_valid = False
            else:
                logger.warning(
                    "Google Books API Key 验证异常 (状态码:%s)，降级为无Key模式",
                    resp.status_code,
                )
                self._key_is_valid = False
        except Exception as e:
            logger.warning("Google Books API Key 验证失败: %s，降级为无Key模式", e)
            self._key_is_valid = False

        self._key_validated = True
        return self._key_is_valid

    def _build_query_params(
        self,
        subject: str,
        max_results: int,
        start_index: int = 0,
    ) -> dict[str, Any]:
        """构建查询参数"""
        query_parts = []
        if subject and subject != "general":
            query_parts.append(f"subject:{subject}")

        if not query_parts:
            query_parts.append("books")

        params = {
            "q": " ".join(query_parts),
            "maxResults": min(max_results, 40),
            "startIndex": start_index,
            "printType": "books",
            "langRestrict": "en",
        }

        if self._key_is_valid and self._api_key:
            params["key"] = self._api_key

        return params

    def get_categories(self) -> list[dict[str, str]]:
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'nonfiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'thriller', 'name': '惊悚'},
            {'id': 'science_fiction', 'name': '科幻'},
            {'id': 'fantasy', 'name': '奇幻'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young_adult', 'name': '青少年'},
        ]

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
        year_from: int | None = None,
    ):
        """
        获取新书列表

        Args:
            category: 分类主题
            max_books: 最大数量
            year_from: 出版年份起（用于筛选新书，默认近2年）
        """
        subject = category or "fiction"
        current_year = datetime.now().year
        min_year = year_from or (current_year - 2)

        logger.info(
            "正在从 Google Books 获取 %s 类新书 (%s-%s)...",
            subject, min_year, current_year,
        )

        self._validate_api_key()

        collected = 0
        start_index = 0
        max_pages = 5

        for page in range(max_pages):
            if collected >= max_books:
                break

            remaining = max_books - collected
            params = self._build_query_params(subject, remaining, start_index)

            try:
                response = self._session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=self.config.timeout,
                )

                if response.status_code == 400 and self._key_is_valid:
                    logger.warning("API Key 可能已失效，尝试无Key模式")
                    self._key_is_valid = False
                    params.pop("key", None)
                    response = self._session.get(
                        self.BASE_URL,
                        params=params,
                        timeout=self.config.timeout,
                    )

                response.raise_for_status()
                data = response.json()

            except requests.RequestException as e:
                logger.error("Google Books API 请求失败: %s", e)
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                if collected >= max_books:
                    break

                volume_info = item.get("volumeInfo", {})
                published_date = volume_info.get("publishedDate", "")

                if not self._is_recent_book(published_date, min_year):
                    continue

                book_info = self._parse_volume_info(volume_info, subject)
                if book_info:
                    book_info.category = self.SUBJECT_MAP.get(subject, subject)
                    yield book_info
                    collected += 1

            total_items = data.get("totalItems", 0)
            start_index += len(items)
            if start_index >= total_items:
                break

        if collected == 0:
            logger.warning(
                "Google Books 未找到 %s 年后的 %s 类书籍",
                min_year, subject,
            )
        else:
            logger.info("Google Books 共获取 %s 本 %s 类新书", collected, subject)

    @staticmethod
    def _is_recent_book(published_date: str, min_year: int) -> bool:
        """判断书籍是否为近期出版（排除未来占位日期和过旧书籍）"""
        if not published_date:
            return True

        try:
            year = int(published_date[:4])
            current_year = datetime.now().year
            # 过滤未来超过1年的占位日期（Google Books 常返回 2030-12-31 等占位值）
            if year > current_year + 1:
                return False
            return year >= min_year
        except (ValueError, IndexError):
            return True

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
            publisher = volume_info.get('publisher', '')

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
                buy_links.append({
                    'name': 'Google Books',
                    'url': canonical_volume_link,
                })

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
            logger.warning("解析 Google Books 卷信息失败: %s", e)
            return None

    def get_book_details(self, book_url: str) -> BookInfo | None:
        """获取书籍详情"""
        if not book_url:
            return None

        try:
            if 'volumes/' in book_url:
                volume_id = book_url.split('volumes/')[-1]
                url = f"{self.BASE_URL}/{volume_id}"
            else:
                url = book_url

            params = {}
            if self._key_is_valid and self._api_key:
                params['key'] = self._api_key

            response = self._session.get(url, params=params, timeout=self.config.timeout)

            if response.status_code == 400 and self._key_is_valid:
                self._key_is_valid = False
                params.pop('key', None)
                response = self._session.get(url, params=params, timeout=self.config.timeout)

            response.raise_for_status()
            data = response.json()

            volume_info = data.get('volumeInfo', {})
            return self._parse_volume_info(volume_info, 'general')

        except Exception as e:
            logger.error("获取 Google Books 详情失败: %s", e)
            return None
