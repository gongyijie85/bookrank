# Crawl4AI 在 GitHub Actions 中的生产集成约束

> Wayfinder research ticket: [#117](https://github.com/gongyijie85/bookrank/issues/117)
>
> 核对日期：2026-08-09
>
> 研究范围：Crawl4AI 官方文档、官方仓库/发布/安全公告、GitHub Actions 官方文档，以及 BookRank 当前源码。本文区分“已核实事实”“推论”和“决策建议”；未对出版社站点进行实时压测。

## 结论先行

Crawl4AI 适合承担“没有可靠官方 API/RSS、但有公开官网新书页面”的浏览器采集层，但 BookRank 当前实现不能直接扩容上线。建议采用 **GitHub Actions 内进程 SDK + 精确版本锁定 + 单个长生命周期浏览器 + `arun_many()` 受控并发 + 确定性 Schema 主路径 + 模板级 AI 降级 + 出版社级原子批次**。Crawl4AI 不应替代 PRH、Google Books、Open Library 等已有 API 通道，也不应部署到 Render Web 服务。

上线前必须解决四个阻断项：

1. 工作流当前执行未固定版本的 `pip install crawl4ai`，不能复现，也会在新版本发布后无审查升级；当前官方最新稳定发布为 `0.9.2`，应精确锁定。[BookRank 工作流](../.github/workflows/update-books.yml#L140-L148)；[Crawl4AI v0.9.2 官方发布](https://github.com/unclecode/crawl4ai/releases/tag/v0.9.2)；[PyPI 发布记录](https://pypi.org/project/Crawl4AI/)
2. `MixedCrawl4AICrawler` 每个 URL 都创建并关闭一个 `AsyncWebCrawler`，再由同步包装为每个 URL 创建一次事件循环；这与官方“一次创建、执行多个 `arun()`/`arun_many()`、最后关闭”的生命周期相反。[当前实现](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L90-L123)；[官方 `AsyncWebCrawler` 生命周期](https://docs.crawl4ai.com/api/async-webcrawler/)
3. `requests` 路径因 robots.txt 禁止而返回 `None` 后，混合层无法区分“政策禁止”和“网络失败”，会继续进入未设置 `check_robots_txt=True` 的 Crawl4AI；这会绕过已锁定的合规边界。[BaseCrawler robots 分支](../app/services/publisher_crawler/base_crawler.py#L202-L239)；[混合降级分支](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L135-L158)；[Crawl4AI robots 行为](https://docs.crawl4ai.com/advanced/advanced-features/#6-robotstxt-compliance)
4. `update_books.py` 把异常转换为空列表，随后仍覆盖每家出版社 JSON 和汇总 JSON；因此“空结果”目前会被当成可发布结果，违反“失败批次不得覆盖上次成功数据”。[异常转空列表](../update_books.py#L58-L84)；[无条件覆盖输出](../update_books.py#L89-L113)

## 决策表

| 主题 | 生产决策 | 依据 |
| --- | --- | --- |
| 运行形态 | 只在 GitHub Actions 中使用 Python **in-process SDK**；不启用 Crawl4AI Docker API，不放入 Render Web worker | v0.9.0 的主要破坏性变更和多项高危漏洞集中在自托管 HTTP 服务，官方明确 in-process SDK API 不受该组服务端破坏性变更影响；Render 当前又以单 worker/低内存为约束。[v0.9.0 changelog](https://github.com/unclecode/crawl4ai/blob/v0.9.2/CHANGELOG.md#090---2026-06-18)；[Render 配置](../render.yaml#L47-L52) |
| 版本 | 首版锁定 `crawl4ai==0.9.2`；升级必须经过 fixture、真实站点试跑和安全公告复核 | `0.9.2` 是 2026-07-15 的官方 latest release，且修复了流式抓取关闭时 `MemoryAdaptiveDispatcher` 的 task/page 泄漏。[官方发布](https://github.com/unclecode/crawl4ai/releases/tag/v0.9.2)；[PyPI 0.9.2 描述](https://pypi.org/project/Crawl4AI/) |
| 浏览器安装 | 安装与 Python Playwright 版本匹配的 Chromium；CI 不再使用未绑定 Python 依赖版本的 `npx playwright` 路径 | Playwright 明确每个库版本需要对应浏览器二进制，并给出 Python CLI 的 `playwright install --with-deps chromium`；Crawl4AI 官方完整初始化入口是 `crawl4ai-setup`。[Playwright 浏览器文档](https://playwright.dev/python/docs/browsers)；[Crawl4AI 安装文档](https://docs.crawl4ai.com/core/installation/) |
| 生命周期 | 每个 Actions 采集 job 创建一个 `AsyncWebCrawler`，跨来源/URL 复用，最终统一关闭 | 官方建议通常只创建一次 crawler，然后执行多个 `arun()`，批量用 `arun_many()`。[AsyncWebCrawler](https://docs.crawl4ai.com/api/async-webcrawler/)；[`arun_many()`](https://docs.crawl4ai.com/api/arun_many/) |
| 并发 | `MemoryAdaptiveDispatcher(memory_threshold_percent=70, max_session_permit=2)`；同域配 `RateLimiter`，流式消费结果 | 官方 dispatcher 可按内存暂停、限制 session 数并对 429/503 退避；`max_session_permit` 官方默认 10，但“两页上限”是本项目保守预算，需由 14 天试点数据复核。[多 URL 调度文档](https://docs.crawl4ai.com/advanced/multi-url-crawling/) |
| 缓存 | 每日新书发现使用 `CacheMode.BYPASS`；不跨 workflow 缓存页面内容；robots 缓存采用库默认机制并记录检查结果 | `CacheMode.BYPASS` 跳过读写缓存；GitHub-hosted job 从干净 runner 开始，只有显式 Actions cache/artifact 才跨 run 保留。[Crawl4AI cache modes](https://docs.crawl4ai.com/core/cache-modes/)；[GitHub dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching) |
| robots/反爬 | 显式设置 `check_robots_txt=True`；403/验证码/登录墙/明确禁止均停止官网路径，不使用 stealth、代理或 UA 轮换绕过 | Crawl4AI 在 robots 禁止时返回失败和 403；BookRank 当前 `_make_request` 会在 403 后轮换浏览器 UA，需要从新路径移除。[Crawl4AI robots](https://docs.crawl4ai.com/advanced/advanced-features/#6-robotstxt-compliance)；[当前 UA 轮换](../app/services/publisher_crawler/base_crawler.py#L267-L276) |
| 提取 | JSON-LD/稳定 DOM 优先，`JsonCssExtractionStrategy` 或 `JsonXPathExtractionStrategy` 产出 `extracted_content`；LLM 只处理未知模板/规则漂移 | 官方将 CSS/XPath/Regex 定位为精确、可重复、低成本路径，并建议一致结构优先使用它们；LLM 适合复杂非结构化页面，输出仍需校验。[无 LLM 提取](https://docs.crawl4ai.com/extraction/no-llm-strategies/)；[LLM 提取](https://docs.crawl4ai.com/extraction/llm-strategies/) |
| 成败契约 | URL 级结果与出版社批次分离；只有全批次校验通过才可交付 Render；空列表不是成功 | `CrawlResult.success` 只表示抓取管线无重大错误，并同时提供 HTTP 状态、跳转状态、错误文本和提取内容；业务字段完整性必须另行判定。[`CrawlResult` 官方契约](https://docs.crawl4ai.com/api/crawl-result/) |
| Actions 交付 | crawl/validate job 只读仓库；通过 artifact 交给 import job，后者持 `CRON_SECRET` 并调用新建的批次导入端点；失败证据 artifact 保留 7 天 | GitHub 支持 artifact 跨 job 传递并允许单 artifact 自定义保留期；当前 cron 端点只会在 Render 启动旧同步，不是批次导入端点。[Artifacts 跨 job](https://docs.github.com/en/actions/tutorials/store-and-share-data)；[artifact 保留](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)；[当前 trigger 端点](../app/routes/api/cron.py#L62-L87) |

## 1. 版本、锁定与安装

### 已核实事实

- 截至核对日，GitHub 将 `v0.9.2` 标记为 Latest；PyPI 的最新文件也是 `crawl4ai-0.9.2`，上传于 2026-07-15。PyPI 元数据要求 Python `>=3.10`，并列出 Python 3.13 classifier，因此当前 workflow 的 Python 3.13 在声明支持范围内。[GitHub release](https://github.com/unclecode/crawl4ai/releases/tag/v0.9.2)；[PyPI](https://pypi.org/project/Crawl4AI/)；[当前 Python 3.13](../.github/workflows/update-books.yml#L133-L144)
- `0.9.2` 是维护补丁，官方摘要列出流式抓取关闭时 dispatcher task/page 泄漏、Playwright headless-shell packaging 等修复；本项目准备使用流式 `arun_many()`，因此不应选择早于该修复的 `0.9.x`。[PyPI 项目描述](https://pypi.org/project/Crawl4AI/)
- 官方 `0.8.6` 发布因上游 `litellm` PyPI 供应链事件替换依赖；`0.9.0` 又修复了影响 `<=0.8.9` 的浏览器下载任意文件写入，后者明确同时可从 SDK 触达。[v0.8.6 release](https://github.com/unclecode/crawl4ai/releases/tag/v0.8.6)；[GHSA-2jq4-q6vv-4cp3](https://github.com/unclecode/crawl4ai/security/advisories/GHSA-2jq4-q6vv-4cp3)
- pip 官方说明：仅锁顶层版本可避免该包无审查升级，但完整可复现还需锁传递依赖；hash-checking 可防止下载内容与批准哈希不一致，适合自动部署。[pip repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/)

### 决策建议

1. 在专用 crawl lock/requirements 中写入 `crawl4ai==0.9.2`，不要继续在 workflow 内单独执行浮动的 `pip install crawl4ai`。[当前浮动安装](../.github/workflows/update-books.yml#L140-L145)
2. 第一阶段至少锁顶层版本；上线稳定后生成包含传递依赖和 SHA-256 的 lock，并通过 `--require-hashes` 安装。PyPI 当前公开了 `0.9.2` wheel/sdist 的 SHA-256，可作为核验起点，但实际 lock 必须包含安装图中的全部发行物。[PyPI 文件哈希](https://pypi.org/project/Crawl4AI/#files)；[pip hash-checking](https://pip.pypa.io/en/stable/topics/repeatable-installs/#hash-checking)
3. 每月检查官方 release、安全公告和 PyPI；安全修复升级可以加急，但仍要跑固定 fixture 与两家试点站点。Crawl4AI 在 PyPI 仍标为 Beta，不能把 semver 补丁视为零风险升级。[PyPI classifier](https://pypi.org/project/Crawl4AI/)

推荐的 CI 安装骨架：

```bash
python -m pip install --require-hashes -r requirements-crawl.lock
python -m playwright install --with-deps chromium
crawl4ai-doctor
```

若第一阶段尚未生成 hash lock，可临时用 `python -m pip install "crawl4ai==0.9.2"`，但不得使用无版本约束的安装。Crawl4AI 官方推荐安装后运行 `crawl4ai-setup`，并可用 `crawl4ai-doctor` 检查 Python、Playwright 与环境冲突；只需要标准 Chromium 的 CI 可以使用 Playwright Python 官方的单浏览器安装命令来减小下载面。[Crawl4AI installation](https://docs.crawl4ai.com/core/installation/)；[Playwright installation](https://playwright.dev/python/docs/browsers)

当前 workflow 的 `npx playwright install --with-deps chromium` 应改为 Python Playwright CLI；Playwright 官方强调库升级后可能需要重新安装与该库版本匹配的浏览器，因此安装步骤必须在 pinned Python 依赖之后执行。[当前 `npx` 步骤](../.github/workflows/update-books.yml#L140-L149)；[Playwright version/browser coupling](https://playwright.dev/python/docs/browsers)

## 2. `AsyncWebCrawler` 生命周期与并发

### 已核实事实

- 官方推荐 `async with AsyncWebCrawler(...)` 包住多次抓取，或显式 `start()`/`close()`；`arun_many()` 用同一个 crawler 批量调度 URL，并逐 URL 返回 `CrawlResult`。[AsyncWebCrawler API](https://docs.crawl4ai.com/api/async-webcrawler/)；[`arun_many()` API](https://docs.crawl4ai.com/api/arun_many/)
- `MemoryAdaptiveDispatcher` 会在系统内存超过阈值时暂停派发，并由 `max_session_permit` 设并发上限；可附加 `RateLimiter` 对 429/503 退避。官方默认 `max_session_permit=10`，这不是 BookRank 应直接沿用的安全值。[dispatcher 参数](https://docs.crawl4ai.com/advanced/multi-url-crawling/#31-memoryadaptivedispatcher-default)
- `arun_many(stream=True)` 可以按完成顺序流式处理结果，避免等全部 URL 完成后才开始业务校验；每项可带 `dispatch_result`，其中有内存、峰值内存、开始/结束和调度错误。[流式示例](https://docs.crawl4ai.com/advanced/multi-url-crawling/#42-streaming-mode)；[`dispatch_result`](https://docs.crawl4ai.com/api/crawl-result/#6-dispatch_result-optional)

### 当前实现差距

1. `_crawl_with_crawl4ai_async()` 在每个 URL 内部创建 `BrowserConfig`、`CrawlerRunConfig` 和 `AsyncWebCrawler`，退出后立即销毁浏览器；同步包装又对每个 URL 执行 `asyncio.run()`。[当前实现](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L90-L123)
2. Python 官方说明 `asyncio.run()` 会创建并关闭事件循环，且同一线程已有运行中的 event loop 时不能调用；因此该同步桥不适合作为新的 async 批量协调器边界。[Python `asyncio.run`](https://docs.python.org/3/library/asyncio-runner.html#asyncio.run)
3. `_check_crawl4ai()` 调用 `importlib.util.find_spec('crawl4ai')` 却没有检查返回值，随后无条件返回 `True`；Python 官方说明找不到 spec 时返回 `None`，所以“未安装”可以被误报为“可用”。[当前检测](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L77-L88)；[Python `find_spec`](https://docs.python.org/3/library/importlib.html#importlib.util.find_spec)
4. `update_books.py` 外层以出版社数量作为 `ThreadPoolExecutor.max_workers`；若把多个出版社直接改接当前 Mixed 类，就可能由多个线程分别启动浏览器，绕开 Crawl4AI 自己的内存调度器。[当前七路线程](../update_books.py#L72-L84)

### 决策建议

使用一个异步 orchestration 层，而不是让每个出版社爬虫自己创建浏览器：

```python
dispatcher = MemoryAdaptiveDispatcher(
    memory_threshold_percent=70.0,
    max_session_permit=2,
    rate_limiter=RateLimiter(base_delay=(1.0, 3.0), max_retries=2),
)

async with AsyncWebCrawler(config=browser_config) as crawler:
    async for result in await crawler.arun_many(
        urls,
        config=run_configs,
        dispatcher=dispatcher,
    ):
        validate_and_accumulate(result)
```

`max_session_permit=2` 是 Wayfinder 试点约束，不是库的性能上限。试点必须记录 `dispatch_result.peak_memory`、耗时、429/503、超时和 Chromium 进程退出情况；只有在 14 天数据证明有余量时才评估提高并发。[Crawl4AI dispatcher/monitor](https://docs.crawl4ai.com/advanced/multi-url-crawling/)；[GitHub runner 资源](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for-public-repositories)

同一 `session_id` 只用于必须连续操作同一页面的顺序流程；官方明确 session management 适用于顺序工作，不适合并行抓取。普通详情页并发应让 dispatcher 管理独立页面，不共享同一 session。[Session Management](https://docs.crawl4ai.com/advanced/session-management/)

## 3. 缓存、robots.txt 与站点合规

### 缓存

Crawl4AI 的新缓存枚举包含 `ENABLED`、`DISABLED`、`READ_ONLY`、`WRITE_ONLY`、`BYPASS`；当前 Mixed 已使用 `BYPASS`。对每日新书发现，保留 `BYPASS` 可以避免读到前一轮页面，但同一批次必须先按 canonical URL 去重，避免重复浏览器请求。[CacheMode 官方定义](https://docs.crawl4ai.com/core/cache-modes/)；[当前配置](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L100-L108)

GitHub-hosted runner 每个 job 是新 VM，job 完成后被销毁；跨 run 保留数据必须显式使用 cache 或 artifact。因此不应依赖本机 Crawl4AI 页面缓存实现“保留上次成功批次”，上次成功批次必须在数据库/受控产物层保存。[GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)；[GitHub caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching)

失败 HTML/Markdown/截图可作为私有 workflow artifact 保留 7 天，成功页面不上传；GitHub 官方允许给单个 artifact 自定义 retention，默认则是 90 天。[artifact retention](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)

### robots 与禁止绕过

Crawl4AI 只有显式设置 `CrawlerRunConfig(check_robots_txt=True)` 才执行 robots 检查；robots 禁止会返回失败和 403，robots 文件抓取失败时官方实现为允许继续，robots 结果在本机 SQLite 中默认缓存 7 天。[官方 robots 说明](https://docs.crawl4ai.com/advanced/advanced-features/#6-robotstxt-compliance)

BookRank 当前 `BaseCrawler` 默认尊重 robots，但 robots 文件无法获取时同样 fail-open；这与 Crawl4AI 官方默认策略一致。批次元数据应记录 `robots_checked`、`robots_allowed` 和检查错误，以便区分“明确禁止”与“无法核实”。[当前 BaseCrawler robots 初始化](../app/services/publisher_crawler/base_crawler.py#L178-L222)

当前 Mixed 存在政策旁路：`BaseCrawler._make_request()` 对 robots 禁止返回 `None`，`_make_request_with_fallback()` 又把所有 `None` 当网络失败转入 Crawl4AI，而其 `CrawlerRunConfig` 未启用 robots。新实现必须在 crawler 调度之前完成独立 robots gate，或让请求层返回带原因的失败类型；明确 `disallowed` 时不允许进入任何 fallback。[当前请求 gate](../app/services/publisher_crawler/base_crawler.py#L224-L239)；[当前无差别 fallback](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L135-L158)

同理，403、验证码、登录墙和明确反自动化条款必须映射为 `POLICY_OR_ACCESS_BLOCKED`，随后回退 Google Books/RSS/Sitemap，而不是启用 `browser_type="undetected"`、代理链、AI 生成 JS 或现有的 User-Agent 轮换。该约束来自已确认的 Wayfinder 决策；当前 UA 轮换行为与之冲突。[当前 403 处理](../app/services/publisher_crawler/base_crawler.py#L267-L276)

## 4. CSS/XPath/JSON 与 LLM 的职责边界

### 确定性主路径

Crawl4AI 的 `JsonCssExtractionStrategy` 与 `JsonXPathExtractionStrategy` 接收包含 base selector、字段 selector、类型和默认值的 schema，结果写入 `result.extracted_content`，内容是需要 `json.loads()` 的 JSON 字符串。官方把该路径定位为重复页面上的快速、精确、可复现提取。[No-LLM Strategies](https://docs.crawl4ai.com/extraction/no-llm-strategies/)；[Crawler result](https://docs.crawl4ai.com/core/crawler-result/)

BookRank 应为 Hachette、HarperCollins 分别维护版本化 schema：优先解析页面内 JSON-LD，再用 CSS/XPath 提取列表链接和详情字段；ISBN checksum、出版日期窗口、作者/标题非空、规范 URL 和作品归并仍由项目代码校验。`result.success=True` 不代表这些业务条件成立。[CrawlResult `success`](https://docs.crawl4ai.com/api/crawl-result/#12-success-bool)；[BookRank `BookInfo`](../app/services/publisher_crawler/base_crawler.py#L43-L81)

现有 Mixed 没有使用 `extraction_strategy` 或 `extracted_content`，而是取得完整 `result.html` 后再次交给 BeautifulSoup；它因此只把 Crawl4AI 当浏览器下载器，未获得 schema 输出、逐 URL 错误契约或 dispatcher 指标。[当前 HTML 回传](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L105-L115)；[再次 BeautifulSoup](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L149-L155)

对于本来返回 JSON 的官方 API，不要经 Chromium 抓取 HTML 再猜 JSON。当前 `OpenLibraryCrawler` 把 Crawl4AI 作为 JSON API fallback，但本次范围已明确“保留可靠 API”，因此该路径不应成为新架构模板。[当前 Open Library Crawl4AI fallback](../app/services/publisher_crawler/open_library.py#L80-L139)；[来源启用状态](../app/services/publisher_data.py#L17-L40)

### AI 降级路径

官方 `LLMExtractionStrategy` 面向散乱、需要语义理解的内容；它可能按 token 阈值分块并发调用模型，成本和延迟高于 CSS/XPath，且官方明确要求对 JSON 做后置校验。[LLM Strategies](https://docs.crawl4ai.com/extraction/llm-strategies/)

生产规则如下：

1. 日常页面只运行 JSON-LD/CSS/XPath/Regex，不逐书调用模型。
2. 仅当已知 schema 在代表页面上失效，或出现未知模板时，允许每来源每批次一次“模板级 AI 尝试”。AI 只能输出候选记录或候选 schema，不能自动修改生产规则。
3. “一次模板尝试”不等于“一次计费 API 请求”：官方 `generate_schema()` 可能执行字段推断、生成、验证重试等多个模型调用，`LLMExtractionStrategy` 也可能因 chunking 发出多次请求。实现必须同时限制 attempt、实际 provider call、token 和费用，并记录 `TokenUsage`/`show_usage()`。[Schema generator token usage](https://docs.crawl4ai.com/extraction/no-llm-strategies/#token-usage-tracking)；[LLM chunking/usage](https://docs.crawl4ai.com/extraction/llm-strategies/#8-token-usage-show-usage)
4. AI 输出必须经过与确定性路径完全相同的 Pydantic/业务校验；缺 ISBN-13、日期窗口不合格、来源 URL 缺失或作者/标题缺失时不得自动展示。官方也警告 schema 模式仍可能产生非法/部分 JSON或漏字段。[LLM caveats](https://docs.crawl4ai.com/extraction/llm-strategies/#10-best-practices-caveats)

## 5. 结果与失败契约

### Crawl4AI 原生契约

每个 `CrawlResult` 至少提供 `url`、`html`、`success`、`extracted_content`、`error_message`、`status_code`、`redirected_status_code`；并发时还可提供 `dispatch_result`。官方定义的 `success` 只是“抓取管线没有重大错误”，不是“结构化数据合格”。[CrawlResult fields](https://docs.crawl4ai.com/api/crawl-result/)

建议映射为 BookRank 自有的 URL 级状态：

| 状态 | 判定 | 批次动作 |
| --- | --- | --- |
| `FETCH_FAILED` | `success=False`，超时、网络错误或 5xx | 记录 `error_message`/status；允许有限重试，然后来源回退 |
| `POLICY_OR_ACCESS_BLOCKED` | robots 403、明确 403/验证码/登录墙 | 不重试绕过；官网来源本批失败，走合规 fallback |
| `EXTRACTION_FAILED` | 抓取成功但 JSON 无法解析、schema 空结果或关键字段缺失 | 可触发一次模板级 AI；仍失败则整批失败 |
| `VALIDATION_FAILED` | ISBN、日期窗口、必填字段、来源 URL 或重复规则不通过 | 进入待验/隔离，不自动发布 |
| `VALID` | 抓取、提取和业务校验全部通过 | 加入该出版社候选批次 |

出版社批次必须另有 `batch_id`、来源、started/finished 时间、schema 版本、提取方式、URL 计数、各状态计数、内容摘要和总体状态。只有总体状态 `VALIDATED` 才允许导入；`0` 条记录、任一必需分页失败或摘要不一致都不能标记成功。这是 BookRank 的业务契约，不由 `CrawlResult.success` 自动提供。[CrawlResult 语义](https://docs.crawl4ai.com/api/crawl-result/#12-success-bool)

当前实现丢失了这些证据：Mixed 捕获所有异常后只返回 `None`，没有向上保留 status、redirect、`error_message` 或 dispatcher 指标；`BaseCrawler.crawl()` 也捕获迭代异常并返回已经收集到的部分列表。[Mixed 异常吞并](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L110-L133)；[BaseCrawler 返回部分列表](../app/services/publisher_crawler/base_crawler.py#L498-L530)

`update_books.py` 又把出版社异常转换为空列表并无条件写出所有 JSON，所以现有返回类型无法满足“按出版社原子、空批次保护、保留上次成功批次”。迁移需要 typed result，不应继续以 `list[BookInfo]` 的空/非空承载所有状态。[当前 worker](../update_books.py#L58-L86)；[当前导出](../update_books.py#L89-L113)

## 6. 安全约束

### 版本安全

- `<=0.8.9` 的浏览器/HTTP 下载路径存在可由页面控制文件名触发的任意文件写入，SDK 用户也可触达；官方 patched version 是 `0.9.0`。因此 `0.9.0` 是最低安全下限，首版直接使用当前 `0.9.2`。[GHSA-2jq4-q6vv-4cp3](https://github.com/unclecode/crawl4ai/security/advisories/GHSA-2jq4-q6vv-4cp3)
- `<=0.8.9` Docker API 还存在 Chromium launch argument injection RCE；官方说明 patched version 为 `0.9.0`，且 in-process SDK 的受信调用者不受该服务端 request-boundary 问题影响。本项目没有必要引入 Docker API 攻击面。[GHSA-r253-r9jw-qg44](https://github.com/unclecode/crawl4ai/security/advisories/GHSA-r253-r9jw-qg44)
- `0.8.6` 曾因上游 PyPI 供应链事件替换 LLM 依赖，这支持“精确版本 + 传递依赖 lock + hashes”的供应链策略。[v0.8.6 release](https://github.com/unclecode/crawl4ai/releases/tag/v0.8.6)；[pip hash checking](https://pip.pypa.io/en/stable/topics/repeatable-installs/#hash-checking)

### 运行隔离

只允许来自配置的出版社 HTTPS host；列表页抽取出的详情 URL 必须再次做 scheme/host allowlist，禁止 `file:`、`data:`、`javascript:`、localhost、私网和云 metadata 地址。Crawl4AI 官方对 library usage 同样建议校验不可信 URL、清洗输出，并警告 hooks 可执行任意代码。[官方 Security Policy](https://github.com/unclecode/crawl4ai/security)

关闭下载、PDF、MHTML、截图等非必要能力；失败截图只有明确需要时才开启，并写入 runner 临时目录。即使 `0.9.0` 已修复路径穿越，最小功能面仍能降低被访问页面控制副作用的概率。[下载漏洞及修复](https://github.com/unclecode/crawl4ai/security/advisories/GHSA-2jq4-q6vv-4cp3)

不执行由网页或 AI 生成的 hook/JS，不把 ZHIPU、Google 或 `CRON_SECRET` 暴露给纯浏览器抓取步骤。LLM fallback 与 Render 导入应是后续独立步骤，只接收裁剪后的文本/已验证 JSON。

## 7. GitHub Actions 约束与工作流拆分

### Runner 资源与网络

当前 job 使用 `ubuntu-latest`。对 public repository，GitHub 官方当前规格是 4 vCPU、16 GB RAM、14 GB SSD；如果仓库变为 private，同标签规格是 2 vCPU、8 GB RAM、14 GB SSD。浏览器并发预算不能只按 public 规格写死。[runner 规格](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#supported-runners-and-hardware-resources)

GitHub-hosted Ubuntu runner 位于 Azure，出口 IP 范围很多且每周更新，GitHub 不建议将全部范围加入 allowlist。由此推论：Hachette/HarperCollins 若按云出口或 Azure ASN 拦截，换成 Crawl4AI 浏览器也未必成功；必须用真实 scheduled run 验证，不能把“Chromium 能渲染”当成“可绕过 Cloudflare”。[GitHub Actions IP](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#ip-addresses)；[BookRank 已记录的生产阻断](../app/services/publisher_data.py#L48-L62)

GitHub-hosted job 的平台最大运行时间为 6 小时，当前 workflow 自行设置为 60 分钟；来源级目标仍应是 10 分钟内完成，并为每个 URL 和每个来源分别设置 timeout，不能只依赖 job timeout。[GitHub token/job lifetime](https://docs.github.com/en/actions/concepts/security/github_token)；[当前 60 分钟](../.github/workflows/update-books.yml#L120-L127)

当前 workflow 使用 `concurrency.group=update-books` 和 `cancel-in-progress=true`，新 run 会取消正在运行的旧 run。只有在“未完成批次永不导入、导入端点按稳定 `batch_id` 幂等”的前提下，这一设置才安全。[当前 concurrency](../.github/workflows/update-books.yml#L14-L16)

### 权限与 secrets

当前 workflow 在顶层授予 `contents: write`、`issues: write`，因此 frequency check 和浏览器抓取 job 都继承写权限；GitHub 官方建议按 job 授予最小 `GITHUB_TOKEN` 权限。[当前顶层权限](../.github/workflows/update-books.yml#L3-L5)；[GitHub least privilege](https://docs.github.com/actions/how-tos/security-for-github-actions/security-guides/automatic-token-authentication#modifying-the-permissions-for-the-github_token)

当前 `actions/checkout@v4` 默认持久化 auth token，官方 action 允许通过 `persist-credentials: false` 关闭。crawl job 应设置 `contents: read` 且关闭凭据持久化；只有需要提交静态兜底数据的独立 publish job 才获得 `contents: write`。[actions/checkout 官方说明](https://github.com/actions/checkout#usage)

建议拆为：

1. `crawl`：`contents: read`，无 `CRON_SECRET`，只抓取并输出 URL 级原始结果；checkout 使用 `persist-credentials: false`。
2. `validate`：接收 artifact；确定性校验。只有需要 AI fallback 的该步骤获得 `ZHIPU_API_KEY`，且只看到裁剪内容。
3. `import`：`needs: validate`；获得 `CRON_SECRET`，把已签名/摘要一致的出版社批次提交到 Render；它不启动 Chromium。
4. `alert`：仅连续三次失败时获得 `issues: write`；其余 job 不需要 issue 权限。
5. `legacy-static-publish`：试点期可保留的应急 job；若继续 git push，单独授予 `contents: write`，不要让浏览器 job 持有写 token。

GitHub 官方支持用 artifact 在 jobs 间传递文件，且有 `needs` 保证下游只在上游成功后运行；cache 用于可再生依赖，artifact 用于 job 产物和审计证据，两者不能互换。[Artifacts between jobs](https://docs.github.com/en/actions/tutorials/store-and-share-data#passing-data-between-jobs-in-a-workflow)；[cache vs artifact](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching#artifacts-versus-dependency-caching)

现有 `/api/cron/trigger-new-books-sync` 只是验证 `CRON_SECRET` 后在 Render 后台线程启动旧同步，返回时任务尚未完成；它不能接收批次、校验摘要或按 `batch_id` 幂等。因此 Q7 所需的是一个新的 import endpoint，不能复用该 trigger endpoint。[当前 endpoint](../app/routes/api/cron.py#L62-L87)

## 8. BookRank 具体迁移关注点

### `MixedCrawl4AICrawler`

| 问题 | 证据 | 迁移要求 |
| --- | --- | --- |
| 可用性误判 | `find_spec()` 返回值未检查。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L77-L88) | 改成真实 import/version smoke check；版本不符时 job fail-fast |
| 每 URL 启停浏览器 | 每次 `async with AsyncWebCrawler`。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L90-L115) | crawler 生命周期提升到 batch orchestrator |
| 每 URL 新事件循环 | `asyncio.run(wait_for(...))`。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L120-L133) | Actions 入口只运行一次 async main |
| 无结构化提取 | 只返回 `result.html` 后用 BeautifulSoup。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L110-L155) | 按来源配置 extraction strategy，消费 `extracted_content` |
| robots 旁路 | requests 的所有 `None` 都触发 Crawl4AI，run config 无 robots flag。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L105-L158) | typed failure + crawler 前置 policy gate + `check_robots_txt=True` |
| 错误证据丢失 | catch-all 只返回 `None`。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L116-L133) | 保留 status/error/redirect/dispatch metrics |
| 占位值可能入流 | 缺字段时返回 `Unknown Title/Author`。[代码](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L388-L402) | 必填缺失即 validation failure，不造占位业务数据 |

该类更适合被“替换为/拆入新的 Actions batch adapter”，而不是继续扩充同步 fallback 方法。现有具体类也没有形成 `BaseCrawler -> Mixed -> publisher` 的运行继承链：Hachette/HarperCollins 直接继承 `BaseCrawler`，Simon & Schuster/Macmillan 继承 Google Books crawler。[Hachette](../app/services/publisher_crawler/hachette.py#L27)；[HarperCollins](../app/services/publisher_crawler/harpercollins.py#L28)；[Simon & Schuster](../app/services/publisher_crawler/simon_schuster.py#L19)；[Macmillan](../app/services/publisher_crawler/macmillan.py#L49)

### `update_books.py`

当前脚本同时调度 7 个来源，并让线程数等于来源数；Crawl4AI 接入后必须把浏览器来源从该线程池抽离，统一交给 async dispatcher，API/RSS 来源可以保留独立的轻量并发。[当前 publishers/线程池](../update_books.py#L30-L84)

当前 `_sync_one` 的异常与合法空列表都被编码成 `[]`，导出器无法区分；必须改成带状态的 source result，并让失败出版社沿用上次成功文件/数据库批次。[当前失败编码](../update_books.py#L58-L86)

当前导出会先覆盖 `all_books.json`，再逐个覆盖来源文件，最后写一个把所有来源都列为成功的更新时间文件；这不是原子发布。试点期静态兜底应先写临时 staging 目录，整批验证后再发布，或完全由 Render import endpoint 管理原子事务。[当前导出顺序](../update_books.py#L89-L113)

### `.github/workflows/update-books.yml`

当前 schedule 是每周一，不是已确认的每日采集；新 Crawl4AI 路径应新建统一每日 workflow，旧 weekly 静态任务在试点期间保留为应急兜底。[当前 schedule](../.github/workflows/update-books.yml#L7-L12)

当前安装浮动版本、使用 Node `npx` 安装浏览器、把所有来源放入同一个 Python 进程并在同一步注入 ZHIPU/Google secrets，随后同 job 直接 git push。应按前述 crawl/validate/import/alert 权限边界拆分。[当前安装与执行](../.github/workflows/update-books.yml#L140-L159)；[当前 push](../.github/workflows/update-books.yml#L161-L169)

## 9. 试点上线检查表

以下条目全部通过后，Hachette/HarperCollins 才能从 Google Books fallback 切为官网主来源：

- [ ] `crawl4ai==0.9.2` 与传递依赖可复现安装；Chromium 由 Python Playwright 对应版本安装；doctor/smoke crawl 通过。[安装依据](https://docs.crawl4ai.com/core/installation/)
- [ ] 全 workflow 只有一个长生命周期 crawler；`arun_many(stream=True)`；最大页面数 2；记录 dispatcher 峰值内存。[并发依据](https://docs.crawl4ai.com/advanced/multi-url-crawling/)
- [ ] `check_robots_txt=True`；robots 禁止、403、验证码、登录墙不会进入任何绕过路径。[robots 依据](https://docs.crawl4ai.com/advanced/advanced-features/#6-robotstxt-compliance)
- [ ] 每来源独立 deterministic schema；正常路径无 LLM；AI attempt/call/token/cost 四重上限生效。[提取依据](https://docs.crawl4ai.com/extraction/no-llm-strategies/)
- [ ] URL 级错误保留 `success/status/error/redirect/dispatch`；空结果、部分分页、字段校验失败均不会导入。[结果依据](https://docs.crawl4ai.com/api/crawl-result/)
- [ ] 出版社批次有稳定 `batch_id`、内容摘要和幂等导入；重试不会重复入库；失败不覆盖上次成功批次。
- [ ] crawl job 没有 write token、`CRON_SECRET` 或不必要 API secret；失败 artifact 保留 7 天。[GitHub 最小权限](https://docs.github.com/actions/how-tos/security-for-github-actions/security-guides/automatic-token-authentication)
- [ ] 403/超时、空列表、结构漂移、AI 不可用、部分失败、重复 batch_id 六类演练全部通过。
- [ ] 连续观察 14 天且至少 10 次计划采集；每来源成功率不低于 90%，不连续失败 3 次，单来源 10 分钟内完成。
- [ ] 自动展示记录必填/ISBN/日期窗口合规率 100%，人工字段准确率至少 95%，官网发现覆盖率至少 90%，无重复作品/预售误入/空批次覆盖。

## 10. 尚需实测的未知项

1. **GitHub Actions 出口是否被出版社拦截。** 官方只能证明 runner 出口来自宽广、变化的 Azure IP 范围；Hachette/HarperCollins 是否允许必须在 scheduled runner 上验证。[GitHub IP 文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#ip-addresses)
2. **每页实际内存与最优并发。** `max_session_permit=2` 是风险控制值；必须以 `dispatch_result.peak_memory` 和 runner 指标验证，不能从官方默认 10 推断 BookRank 可承受 10。[dispatcher 参数](https://docs.crawl4ai.com/advanced/multi-url-crawling/#31-memoryadaptivedispatcher-default)
3. **两家站点的稳定 schema。** 本票没有抓取并保存真实页面 fixture；CSS/XPath/JSON-LD 选择器需要在实现票中用多种页面模板建立 fixture 和漂移测试。
4. **Render import endpoint。** 当前仓库只有“触发 Render 自己同步”的 cron endpoint，没有批次导入、摘要校验或幂等记录；该接口与数据模型必须另开实现票。[当前 cron endpoint](../app/routes/api/cron.py#L62-L87)

## 最终决策

**Go，但只能按受控试点进入实施。** Crawl4AI 本身具备 BookRank 所需的浏览器生命周期、批量并发、robots、确定性提取、LLM 降级和逐 URL 结果模型；真正的生产风险不在“能否打开网页”，而在当前项目的资源编排、robots 旁路、失败语义、空批次覆盖、供应链锁定和 Actions 权限边界。上述四个上线阻断项与检查表未完成前，不应把 Hachette/HarperCollins 切为官网主来源。
