# CONTEXT.md — BookRank 领域词汇表

本文件沉淀 BookRank 的领域术语。代码与文档中出现的概念以此处定义为准；
未收录的词请勿随意发明，先回到这里对齐。

## 词汇表

- **出版社（Publisher）** — 新书速递同步的数据源主体，对应
  `app/models/new_book.py` 的 `Publisher` 行与
  `app/data/publishers.py` 的展示目录条目。每家出版社绑定一个爬虫类
  （`crawler_class`）与启用状态（`is_active`）。
- **爬虫适配器（crawler adapter）** — 实现 `BaseCrawler` 接口、从某一
  数据源（Google Books / PRH 官方 API / 出版社站点等，2026-08 死适配器
  清理后仅保留生产活跃类）产出新书数据的模块。一个接口、多个适配器：
  基类模板方法 `get_new_books(CrawlRequest) -> CrawlOutcome` 组装抓取结果，
  适配器只实现 `_iter_new_books(request)` 钩子；适配器之间的差异（回填能力、
  所需 API Key、日期过滤计数）必须在基类声明，调用方不得用 `getattr`
  猜测。
- **同步请求闸门（sync request gate）** — 应用级同步请求状态模块
  （`SyncRequestGate`，注册于 `app.extensions['sync_request_gate']`）：同步冷却、
  multi-worker 锁、per-IP 导出冷却（惰性过期清理）与静态播种一次性化。
- **导出冷却（export cooldown）** — 每 IP 10 秒的 CSV 导出限速，状态在闸门内。
- **抓取请求（CrawlRequest）** — 调用爬虫接口时传入的请求参数对象：
  `category`（分类筛选）、`max_books`（最大取书数）、`backfill`
  （是否回填窗口模式）。
- **抓取结果（CrawlOutcome）** — 爬虫接口的返回对象：
  `books`（`BookInfo` 可迭代流）+ `date_filter_stats`
  （日期过滤计数，非 Google Books 系为 `None`）。
- **回填窗口（backfill）** — 出版社无存量书时启用的一次性大窗口模式：
  由同步引擎按存量书数决定并写入 `CrawlRequest.backfill`，适配器只负责
  按开关执行，保持无状态。
- **日期过滤计数（date_filter_stats）** — Google Books 系适配器在抓取
  过程中统计的分类拒绝计数器（traversed_total、rejected_no_date 等），
  随 `CrawlOutcome` 返回，仅供测量持久化，不改变同步行为。
- **封面解析（cover resolution）** — 获奖书籍封面的单一获取策略
  （`CoverResolver`）：本地文件 → 原 URL 缓存 → 按需回源 → 缓存 → 持久化；
  批编排（清单/延迟/统计）在 `AwardCoverSyncService`。
- **分类清洗（category cleanup）** — 对 `NewBook.category` 的营销文案过滤与
  英文→中文归一。sanitize=单值规则（`publisher_data.sanitize_category`），
  scan=清单扫描，apply=批量写入（`category_cleanup_service`）；入库路径只做
  单值清洗，不参与扫描。
- **API Key 配置（API_KEY_CONFIG / api_key_required / REQUEST_DELAY）** — 基类声明的
  配置事实：适配器所需的 API Key 配置键名（如 `GOOGLE_API_KEY`、
  `PRH_API_KEY`）、缺 key 时是否快速失败（PRH 为必填），以及引擎注入
  配置时的请求间隔（`REQUEST_DELAY`，如 PRH 的 0.5s 礼貌间隔）。

## 相关文档

- 架构词汇（模块/接口/深度/接缝/适配器/杠杆/局部性）见 codebase-design skill。
- 同步流水线设计见 `docs/superpowers/specs/` 下对应 spec。
