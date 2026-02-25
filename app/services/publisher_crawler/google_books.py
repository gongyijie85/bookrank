"""
Google Books 新书数据源

Google Books API 提供更精确的新书筛选功能。
API文档: https://developers.google.com/books/docs/v1//getting_started
"""
import logging
from datetime import datetime
from typing import Any

import requests
from werkzeug.exceptions import abort

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class GoogleBooksCrawler(BaseCrawler):
    """
    Google Books 新书爬虫

    使用 Google Books API 获取新书数据，支持按年份筛选。
    注意：无 API key 时 orderBy=newest 不可用，但可以通过publishedDate过滤
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
        year_from: int | None = None
    ):
        """
        获取新书列表

        Args:
            category: 分类主题
            max_books: 最大数量
            year_from: 出版年份起（用于筛选新书，默认近2年）
        """
        subject = category or 'fiction'
        current_year = datetime.now().year
        min_year = year_from or (current_year - 2)

        logger.info(f"📚 正在从 Google Books 获取 {subject} 类新书 ({min_year}-{current_year})...")

        # 使用日期范围查询来筛选新书
        date_range = f"{min_year}:{current_year}"
        params = {
            'q': f'subject:{subject}+publishedDate:{date_range}',
            'maxResults': min(max_books * 3, 40),
            'printType': 'books',
            'langRestrict': 'en',
        }

        if self._api_key:
            params['key'] = self._api_key

        try:
            response = self._session.get(
                self.BASE_URL,
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            data = response.json()

            items = data.get('items', [])
            count = 0

            for item in items:
                if count >= max_books:
                    break

                volume_info = item.get('volumeInfo', {})

                book_info = self._parse_volume_info(volume_info, subject)
                if book_info:
                    book_info.category = self.SUBJECT_MAP.get(subject, subject)
                    yield book_info
                    count += 1

            if count == 0:
                logger.warning(f"⚠️ Google Books 未找到 {min_year} 年后的 {subject} 类书籍")

        except requests.RequestException as e:
            logger.error(f"❌ Google Books API 请求失败: {e}")
        except Exception as e:
            logger.error(f"❌ 解析 Google Books 数据失败: {e}")

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
                cover_url = image_links.get('thumbnail') or image_links.get('smallThumbnail')
                if cover_url and cover_url.startswith('http'):
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
            logger.warning(f"⚠️ 解析 Google Books 卷信息失败: {e}")
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
            if self._api_key:
                params['key'] = self._api_key

            response = self._session.get(url, params=params, timeout=self.config.timeout)
            response.raise_for_status()
            data = response.json()

            volume_info = data.get('volumeInfo', {})
            return self._parse_volume_info(volume_info, 'general')

        except Exception as e:
            logger.error(f"❌ 获取 Google Books 详情失败: {e}")
            return None
