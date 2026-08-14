# 加深爬虫 seam — 设计文档

**日期**: 2026-08-14
**范围**: 爬虫接口深化（CrawlRequest/CrawlOutcome + 能力与配置声明 + 摘除死接口义务）
**策略**: 3 个线性 ticket（T1 基类接口 → T2 SyncEngine 消费 → T3 适配器与测试迁移），每张独立可验证
**上游决策**: 架构评审候选 #2（grilling 决策树已与维护者确认）

---

## 问题

1. **接口过度声明**：BaseCrawler 抽象声明 3 个方法，生产链路只调用
   get_new_books；get_book_details/get_categories 零生产调用方，
   crawl() 辅助方法零调用方。
2. **能力靠 duck-typing 泄漏**：SyncEngine 用
   getattr(crawler, 'SUPPORTS_BACKFILL') 与
   getattr(crawler, 'date_filter_stats') 猜测适配器能力，并对
   date_filter_stats 做 isinstance(dict) 防御（注释自述：防 Mock
   自动属性污染）。
3. **参数形状分裂**：get_new_books 签名在 15 个适配器间分裂
   （backfill 仅 PRH 理解、year_from 生产无人传入），引擎用
   **fetch_kwargs 一把梭。
4. **API Key 注入靠字符串集合**：引擎维护 _GOOGLE_BOOKS_CRAWLERS
   类名集合 + crawler_class 字符串判断来注入 GOOGLE_API_KEY /
   PRH_API_KEY。

## 设计

### 新接口形状（base_crawler.py）

    @dataclass
    class CrawlRequest:
        category: str | None = None
        max_books: int = 100
        backfill: bool = False

    @dataclass
    class CrawlOutcome:
        books: Iterable[BookInfo]
        date_filter_stats: dict[str, int] | None = None

- 基类抽象方法收敛为 **一个**：
  get_new_books(self, request: CrawlRequest) -> CrawlOutcome。
- 基类声明能力与配置（均为默认值，子类按需覆盖）：

    class BaseCrawler(ABC):
        SUPPORTS_BACKFILL: bool = False
        API_KEY_CONFIG: str | None = None
REQUEST_DELAY: float | None = None  # 引擎注入配置时的请求间隔，None 用默认值
        api_key_required: bool = False

        def __init__(self, config=None):
            ...
            # date_filter_stats 由 Google Books 系子类重置为计数字典；
            # 其余适配器保持 None（接口事实，不再靠 getattr 猜测）

- **摘除**：get_book_details / get_categories 抽象声明、crawl()
  方法。具体类上已有的实现保留（legacy 站点爬虫整体删除属候选 #7，不在本 spec）。

### SyncEngine 消费（sync_engine.py）

- get_crawler：
  - 删除 _GOOGLE_BOOKS_CRAWLERS 集合与 crawler_class 字符串分支。
  - 统一按 crawler_cls.API_KEY_CONFIG 注入；REQUEST_DELAY 非 None 时一并注入
  （PRH 0.5s 礼貌间隔由此保留）
    CrawlerConfig(api_key=current_app.config.get(...))；
    api_key_required=True 且无 key → 快速失败返回 None（PRH 语义保留）。
- sync_publisher_books：
  - supports_backfill = crawler.SUPPORTS_BACKFILL（直接属性访问）。
  - 构造 CrawlRequest(category=..., max_books=..., backfill=backfill)。
  - outcome = crawler.get_new_books(request)，迭代 outcome.books。
  - 循环后：

        if outcome.date_filter_stats:
            result.update(outcome.date_filter_stats)

    删除 getattr + isinstance hack。
  - 回填开关判定（按存量书数）与空结果语义不变。

### 适配器迁移（T3）

- 15 个适配器签名统一为 get_new_books(self, request: CrawlRequest) -> CrawlOutcome。
- Google Books 系（GoogleBooksCrawler + GoogleBooksPublisherCrawler 系 4 个 +
  MacmillanCrawler）返回 CrawlOutcome(books=..., date_filter_stats=self.date_filter_stats)；
  其余返回 CrawlOutcome(books=...)。
- year_from 参数随迁移删除（内部自算滚动窗口）。
- SUPPORTS_BACKFILL = True 声明在 PrhApiCrawler；
  API_KEY_CONFIG='GOOGLE_API_KEY' 声明在 GoogleBooksCrawler（子类继承）；
  API_KEY_CONFIG='PRH_API_KEY' + api_key_required=True + REQUEST_DELAY=0.5 声明在 PrhApiCrawler。

## 变更文件

- **T1**: app/services/publisher_crawler/base_crawler.py（+CrawlRequest/CrawlOutcome、
  基类声明、摘除死方法）
- **T2**: app/services/new_book/sync_engine.py
- **T3**: app/services/publisher_crawler/*.py（15 个适配器）、
  tests/test_sync_engine.py、tests/test_publisher_crawler*.py、
  tests/test_prh_api_crawler.py、tests/test_date_filter_counters.py、
  tests/test_new_books_routes.py（若涉及）

## 行为保持不变量

- 回填开关仍由引擎按出版社存量书数决定，适配器无状态。
- with crawler: 上下文与单家出版社超时线程模型不变。
- 空结果（total==0）→ empty/failure 语义不变。
- date_filter_stats 仅测量持久化，不改变同步行为。
- PRH 无 PRH_API_KEY 时快速失败（该出版社标记失败，不阻塞其余）。

## 测试策略

- T1：既有全量测试保持绿色（新对象与声明为纯增量；死方法摘除后
  legacy 爬虫测试不变）。
- T2：以 mock 适配器验证——backfill 判定、API Key 注入（GOOGLE/PRH 两分支）、
  stats 合入、空结果、超时熔断路径。
- T3：迁移后的适配器单测覆盖 get_new_books 返回 CrawlOutcome 形状与统计字段；
  删除 year_from 相关断言。
- 验收门：全量 pytest、ruff check、mypy 通过。

## 接口演化（#153）

code review 发现 6 个适配器重复「get_new_books → CrawlOutcome」包装后，
经 grilling 决策（2026-08-14）收敛为基类模板方法：

- BaseCrawler.get_new_books 变为具体模板方法：组装
  CrawlOutcome(books=_iter_new_books(request), date_filter_stats=self.date_filter_stats)
  ——钩子直接收 CrawlRequest 对象（code review 发现三参重组即 Data Clumps）。
- _iter_new_books 提升为唯一抽象钩子（单参数 CrawlRequest，非回填型实现
  读取并忽略 backfill 字段）。
- 适配器删除全部包装；date_filter_stats=None 的适配器由基类 __init__ 默认值
  天然得到 None，无需分支。

## 术语

见根目录 CONTEXT.md（出版社、爬虫适配器、抓取请求、抓取结果、
回填窗口、日期过滤计数、API Key 配置）。
