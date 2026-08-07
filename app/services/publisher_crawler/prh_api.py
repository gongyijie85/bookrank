"""
Penguin Random House 官方开发者 API 爬虫

使用 PRH Enhanced API v2 的 title list 端点获取新书数据，替代此前
基于 Google Books `inpublisher:` 的兜底搜索（生产实测仅产出 2 本，近乎失效）。

实证修正备忘（来自 key 激活后的真实请求，见工单 #77/#84 决议）：
- `onSaleFrom` 单独使用不生效（返回全量含未来书），必须与 `onSaleTo` 成对使用
- `rows=1000` 返回 status=warning 但数据完整，可用
- PRH.US 域结果混入加拿大分部（CAD 定价），需按 division code 黑名单过滤
- 同一作品多 ISBN 版本会重复出现（实测重复率 36.5%），需按 workId 去重
"""

import logging
from collections.abc import Generator
from datetime import date, timedelta

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)


class PrhApiCrawler(BaseCrawler):
    """
    Penguin Random House 官方 API 爬虫（14 天增量窗口路径）

    输出与其他爬虫相同的 BookInfo 契约；窗口模式由调用方决定，
    本类当前只实现日常增量：成对 onSaleFrom/onSaleTo 拉近 14 天窗口。
    """

    PUBLISHER_NAME = '企鹅兰登'
    PUBLISHER_NAME_EN = 'Penguin Random House'
    PUBLISHER_WEBSITE = 'https://www.penguinrandomhouse.com'
    CRAWLER_CLASS_NAME = 'PrhApiCrawler'

    API_URL = 'https://api.penguinrandomhouse.com/resources/v2/title/domains/PRH.US/titles'
    COVER_URL_TEMPLATE = 'https://images.penguinrandomhouse.com/cover/{isbn}'

    # 日常增量窗口（天）。PRH 固定周二发书，14 天容忍单次同步失败
    INCREMENTAL_WINDOW_DAYS = 14

    # 首次回填窗口（天）。维护者决议（2026-08-07）：出版 30 天内才算"新书"，
    # 回填不再用 showNewReleases（固定近 180 天，会拉进大量超龄书），
    # 改用成对 onSaleFrom/onSaleTo 拉精确 30 天窗口
    BACKFILL_WINDOW_DAYS = 30

    # rows=1000 实测可用（status=warning 但数据完整）
    PAGE_ROWS = 1000

    # 回填模式的翻页上限：30 天窗口约 2000+ 条（约 3 页），保留余量到 20
    BACKFILL_MAX_PAGES = 20

    # division code 黑名单：加拿大系（CAD 定价/加拿大发行）与 Audio
    EXCLUDED_DIVISION_CODES = frozenset({'91', '29', '9B', '9E', '97', '22'})

    # workId 去重时的格式优先级：精装 > 平装 > 其余
    FORMAT_PRIORITY = {'HC': 2, 'TR': 1}

    # 能力声明：支持同步引擎按存量书数量传入窗口模式（工单 #87）
    SUPPORTS_BACKFILL = True

    # BISAC subject 描述 -> 现有分类体系的英文规范名（按顺序取首个命中）。
    # 规则顺序有讲究：更具体的类目（Young Adult/Juvenile/Science Fiction）
    # 必须先于宽泛的 FICTION 命中；TRUE CRIME 属非虚构而非 Mystery。
    _BISAC_CATEGORY_RULES = (
        ('YOUNG ADULT', 'Young Adult'),
        ('JUVENILE', 'Children'),
        ('CHILDREN', 'Children'),
        ('TRUE CRIME', 'Nonfiction'),
        ('MYSTERY', 'Mystery'),
        ('DETECTIVE', 'Mystery'),
        ('ROMANCE', 'Romance'),
        ('THRILLER', 'Thriller'),
        ('SUSPENSE', 'Thriller'),
        ('SCIENCE FICTION', 'Science Fiction'),
        ('FANTASY', 'Fantasy'),
        ('BIOGRAPHY', 'Biography'),
        ('AUTOBIOGRAPHY', 'Biography'),
        ('HISTORY', 'History'),
        ('BUSINESS', 'Business'),
        ('SELF-HELP', 'Self-Help'),
        ('SELF HELP', 'Self-Help'),
        ('FICTION', 'Fiction'),
        ('NONFICTION', 'Nonfiction'),
    )

    def __init__(self, config: CrawlerConfig | None = None):
        if config is None:
            config = CrawlerConfig(request_delay=0.5)
        # 官方 API 无 robots.txt 约束；避免去爬官网 robots.txt 引入挂起风险
        config.respect_robots_txt = False
        # 翻页上限抬高到回填上限，避免默认 max_pages=10 截断回填窗口
        config.max_pages = max(config.max_pages, self.BACKFILL_MAX_PAGES)
        super().__init__(config)
        if not self.config.api_key:
            raise ValueError('PrhApiCrawler 需要 PRH_API_KEY（环境变量注入）')

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
        backfill: bool = False,
    ) -> Generator[BookInfo]:
        """
        获取 PRH 新书

        Args:
            category: 未使用（API 窗口模式不支持分类检索，分类在入库时映射）
            max_books: 最大产出数量（去重后计数）
            backfill: True 走首次回填窗口（成对日期拉近 BACKFILL_WINDOW_DAYS 天），
                False 走近 14 天增量窗口；模式由同步引擎判定传入，爬虫无状态
        """
        if backfill:
            window_end = date.today()
            window_start = window_end - timedelta(days=self.BACKFILL_WINDOW_DAYS)
            raw_titles = self._fetch_window(window_start, window_end)
        else:
            window_end = date.today()
            window_start = window_end - timedelta(days=self.INCREMENTAL_WINDOW_DAYS)
            raw_titles = self._fetch_window(window_start, window_end)

        deduped = self._dedup_by_work_id(t for t in raw_titles if self._division_allowed(t))

        yielded = 0
        for title in deduped:
            book = self._to_book_info(title)
            if book is None:
                continue
            yield book
            yielded += 1
            if yielded >= max_books:
                break

    def get_book_details(self, book_url: str) -> BookInfo | None:
        """不支持详情页抓取（列表端点已包含所需字段）"""
        return None

    def get_categories(self) -> list[dict[str, str]]:
        """API 窗口模式不支持分类检索"""
        return []

    # ---------- 请求与分页 ----------

    def _fetch_window(self, window_start: date, window_end: date) -> list[dict]:
        """成对 onSaleFrom/onSaleTo 拉取窗口内全部 title（分页）"""
        base_params = {
            # 实证：必须成对使用，单独传 onSaleFrom 不生效
            'onSaleFrom': window_start.strftime('%m/%d/%Y'),
            'onSaleTo': window_end.strftime('%m/%d/%Y'),
            'sort': 'onsale',
            'dir': 'desc',
            'rows': self.PAGE_ROWS,
            'api_key': self.config.api_key,
        }
        return self._fetch_pages(base_params, f'窗口 {window_start} ~ {window_end}')

    def _fetch_pages(self, base_params: dict, label: str) -> list[dict]:
        """按 start 偏移翻页拉取全部 title，首页失败抛异常、中途失败返回已取部分"""
        all_titles: list[dict] = []
        offset = 0
        max_pages = max(1, self.config.max_pages)

        for page in range(max_pages):
            params = dict(base_params)
            params['start'] = offset
            response = self._make_request(self.API_URL, method='GET', params=params)
            if response is None:
                if page == 0:
                    raise RuntimeError(f'PRH API 首页请求失败（{label}）')
                # 中途失败：宁可漏报不误报，返回已取部分
                logger.warning('⚠️ PRH API 第 %d 页请求失败，返回已获取的 %d 条', page + 1, len(all_titles))
                break

            try:
                payload = response.json()
            except ValueError:
                logger.warning('⚠️ PRH API 响应不是合法 JSON，停止翻页')
                break

            # status=error 是业务错误（如 key 无效/限流）：首屏直接抛异常
            # 交给单家熔断，避免静默产出 0 本；中途则返回已取部分
            if payload.get('status') == 'error':
                if page == 0:
                    raise RuntimeError(f'PRH API 返回业务错误: {payload.get("error")}')
                logger.warning('⚠️ PRH API 第 %d 页返回业务错误，返回已获取的 %d 条', page + 1, len(all_titles))
                break

            # status=warning 不算失败（rows=1000 时实测返回 warning 但数据完整）
            titles = ((payload.get('data') or {}).get('titles')) or []
            all_titles.extend(titles)
            offset += len(titles)

            record_count = payload.get('recordCount') or 0
            if not titles or offset >= record_count:
                break

        logger.info('📦 PRH API %s 共获取 %d 条原始记录', label, len(all_titles))
        return all_titles

    # ---------- 过滤与去重 ----------

    def _division_allowed(self, title: dict) -> bool:
        division_code = (title.get('division') or {}).get('code')
        return division_code not in self.EXCLUDED_DIVISION_CODES

    def _dedup_by_work_id(self, titles) -> list[dict]:
        """同一 workId 的多 ISBN 版本只保留一条：HC > TR > 其余，同档取 onsale 最新；
        无 workId 的记录不参与去重，原样保留（不静默丢书）"""
        best_by_work: dict[int, tuple[int, date, dict]] = {}
        without_work_id: list[dict] = []

        for title in titles:
            work_id = title.get('workId')
            if not work_id:
                without_work_id.append(title)
                continue
            rank = self.FORMAT_PRIORITY.get(str((title.get('format') or {}).get('code') or '').upper(), 0)
            onsale = self._parse_onsale(title.get('onsale')) or date.min

            current = best_by_work.get(work_id)
            if current is None:
                best_by_work[work_id] = (rank, onsale, title)
                continue

            current_rank, current_onsale, _ = current
            if rank > current_rank or (rank == current_rank and onsale > current_onsale):
                best_by_work[work_id] = (rank, onsale, title)

        return without_work_id + [entry[2] for entry in best_by_work.values()]

    # ---------- 字段映射 ----------

    def _to_book_info(self, title: dict) -> BookInfo | None:
        book_title = self._clean_text(title.get('title'))
        author = self._clean_text(title.get('author'))
        isbn = title.get('isbn')
        if not book_title or not author or not isbn:
            return None

        publication_date = self._parse_onsale(title.get('onsale'))
        if publication_date is None:
            # 出版日期是"新书"判定的核心字段，缺失即拒绝（宁可漏报不误报）
            logger.warning('⚠️ PRH title onsale 缺失/无法解析，跳过: %s', book_title)
            return None

        isbn13 = str(isbn)
        seo_url = title.get('seoFriendlyUrl')
        language_code = title.get('language')

        return BookInfo(
            title=book_title,
            author=author,
            isbn13=isbn13,
            description=self._clean_text(title.get('excerpt')) or None,
            cover_url=self.COVER_URL_TEMPLATE.format(isbn=isbn13),
            category=self._map_bisac_category(title.get('subjects')),
            publication_date=publication_date,
            price=self._extract_usd_price(title.get('price')),
            page_count=title.get('pages'),
            language='en' if language_code == 'E' else None,
            source_url=f'{self.PUBLISHER_WEBSITE}{seo_url}' if seo_url else None,
        )

    @staticmethod
    def _parse_onsale(value) -> date | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None

    @staticmethod
    def _extract_usd_price(prices) -> str | None:
        if not prices:
            return None
        chosen = next((p for p in prices if p.get('currencyCode') == 'USD'), prices[0])
        amount = chosen.get('amount')
        if amount is None:
            return None
        return str(amount)

    def _map_bisac_category(self, subjects) -> str | None:
        """BISAC subjects 取首个可映射项到现有分类体系"""
        for subject in subjects or []:
            description = subject.get('description')
            if not description:
                continue
            normalized = str(description).upper()
            for keyword, category in self._BISAC_CATEGORY_RULES:
                if keyword in normalized:
                    return category
        return None
