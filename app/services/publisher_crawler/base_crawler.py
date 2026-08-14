"""
出版社爬虫基类

提供爬虫的通用功能：
- HTTP请求处理（带重试机制）
- robots.txt 遵守
- 分页处理
- 错误处理和日志记录
"""

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ...utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


class SimpleResponse:
    """轻量级 HTTP 响应包装（用于 Crawl4AI 降级等场景）"""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data


@dataclass
class BookInfo:
    """
    书籍信息数据类

    用于存储从出版社网站爬取的原始书籍数据。
    """

    title: str
    author: str
    isbn13: str | None = None
    isbn10: str | None = None
    description: str | None = None
    cover_url: str | None = None
    category: str | None = None
    publication_date: date | None = None
    price: str | None = None
    page_count: int | None = None
    language: str | None = None
    buy_links: list[dict[str, str]] = field(default_factory=list)
    source_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            'title': self.title,
            'author': self.author,
            'isbn13': self.isbn13,
            'isbn10': self.isbn10,
            'description': self.description,
            'cover_url': self.cover_url,
            'category': self.category,
            'publication_date': self.publication_date.isoformat() if self.publication_date else None,
            'price': self.price,
            'page_count': self.page_count,
            'language': self.language,
            'buy_links': self.buy_links,
            'source_url': self.source_url,
        }


@dataclass
class CrawlerConfig:
    """
    爬虫配置数据类
    """

    # 请求配置
    timeout: int = 15
    max_retries: int = 3
    retry_delay: float = 2.0
    request_delay: float = 1.0  # 请求间隔（秒）

    # 分页配置
    max_pages: int = 10  # 最大爬取页数
    page_size: int = 20  # 每页数量

    # 内容配置
    max_description_length: int = 2000  # 简介最大长度

    # User-Agent
    user_agent: str = 'BookRank/3.0 (https://github.com/gongyijie85/bookrank)'

    # API Key（用于需要认证的API）
    api_key: str | None = None

    # 是否遵守 robots.txt
    respect_robots_txt: bool = True


@dataclass
class CrawlRequest:
    """抓取请求：调用爬虫接口时的统一请求参数（见 CONTEXT.md 术语表）。"""

    category: str | None = None
    max_books: int = 100
    backfill: bool = False


@dataclass
class CrawlOutcome:
    """抓取结果：书籍流 + 日期过滤计数（非 Google Books 系为 None）。"""

    books: Iterable[BookInfo]
    date_filter_stats: dict[str, int] | None = None


