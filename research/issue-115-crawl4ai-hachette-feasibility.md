# Hachette 官网作为 Crawl4AI 新书来源的可行性

> Wayfinder 研究票：[#115](https://github.com/gongyijie85/bookrank/issues/115)
>
> 研究日期：2026-08-09（Asia/Shanghai）
>
> 结论状态：**NO-GO（当前不应将 Hachette 官网启用为生产自动采集源）**

## 结论摘要

Hachette 详情页在纯技术上很适合确定性提取：2026-08-09 对 3 个当期新书页的有限抽样均返回 HTTP 200，每页均有一个 `Product` + `Book` JSON-LD，且 HTML 均有书名、ISBN、作者链接和发售日期。对其中一页的完整 JSON-LD 解析还验证了 `name`、`author`、`isbn`、`datePublished`、`bookFormat`、出版品牌、简介、封面和价格。这些字段应直接解析 JSON-LD，无需 LLM，对当前服务端渲染页面甚至无需启动 Chromium。[抽样 1：The Wound Is Where the Light Enters](https://www.hachettebookgroup.com/titles/chris-young/the-wound-is-where-the-light-enters/9780316565288/)[抽样 2：This Is Fine](https://www.hachettebookgroup.com/titles/kc-green/this-is-fine-life-lessons-for-a-world-on-fire/9798894143156/)[抽样 3：Exhumed](https://www.hachettebookgroup.com/titles/aaron-mahnke/exhumed/9798894141817/)

但整体方案不满足本项目已确定的合规边界：Hachette 的《Terms of Use》第 7 节明确禁止 spidering、screen scraping、database scraping 以及其他自动方式访问服务或取得站点信息；第 2 节只授予个人、非商业的有限使用权。因此，在获得 Hachette 明确书面授权前，不应用 Crawl4AI、requests 或其他自动化工具将官网接入日常生产采集。[Hachette Terms of Use §§2–3, 7](https://www.hachettebookgroup.com/terms-and-policies/terms-of-use/)

即使未来取得授权，当前公开发现入口也不足以独立承担“30 天新书”的权威发现源：首页只返回 24 个 `New Releases` 轮播项，没有下一页 URL 或可验证的全量边界；官方称 HBG 每年约出版 3,000 本书，因而 24 个当时快照不能证明达到项目要求的 90% 发现覆盖率。[Hachette 首页](https://www.hachettebookgroup.com/)[About Hachette Book Group](https://www.hachettebookgroup.com/landing-page/about-hachette-book-group-2/)

**最终建议：**保持当前 Google Books 降级通道，将 Hachette 官网标记为“技术上部分可提取，合规上未获授权，发现覆盖率未证明”。只有在 Hachette 给出自动采集的书面许可，并提供或确认可覆盖全量新书的 feed、ONIX、sitemap 或目录入口后，才进入 14 天试点。

## 研究方法与边界

- 仅使用 Hachette 公开页面与政策、Crawl4AI 官方文档、GitHub 官方文档，以及 BookRank 仓库代码、提交历史和公开 Issue 作为一手证据。
- 对 Hachette 的实时检查限于首页、`robots.txt`、一个官方书单页与 3 个详情页；使用可识别的研究 User-Agent，未登录、未使用代理、未处理验证码、未启用 stealth/undetected 模式，也未执行批量爬取。
- 未从 GitHub-hosted runner 触发实时 Crawl4AI 任务，因此对 GitHub Actions 出口 IP 的结论是风险识别，不是成功性证明。这不影响合规 NO-GO 结论。

## 1. 公开新书发现

### 1.1 首页轮播：可读，但不是可证明的全量目录

2026-08-09 的有限检查对 [Hachette 首页](https://www.hachettebookgroup.com/) 得到 HTTP 200；初始 HTML 中已完整包含 `<section id="new-releases">`、24 个 `.carousel__item` 与 24 个去重后 `/titles/.../{ISBN}/` 链接。轮播元素标记 `auto-paginate="true"`，但该区块没有 `page/N` 或 `?page=N` 链接。这表明 JavaScript 主要管理前端轮播分页，并非从后端继续发现书目。

相同 HTML 快照中还包含桌面日历、闪卡、纸牌和贴纸书等商品，因此“存在 ISBN”或“出现在 New Releases 轮播”不足以单独判定为新书；候选记录仍需格式、出版日期和作品级归并校验。[Hachette 首页](https://www.hachettebookgroup.com/)

当前仓库实现仍先寻找已不存在的 `div[role=tabpanel][aria-label="New Releases"]` 或 `div[data-tab="new-releases"]`，失败时会把整个首页当作新书区域；这会将页面其他区块中的 `/titles/` 链接一并纳入，是 2026-08-07 生产静默失效调查所识别的 DOM 漂移。[当前 HachetteCrawler](../app/services/publisher_crawler/hachette.py#L110-L131)[Issue #112 维护者结论](https://github.com/gongyijie85/bookrank/issues/112#issuecomment-5212971068)

### 1.2 其他公开入口

- [`/tag/new-releases/`](https://www.hachettebookgroup.com/tag/new-releases/) 是内容文章标签归档，其条目是“5 New Books to Check Out”类编辑文章，不是带出版日期边界的书目清单。
- [`/book-list/may-fiction-new-releases/`](https://www.hachettebookgroup.com/book-list/may-fiction-new-releases/) 是按月、按类别策划的编辑书单，页面显式包含 preorder 商品，不等于项目定义的“已出版 30 天内”。
- `robots.txt` 指向的 [`/sitemap.xml`](https://www.hachettebookgroup.com/sitemap.xml) 在 2026-08-09 有限检查中返回 HTTP 404，因此当日不能作为可用的发现入口。

**发现结论：**公开页面足以提供少量候选 URL，但目前没有找到能证明全量、可按日期翻页、且可稳定复现的 HBG 集团级新书目录。因此在技术层面也暂不满足 90% 发现覆盖率门槛。

## 2. 分页与动态行为

| 入口 | 初始 HTML | 分页/动态行为 | Crawl4AI 必要性 | 证据 |
|---|---|---|---|---|
| HBG 首页 `#new-releases` | 服务端已返回 24 个候选 | `ai-carousel` 的 `auto-paginate` 是视图级分页；无后续页 URL | 对这 24 项不必要 | [HBG 首页](https://www.hachettebookgroup.com/) |
| 编辑书单 | 书名、作者、价格、格式和预购日期已在 HTML | 当前抽样无后续页 | 不必要 | [May Fiction New Releases](https://www.hachettebookgroup.com/book-list/may-fiction-new-releases/) |
| 详情页 | JSON-LD 已在 HTML | 核心书目字段不依赖交互 | 不必要 | [详情页抽样](https://www.hachettebookgroup.com/titles/chris-young/the-wound-is-where-the-light-enters/9780316565288/) |

Crawl4AI 确实支持用 `wait_for`、`js_code` 或 `c4a_script` 处理“Load More”和动态内容，但这些能力不会把一个只暴露 24 项的轮播变成可证明的全量目录，也不会改变站点使用条款。[Crawl4AI Browser/Crawler Configuration](https://docs.crawl4ai.com/core/browser-crawler-config/)

## 3. 结构化数据与字段可得性

### 3.1 详情页 JSON-LD

3 个当期详情页抽样均有一个 JSON-LD 对象，`@type` 为 `Product` 与 `Book` 的组合；每个 HTML 均包含 URL 中的 ISBN、书名 H1、作者 contributor 链接和 `On Sale` 日期。详情如下：

| 抽样 | HTTP | `Product` + `Book` JSON-LD | ISBN 在 HTML | 作者链接 | `On Sale` | 证据 |
|---|---:|---|---|---|---|---|
| The Wound Is Where the Light Enters | 200 | 有 | 9780316565288 | 3 个 | 2026-08-04 | [Hachette](https://www.hachettebookgroup.com/titles/chris-young/the-wound-is-where-the-light-enters/9780316565288/) |
| This Is Fine: Life Lessons for a World on Fire | 200 | 有 | 9798894143156 | 3 个 | 2026-08-04 | [Hachette](https://www.hachettebookgroup.com/titles/kc-green/this-is-fine-life-lessons-for-a-world-on-fire/9798894143156/) |
| Exhumed | 200 | 有 | 9798894141817 | 1 个 | 2026-08-04 | [Hachette](https://www.hachettebookgroup.com/titles/aaron-mahnke/exhumed/9798894141817/) |

第一个样本的 JSON-LD 完整解析值为：`name = The Wound Is Where the Light Enters`、`author[0].name = Chris Young`、`isbn = sku = 9780316565288`、`datePublished = 2026-08-04`、`bookFormat = Hardcover`；该对象还包含 `image`、`description`、`brand`、`offers`、`publisher`、`genre` 和 `numberOfPages`。[样本 JSON-LD 来源页](https://www.hachettebookgroup.com/titles/chris-young/the-wound-is-where-the-light-enters/9780316565288/)

### 3.2 主版本和新书时间窗口

Hachette 详情 URL 和 JSON-LD 是“版本级”的：同一作品可在页面上列出 Hardcover、ebook、Audiobook 和 Large Print 等多个格式，每个格式可指向不同 ISBN。[多格式官方书单页](https://www.hachettebookgroup.com/book-list/may-fiction-new-releases/) 因此，即使获得授权，也应将 `isbn + bookFormat + datePublished` 视为版本证据，按项目规则选纸质首发主版本，再在作品级展示去重。

官方书单页明确包含尚未发售的 preorder，所以不能用列表标题中的“New Releases”代替日期校验；只能在 `datePublished <= 采集日期` 且落在 30 天窗口时自动展示。[May Fiction New Releases](https://www.hachettebookgroup.com/book-list/may-fiction-new-releases/)

### 3.3 AI 的边界

这一数据源的已知详情页是高度结构化的，Crawl4AI 官方也建议对结构化页面优先使用 CSS/XPath/Regex 策略，而不是默认 LLM 提取。[Crawl4AI LLM-free extraction](https://docs.crawl4ai.com/extraction/no-llm-strategies/)[Crawl4AI LLM extraction](https://docs.crawl4ai.com/extraction/llm-strategies/) 本源应更进一步：直接解析 Hachette 自己发布的 JSON-LD，对 ISBN 和日期做确定性校验。AI 最多用于已授权场景下的离线漂移诊断或生成候选规则，不应逐书调用，也不能生成缺失的 ISBN/出版日期。

## 4. 合规评估

### 4.1 robots.txt

2026-08-09 直接读取 [`https://www.hachettebookgroup.com/robots.txt`](https://www.hachettebookgroup.com/robots.txt) 返回 HTTP 200，内容对 `User-agent: *` 仅声明 `Disallow: /wp-admin/`，并允许 `/wp-admin/admin-ajax.php`；文件同时宣告了当日返回 404 的 `/sitemap.xml`。从 robots 机器协议角度，公开首页和 `/titles/` 路径未被 `Disallow`。

### 4.2 Terms of Use

robots.txt 没有禁止路径不等于授予自动采集许可。Hachette 《Terms of Use》对这一点更明确：

- 第 2 节的许可限于个人、非商业使用；第 3 节另外禁止未经明示书面同意的商业下载、复制、发布或开发利用。
- 第 7 节禁止 spidering、screen scraping、database scraping 和其他自动访问或取得站点信息的方式；同节也禁止试图绕过或干扰服务。
- 第 9 和第 19 节保留限制或终止访问的权利。

上述条款均来自 [Hachette Terms of Use（最后更新 2023-11-01）](https://www.hachettebookgroup.com/terms-and-policies/terms-of-use/)。HBG 页脚还说明站点部分数据由 Books In Print 提供，书籍图像权利由原权利人保留，所以即使未来获得技术访问许可，仍应另行确认封面、简介与第三方书目数据的可用范围。[Hachette 页脚权利声明](https://www.hachettebookgroup.com/landing-page/read-our-world/)

**合规判定：**robots 路径规则虽未禁止公开书页，但站点使用条款明确禁止本项目计划的自动采集方式。按本 Wayfinder 地图的“不绕过条款/验证码/明确反自动化要求”决策，这是独立的上线阻断项。本文是工程合规建议，不是法律意见。

## 5. GitHub Actions + Crawl4AI 风险

| 风险 | 证据 | 影响 | 处置 |
|---|---|---|---|
| 使用条款禁止自动采集 | [Hachette Terms of Use §7](https://www.hachettebookgroup.com/terms-and-policies/terms-of-use/) | **Critical / 上线阻断** | 不运行；先取得书面授权 |
| GitHub-hosted runner 没有稳定单一出口 IP | GitHub 说明标准 Windows/Ubuntu runner 使用 Azure 地址段，地址段很多且每周更新；如需固定地址，建议 larger runner 或 self-hosted runner。[GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#ip-addresses) | 即使获授权，共享云 IP 也可能收到与本地不同的 403/挑战页；本地 HTTP 200 不能代表 Actions 成功 | 授权后先做 runner 预检；若被拦截，请 Hachette 配置授权访问或改用授权 feed，不使用代理/stealth 绕过 |
| 项目已有静默失效记录 | Issue #112 记录 Hachette 站点路径自 2026-06-22 起生产零入库，本地却仍可取得 24 个链接，维护者判断为出口环境所得页面不同。[Issue #112](https://github.com/gongyijie85/bookrank/issues/112)[维护者结论](https://github.com/gongyijie85/bookrank/issues/112#issuecomment-5212971068) | 仅检查进程成功会漏掉“结果为空”的数据故障 | 空批次必须失败，保留上次成功数据，连续 3 次失败告警 |
| Crawl4AI/浏览器安装不可复现 | 当前 workflow 使用未锁版的 `pip install crawl4ai`，随后运行 `npx playwright install --with-deps chromium`。[update-books.yml](../.github/workflows/update-books.yml#L139-L151) Crawl4AI 官方安装文档要求安装后运行 `crawl4ai-setup`，并可用 `crawl4ai-doctor` 验证。[Crawl4AI Installation](https://docs.crawl4ai.com/core/installation/) | 新版破坏性变更、Python/Node Playwright 浏览器不匹配可使任务在运行时失败 | 锁定经验证的 Crawl4AI 版本，用官方 setup + doctor，再运行一页 smoke test |
| 当前 Crawl4AI 封装频繁重启浏览器 | `_crawl_with_crawl4ai_async()` 每个 URL 都新建一个 `AsyncWebCrawler`，只返回 `result.html` 再交给 BeautifulSoup。[mixed_crawl4ai_crawler.py](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L90-L115) | 24+ 详情页会反复启停 Chromium，增加时间、内存和页面泄漏风险；也未利用结构化提取 | 授权后复用一个 crawler session，用 `arun_many()` + dispatcher 限制最多 2 个并发页，直接消费结构化结果。[Crawl4AI Multi-URL Crawling](https://docs.crawl4ai.com/advanced/multi-url-crawling/) |

当前生产配置已经将历史 `HachetteCrawler` 迁移到 `HachetteGoogleCrawler`，仓库注释明确关联 Issue #112 的生产失效。[publisher_data.py](../app/services/publisher_data.py#L135-L140) 因此本研究不建议把它切回官网路径。

## 6. 可行性判定

| 维度 | 判定 | 理由 |
|---|---|---|
| 公开候选发现 | **部分可行** | 首页有 24 个服务端渲染的当期链接，但无全量边界或翻页。 |
| 字段提取 | **可行** | 抽样详情页 JSON-LD 提供必填字段和版本格式。 |
| 30 天发现覆盖率 ≥ 90% | **未证明 / 暂不可行** | 24 项快照与编辑书单都不是可审计的集团全量目录。 |
| 无 AI 日常提取 | **可行** | JSON-LD 比 LLM 更精确、可重复、低成本。 |
| GitHub Actions 稳定性 | **未证明 / 高风险** | 未在 runner 上实测，出口 IP 不固定，项目已有环境差异导致静默空结果的记录。 |
| 合规 | **不可行** | 现行 Terms of Use 明确禁止计划中的自动采集方式。 |
| **总体** | **NO-GO** | 合规项单独足以阻止上线；发现覆盖率也尚未达标。 |

## 7. 后续建议

### 现在可以做

1. **维持 `HachetteGoogleCrawler` 为主/降级通道。** 它已是当前配置的路径，不要因本次详情页抽样成功就切回官网。[publisher_data.py](../app/services/publisher_data.py#L45-L55)[Issue #112 部署验证](https://github.com/gongyijie85/bookrank/issues/112#issuecomment-5212971068)
2. **向 Hachette 请求书面许可和完整目录通道。** 请求内容应同时覆盖：自动访问许可、允许的频率/User-Agent/IP、可使用的字段与封面/简介范围，以及可审计的全量新书 feed/ONIX/sitemap/catalog。Hachette 的 Terms and Policies 页面对材料使用许可问题提供了 `consumersupport@hbgusa.com` 联系方式。[Terms and Policies](https://www.hachettebookgroup.com/terms-and-policies/)
3. **将当前 DOM 与 JSON-LD 观察仅作为设计证据，不定时运行官网 crawler。** 不用代理、指纹伪装、stealth/undetected browser 或验证码服务规避限制。

### 仅在获得书面授权后进行

1. **先验证发现源，再实现详情提取。** 首选 Hachette 授权的全量目录或 feed；首页 24 项只能作为增量线索，不是完整性根据。
2. **详情页直接解析 JSON-LD。** 必填 `name`、`author`、`isbn`、`datePublished`、`bookFormat`、官网 URL；ISBN-13 要做 checksum，日期要通过 30 天窗口，屏蔽预售和非书商品。
3. **只在确实需要浏览器时用 Crawl4AI。** 复用一个 `AsyncWebCrawler`，用 `arun_many()` 和 dispatcher 将同时页面数限制为 2，设置 1–2 秒请求间隔与 429/503 退避。Crawl4AI 官方 dispatcher 提供并发、内存阈值和速率限制。[Crawl4AI Multi-URL Crawling](https://docs.crawl4ai.com/advanced/multi-url-crawling/)
4. **正常路径不调用 LLM。** 仅在 schema 漂移时生成候选规则；候选规则必须经固定 fixture 和人工确认后才能启用。
5. **先做 GitHub Actions 预检和故障演练。** 锁定 Crawl4AI 版本，执行 setup/doctor/smoke test，覆盖 403/429、超时、空列表、结构漂移和部分失败；空批次绝不覆盖上次成功数据。
6. **通过已定验收门槛后才切换。** 连续 14 天/至少 10 次计划采集，人工核验至少 30 条，必填字段与时间窗口 100% 合规，样本字段准确率 ≥ 95%，对授权全量目录的发现覆盖率 ≥ 90%，且无空批次覆盖、重复作品或预售误入。

## 证据索引

### Hachette 一手来源

- [Hachette 首页](https://www.hachettebookgroup.com/)
- [robots.txt](https://www.hachettebookgroup.com/robots.txt)
- [Terms of Use](https://www.hachettebookgroup.com/terms-and-policies/terms-of-use/)
- [Terms and Policies](https://www.hachettebookgroup.com/terms-and-policies/)
- [About Hachette Book Group](https://www.hachettebookgroup.com/landing-page/about-hachette-book-group-2/)
- [New Releases 标签页](https://www.hachettebookgroup.com/tag/new-releases/)
- [May Fiction New Releases](https://www.hachettebookgroup.com/book-list/may-fiction-new-releases/)
- [详情页抽样 1](https://www.hachettebookgroup.com/titles/chris-young/the-wound-is-where-the-light-enters/9780316565288/)
- [详情页抽样 2](https://www.hachettebookgroup.com/titles/kc-green/this-is-fine-life-lessons-for-a-world-on-fire/9798894143156/)
- [详情页抽样 3](https://www.hachettebookgroup.com/titles/aaron-mahnke/exhumed/9798894141817/)

### Crawl4AI / GitHub 官方来源

- [Crawl4AI Installation](https://docs.crawl4ai.com/core/installation/)
- [Crawl4AI Browser, Crawler & LLM Configuration](https://docs.crawl4ai.com/core/browser-crawler-config/)
- [Crawl4AI LLM-free extraction](https://docs.crawl4ai.com/extraction/no-llm-strategies/)
- [Crawl4AI LLM extraction](https://docs.crawl4ai.com/extraction/llm-strategies/)
- [Crawl4AI Multi-URL Crawling](https://docs.crawl4ai.com/advanced/multi-url-crawling/)
- [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

### BookRank 仓库一手证据

- [Issue #115](https://github.com/gongyijie85/bookrank/issues/115)
- [Issue #112](https://github.com/gongyijie85/bookrank/issues/112)
- [HachetteCrawler](../app/services/publisher_crawler/hachette.py)
- [MixedCrawl4AICrawler](../app/services/publisher_crawler/mixed_crawl4ai_crawler.py)
- [出版社路径与迁移映射](../app/services/publisher_data.py)
- [update-books workflow](../.github/workflows/update-books.yml)
- [2026-08-07 切回 Google Books 的提交](https://github.com/gongyijie85/bookrank/commit/1c1b987c)
- [2026-04-28 记录 Cloudflare 403/Playwright 失败的提交](https://github.com/gongyijie85/bookrank/commit/e4a6361f966060346ded440999c72395aa42ee10)
