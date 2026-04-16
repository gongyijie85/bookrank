"""
Crawl4AI 爬虫基类

提供基于 Crawl4AI 的爬虫功能，用于处理传统 requests 无法连接的网站。
特点：
- 使用真实浏览器（Playwright）
- 更好的反爬虫绕过能力
- 支持 JS 渲染
- 自动降级到传统爬虫
"""
import asyncio
import logging
from abc import abstractmethod
from typing import Any, Generator, Optional

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class Crawl4AICrawler(BaseCrawler):
    """
    Crawl4AI 爬虫基类

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 重试
    """

    # 是否启用 Crawl4AI
    USE_CRAWL4AI = True

    def __init__(self, config: CrawlerConfig | None = None):
        super().__init__(config)
        self._crawl4ai_available = self._check_crawl4ai()
        self._fallback_to_requests = True

    def _check_crawl4ai(self) -> bool:
        """检查 Crawl4AI 是否可用"""
        try:
            import crawl4ai
            logger.info(f"✅ Crawl4AI 可用: v{crawl4ai.__version__}")
            return True
        except ImportError:
            logger.warning("⚠️ Crawl4AI 未安装，将使用传统 requests")
            return False

    async def _crawl_with_crawl4ai_async(self, url: str) -> Optional[dict]:
        """
        使用 Crawl4AI 异步爬取

        Args:
            url: 要爬取的 URL

        Returns:
            爬取结果字典，包含 html, markdown 等
        """
        if not self._crawl4ai_available or not self.USE_CRAWL4AI:
            return None

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

            logger.info(f"🕸️ 使用 Crawl4AI 爬取: {url}")

            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
            )

            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                timeout=30000,
                word_count_threshold=1,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(
                    url=url,
                    config=run_config,
                )

                if result and result.success:
                    logger.info(f"✅ Crawl4AI 爬取成功")
                    return {
                        'html': result.html,
                        'markdown': result.markdown,
                        'success': True,
                    }
                else:
                    logger.warning(f"⚠️ Crawl4AI 爬取失败")
                    return None

        except Exception as e:
            logger.warning(f"⚠️ Crawl4AI 出错: {e}")
            return None

    def _crawl_with_crawl4ai(self, url: str) -> Optional[dict]:
        """
        同步版本的 Crawl4AI 爬取

        Args:
            url: 要爬取的 URL

        Returns:
            爬取结果字典
        """
        try:
            return asyncio.run(self._crawl_with_crawl4ai_async(url))
        except Exception as e:
            logger.warning(f"⚠️ Crawl4AI 同步调用失败: {e}")
            return None

    def _make_request_with_fallback(
        self,
        url: str,
        method: str = 'GET',
        **kwargs
    ) -> tuple[Optional[Any], Optional[str]]:
        """
        带降级的请求方法

        先尝试传统 requests，失败后用 Crawl4AI

        Args:
            url: 请求 URL
            method: HTTP 方法
            **kwargs: 其他参数

        Returns:
            (response_or_html, source) 元组
            source: 'requests' 或 'crawl4ai'
        """
        # 先尝试传统 requests
        logger.info(f"🔄 尝试传统 requests: {url}")
        response = self._make_request(url, method, **kwargs)

        if response:
            logger.info(f"✅ 传统 requests 成功")
            return response, 'requests'

        # 失败后尝试 Crawl4AI
        if self._crawl4ai_available and self.USE_CRAWL4AI:
            logger.info(f"🔄 降级到 Crawl4AI: {url}")
            crawl4ai_result = self._crawl_with_crawl4ai(url)

            if crawl4ai_result:
                logger.info(f"✅ Crawl4AI 成功")
                return crawl4ai_result, 'crawl4ai'

        logger.warning(f"❌ 所有方法都失败: {url}")
        return None, None

    @abstractmethod
    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100
    ) -> Generator[BookInfo, None, None]:
        """
        获取新书列表（子类必须实现）

        子类应该使用 _make_request_with_fallback 来获得自动降级能力
        """
        pass

    @abstractmethod
    def get_book_details(self, book_url: str) -> BookInfo | None:
        """
        获取书籍详情（子类必须实现）

        子类应该使用 _make_request_with_fallback 来获得自动降级能力
        """
        pass


class HybridCrawlerMixin:
    """
    混合爬虫混入类

    可以让现有爬虫支持 Crawl4AI 降级
    使用方法：
        class MyCrawler(HybridCrawlerMixin, BaseCrawler):
            pass
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._crawl4ai_available = self._check_crawl4ai()

    def _check_crawl4ai(self) -> bool:
        """检查 Crawl4AI 是否可用"""
        try:
            import crawl4ai
            return True
        except ImportError:
            return False

    async def _crawl_with_crawl4ai_async(self, url: str) -> Optional[str]:
        """异步使用 Crawl4AI 爬取"""
        if not self._crawl4ai_available:
            return None

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

            browser_config = BrowserConfig(headless=True, verbose=False)
            run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, timeout=30000)

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                if result and result.success:
                    return result.html
            return None
        except Exception:
            return None

    def _crawl_with_crawl4ai(self, url: str) -> Optional[str]:
        """同步使用 Crawl4AI 爬取"""
        try:
            return asyncio.run(self._crawl_with_crawl4ai_async(url))
        except Exception:
            return None

