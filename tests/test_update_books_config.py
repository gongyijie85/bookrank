"""update_books.py 的爬虫配置注入：CI 路径必须真的把 secrets 用起来。

历史 bug：#346 之后每周跑绿但 Google 系恒为 0，日志里 53 条
`429 Client Error .../volumes?q=inpublisher:`，且请求 URL 里没有 `key=`。
原因是本脚本一直 `crawler_cls()` 直接实例化，workflow 注入的 GOOGLE_API_KEY
没有任何代码去读（Flask 内的 sync_engine 才走 API_KEY_CONFIG 注入）。
"""

import importlib
import sys

import pytest


@pytest.fixture()
def update_books(tmp_path, monkeypatch):
    """在干净目录里导入，避免模块级 logging.FileHandler 落到仓库根。"""
    monkeypatch.chdir(tmp_path)
    sys.modules.pop('update_books', None)
    module = importlib.import_module('update_books')
    yield module
    sys.modules.pop('update_books', None)


class TestBuildCrawlerConfig:
    def test_injects_api_key_declared_by_crawler_class(self, update_books, monkeypatch):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler

        monkeypatch.setenv('GOOGLE_API_KEY', 'gb-secret')

        config = update_books._build_crawler_config(GoogleBooksCrawler)

        assert config is not None
        assert config.api_key == 'gb-secret'

    def test_returns_none_when_nothing_to_inject(self, update_books, monkeypatch):
        """没有 key、也没有声明 REQUEST_DELAY 的爬虫保持原来的默认节奏。"""
        from app.services.publisher_crawler.macmillan import MacmillanCrawler

        monkeypatch.delenv('GOOGLE_API_KEY', raising=False)

        assert update_books._build_crawler_config(MacmillanCrawler) is None

    def test_applies_declared_request_delay(self, update_books, monkeypatch):
        from app.services.publisher_crawler.prh_api import PrhApiCrawler

        monkeypatch.setenv('PRH_API_KEY', 'prh-secret')

        config = update_books._build_crawler_config(PrhApiCrawler)

        assert config is not None
        assert config.api_key == 'prh-secret'
        assert config.request_delay == PrhApiCrawler.REQUEST_DELAY


class TestMissingRequiredEnv:
    def test_reports_missing_prh_env(self, update_books, monkeypatch):
        from app.services.publisher_crawler.prh_api import PrhApiCrawler

        monkeypatch.delenv('PRH_API_KEY', raising=False)

        assert update_books._missing_required_env(PrhApiCrawler) == 'PRH_API_KEY'

    def test_returns_none_when_env_present(self, update_books, monkeypatch):
        from app.services.publisher_crawler.prh_api import PrhApiCrawler

        monkeypatch.setenv('PRH_API_KEY', 'prh-secret')

        assert update_books._missing_required_env(PrhApiCrawler) is None

    def test_optional_key_crawler_is_not_gated(self, update_books, monkeypatch):
        """Google Books 的 key 是可选的（无 key 也能跑），不能因此跳过整源。"""
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler

        monkeypatch.delenv('GOOGLE_API_KEY', raising=False)

        assert update_books._missing_required_env(GoogleBooksCrawler) is None


class TestSyncInjectsKey:
    def test_sync_passes_api_key_into_crawler_config(self, update_books, monkeypatch):
        """端到端：sync_all_publishers 实例化的爬虫必须拿到 workflow 注入的 key。"""
        from app.services.publisher_crawler.base_crawler import CrawlOutcome

        seen = {}

        class FakeCrawler:
            API_KEY_CONFIG = 'GOOGLE_API_KEY'
            api_key_required = False
            REQUEST_DELAY = None

            def __init__(self, config=None):
                seen['api_key'] = config.api_key if config else None

            def get_new_books(self, request):
                return CrawlOutcome(books=[])

        monkeypatch.setattr(update_books, '_PUBLISHER_EXPORTS', [('Simon & Schuster', 'simon_schuster')])
        monkeypatch.setenv('GOOGLE_API_KEY', 'gb-secret')
        monkeypatch.setattr(
            'app.services.publisher_crawler.get_crawler_class',
            lambda name: FakeCrawler,
        )

        update_books.sync_all_publishers()

        assert seen.get('api_key') == 'gb-secret'