class BaseCrawler(ABC):
    """
    出版社爬虫抽象基类

    所有出版社爬虫都需要继承此类并实现抽象方法。
    """

    # 出版社信息（子类需要覆盖）
    PUBLISHER_NAME: str = ''
    PUBLISHER_NAME_EN: str = ''
    PUBLISHER_WEBSITE: str = ''
    CRAWLER_CLASS_NAME: str = ''

    # 能力与配置声明（接口事实，调用方直接读取，不得用 getattr 猜测）：
    # 是否支持回填窗口模式（引擎按存量书数决定开关）
    SUPPORTS_BACKFILL: bool = False
    # 所需 API Key 的配置键名（如 'GOOGLE_API_KEY' / 'PRH_API_KEY'）；None 表示无需注入
    API_KEY_CONFIG: str | None = None
    # 缺 API Key 时是否快速失败（PRH 官方 API 为必填）
    api_key_required: bool = False
    # 引擎注入配置时的请求间隔（秒）；None 用 CrawlerConfig 默认值
    REQUEST_DELAY: float | None = None

    def __init__(self, config: CrawlerConfig | None = None):
        """
        初始化爬虫

        Args:
            config: 爬虫配置，为 None 时使用默认配置
        """
        self.config = config or CrawlerConfig()
        self._session = self._create_session()
        self._robots_parser: RobotFileParser | None = None
        self._is_allowed_by_robots = True
        # 日期过滤计数：Google Books 系子类重置为计数字典，其余保持 None
        self.date_filter_stats: dict[str, int] | None = None

        # 初始化 robots.txt 解析器
        if self.config.respect_robots_txt and self.PUBLISHER_WEBSITE:
            self._init_robots_parser()

    def _create_session(self) -> requests.Session:
        """
        创建配置了重试机制的 requests Session

        Returns:
            配置好的 Session 对象
        """
        session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_delay,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=['HEAD', 'GET', 'OPTIONS'],
        )

        # 配置连接池
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry_strategy)

        session.mount('http://', adapter)
        session.mount('https://', adapter)

        # 设置默认请求头
        session.headers.update(
            {
                'User-Agent': self.config.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
        )

        return session

    def _init_robots_parser(self) -> None:
        """初始化 robots.txt 解析器

        注意：RobotFileParser.read() 内部用 urllib.urlopen 且无超时，
        一旦目标站点接受连接却不返回数据会无限挂起（曾导致后台全量同步
        卡死数十分钟）。这里改用带超时的 session 请求取回内容后 parse()，
        获取失败则放弃 robots 约束，不阻塞后续抓取。
        """
        try:
            robots_url = urljoin(self.PUBLISHER_WEBSITE, '/robots.txt')
            parser = RobotFileParser()
            parser.set_url(robots_url)
            response = self._session.get(robots_url, timeout=self.config.timeout)
            if response.ok:
                parser.parse(response.text.splitlines())
                self._robots_parser = parser
                logger.info(f'✅ 已加载 robots.txt: {robots_url}')
            else:
                logger.warning(f'ℹ️ robots.txt 状态码 {response.status_code}，跳过 robots 约束: {robots_url}')
                self._robots_parser = None
        except Exception as e:
            log_error(ErrorCategory.CRAWLER, f'无法加载 robots.txt: {e}', level='warning')
            self._robots_parser = None

    def _is_url_allowed(self, url: str) -> bool:
        """
        检查 URL 是否被 robots.txt 允许

        Args:
            url: 要检查的 URL

        Returns:
            是否允许访问
        """
        # 如果配置为忽略robots.txt，直接允许访问
        if not self.config.respect_robots_txt:
            return True

        if not self._robots_parser:
            return True

        try:
            return self._robots_parser.can_fetch(self.config.user_agent, url)
        except Exception:
            return True

    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> requests.Response | None:
        """
        发送 HTTP 请求（带重试和延迟）

        Args:
            url: 请求 URL
            method: 请求方法
            **kwargs: 传递给 requests 的其他参数

        Returns:
            Response 对象或 None
        """
        # 检查 robots.txt
        if not self._is_url_allowed(url):
            logger.warning(f'⚠️ robots.txt 禁止访问: {url}')
            return None

        # 设置超时
        kwargs.setdefault('timeout', self.config.timeout)

        # 添加更多的请求头
        headers = kwargs.get('headers', {})
        headers.update(
            {
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Pragma': 'no-cache',
            }
        )
        kwargs['headers'] = headers

        # 多次重试
        for attempt in range(self.config.max_retries + 1):
            try:
                # 请求前延迟
                delay = self.config.request_delay * (attempt + 1)
                logger.debug(f'⏳ 等待 {delay:.1f} 秒后请求: {url}')
                time.sleep(delay)

                response = self._session.request(method, url, **kwargs)

                # 处理常见的反爬响应
                if response.status_code == 403:
                    logger.warning(f'⚠️ 403 禁止访问: {url}')
                    # 尝试使用不同的 User-Agent
                    headers['User-Agent'] = (
                        f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{90 + attempt}.0.4430.212 Safari/537.36'
                    )
                    kwargs['headers'] = headers
                    logger.debug(f'🔄 尝试使用新的 User-Agent: {headers["User-Agent"]}')
                    continue

                # 处理 429 速率限制
                if response.status_code == 429:
                    logger.warning(f'⚠️ 429 速率限制: {url}')
                    # 增加延迟
                    time.sleep(5 * (attempt + 1))
                    continue

                # 处理 500 系列错误
                if 500 <= response.status_code < 600:
                    logger.warning(f'⚠️ 服务器错误 {response.status_code}: {url}')
                    # 增加延迟后重试
                    time.sleep(3 * (attempt + 1))
                    continue

                response.raise_for_status()

                logger.info(f'✅ 请求成功: {url} (状态码: {response.status_code}, 尝试: {attempt + 1})')
                logger.debug(f'📦 响应大小: {len(response.content)} 字节')
                return response

            except requests.Timeout:
                logger.error(f'❌ 请求超时: {url} (尝试: {attempt + 1})')
                if attempt >= self.config.max_retries:
                    logger.error(f'❌ 请求最终失败: {url} - 超时')
                    return None
            except requests.HTTPError as e:
                logger.error(f'❌ HTTP错误: {url} - {e} (尝试: {attempt + 1})')
                if attempt >= self.config.max_retries:
                    logger.error(f'❌ 请求最终失败: {url} - HTTP错误')
                    return None
            except requests.RequestException as e:
                logger.error(f'❌ 请求失败: {url} - {e} (尝试: {attempt + 1})')
                if attempt >= self.config.max_retries:
                    logger.error(f'❌ 请求最终失败: {url} - 请求异常')
                    return None
            except Exception as e:
                log_error(ErrorCategory.CRAWLER, f'未知错误: {url} - {e} (尝试: {attempt + 1})')
                if attempt >= self.config.max_retries:
                    logger.error(f'❌ 请求最终失败: {url} - 未知错误')
                    return None

        logger.error(f'❌ 所有尝试失败: {url}')
        return None

    def _parse_html(self, html: str, parser: str = 'html.parser') -> BeautifulSoup:
        """
        解析 HTML 内容

        Args:
            html: HTML 字符串
            parser: BeautifulSoup 解析器

        Returns:
            BeautifulSoup 对象
        """
        return BeautifulSoup(html, parser)

    def _clean_text(self, text: str | None) -> str:
        """
        清理文本（去除多余空白和换行）

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        if not text:
            return ''

        # 去除多余空白和换行
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_isbn(self, text: str) -> tuple[str | None, str | None]:
        """
        从文本中提取 ISBN-13 和 ISBN-10

        Args:
            text: 包含 ISBN 的文本

        Returns:
            (isbn13, isbn10) 元组
        """
        isbn13 = None
        isbn10 = None

        # 提取 ISBN-13（13位数字，可能以978或979开头）
        isbn13_match = re.search(r'(?:ISBN[-:\s]*)?(97[89]\d{10})', text, re.IGNORECASE)
        if isbn13_match:
            isbn13 = isbn13_match.group(1)

        # 提取 ISBN-10（10位，最后一位可能是X）
        isbn10_match = re.search(r'(?:ISBN[-:\s]*)?(\d{9}[\dXx])(?!\d)', text, re.IGNORECASE)
        if isbn10_match and not isbn13:
            isbn10 = isbn10_match.group(1).upper()

        return isbn13, isbn10

    def _parse_date(self, date_str: str | None) -> date | None:
        """
        解析日期字符串

        支持多种常见格式：
        - YYYY-MM-DD
        - YYYY/MM/DD
        - Month DD, YYYY
        - DD Month YYYY

        Args:
            date_str: 日期字符串

        Returns:
            date 对象或 None
        """
        if not date_str:
            return None

        date_str = self._clean_text(date_str)

        # 常见日期格式
        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%B %d, %Y',  # January 15, 2024
            '%b %d, %Y',  # Jan 15, 2024
            '%d %B %Y',  # 15 January 2024
            '%d %b %Y',  # 15 Jan 2024
            '%Y',  # 仅年份
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.date()
            except ValueError:
                continue

        logger.warning(f'⚠️ 无法解析日期: {date_str}')
        return None

    def _parse_price(self, price_str: str | None) -> str | None:
        """
        解析价格字符串

        Args:
            price_str: 价格字符串

        Returns:
            格式化后的价格
        """
        if not price_str:
            return None

        price_str = self._clean_text(price_str)

        # 提取数字和货币符号
        match = re.search(r'([\$€£¥]?\s*[\d,]+\.?\d*)', price_str)
        if match:
            return match.group(1).strip()

        return price_str

    def _truncate_description(self, description: str | None) -> str | None:
        """
        截断简介到最大长度

        Args:
            description: 原始简介

        Returns:
            截断后的简介
        """
        if not description:
            return None

        if len(description) <= self.config.max_description_length:
            return description

        return description[: self.config.max_description_length - 3] + '...'

    def get_new_books(self, request: 'CrawlRequest') -> 'CrawlOutcome':
        """
        按抓取请求获取新书（模板方法）。

        组装抓取结果：书籍流由抽象钩子 _iter_new_books 产出；
        日期过滤计数取实例属性 date_filter_stats（非 Google Books 系为 None）。

        Args:
            request: 抓取请求（category / max_books / backfill）

        Returns:
            抓取结果（书籍流 + 日期过滤计数）
        """
        return CrawlOutcome(
            books=self._iter_new_books(request),
            date_filter_stats=self.date_filter_stats,
        )

    @abstractmethod
    def _iter_new_books(self, request: 'CrawlRequest') -> 'Iterable[BookInfo]':
        """按抓取请求产出新书流的生成器实现（模板方法钩子，子类必须实现）。

        非回填型适配器读取并忽略 backfill 字段。
        """
        pass

    def close(self) -> None:
        """关闭爬虫，释放资源"""
        if self._session:
            self._session.close()
            logger.info(f'🔒 已关闭 {self.PUBLISHER_NAME} 爬虫')

    def __enter__(self) -> 'BaseCrawler':
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.close()
