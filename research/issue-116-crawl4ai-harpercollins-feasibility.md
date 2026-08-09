# HarperCollins 官网作为 Crawl4AI 采集来源的可行性

- 对应工单：[BookRank #116](https://github.com/gongyijie85/bookrank/issues/116)
- 调研日期：2026-08-09（Asia/Shanghai）
- 研究范围：HarperCollins 美国公开官网、新书发现与详情字段、Crawl4AI/GitHub Actions 运行风险及合规边界
- 证据口径：只使用 HarperCollins/Shopify 公开页面、Crawl4AI 官方文档与源码仓库、BookRank 仓库代码和历史工单

## 结论

**结论是“技术上适合做受控试点，但当前不适合作为生产主来源”。** HarperCollins 当前提供可公开访问的新书集合页、集合 Atom feed 和 Shopify 产品 JSON；因此产品发现、标题和分版本 ISBN 不必先依赖 LLM，甚至多数步骤不必依赖浏览器。[新书集合](https://www.harpercollins.com/collections/new-releases) [Atom feed](https://www.harpercollins.com/collections/new-releases.atom) [产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js)

阻止其直接成为主来源的有两个硬条件：

1. 公开产品 JSON 没有明确的图书 `On Sale`/出版日期字段，作者也没有独立字段；而 BookRank 的自动展示资格要求可靠 ISBN-13、作者和 30 天出版窗口。产品 HTML 虽预留 `selected_variant.publish_date`，但本次从当前运行环境访问详情 HTML 时触发了 Cloudflare managed challenge，无法证明该字段可在 GitHub Actions 中稳定取得。[产品页](https://www.harpercollins.com/products/whistler-ann-patchett) [BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)
2. `robots.txt` 目前明确允许抓取公开产品、集合和页面，但 HarperCollins 使用条款仍将站内材料授权限制为个人、非商业用途，并禁止未经事先书面同意的复制、发布或传输。公开 BookRank 服务不能把 robots 许可等同于内容再发布许可；上线前应获得站方许可或完成针对“只保存事实型书目字段和源链接”的合规审查，封面与简介尤其不能默认再发布。本报告不是法律意见。[robots.txt](https://www.harpercollins.com/robots.txt) [HarperCollins Terms of Use](https://www.harpercollins.com/pages/terms-of-use)

因此建议维持 `HarperCollinsGoogleCrawler` 为主通道，以官网路径作为**关闭写库的观察性试点/候选补充源**。只有在 14 天试点同时通过访问稳定性、出版日期完整性、字段准确率和合规门槛后，才用来源开关将官网提升为主来源；任何阶段都不使用代理、隐身模式或验证码绕过。[当前生产映射](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/app/services/publisher_data.py#L57-L61) [切回 Google Books 的提交](https://github.com/gongyijie85/bookrank/commit/1c1b987c8437b246af3cef92e42811366745d679)

## 逐项判断

| 问题 | 证据 | 判断 |
| --- | --- | --- |
| 是否有公开新书入口 | 网站导航的当前入口是 `/collections/new-releases`，页面还声明了 `/collections/new-releases.atom`。[集合页](https://www.harpercollins.com/collections/new-releases) [Atom feed](https://www.harpercollins.com/collections/new-releases.atom) | 有。优先使用 Atom 做低成本发现，集合页做覆盖率补充。 |
| 列表是否静态 | 集合 HTML 中的命中容器最初为空，HarperCollins 自有脚本在集合页启用 Algolia InstantSearch，以 `collection_ids` 过滤，并挂载分页组件。[初始化脚本](https://www.harpercollins.com/cdn/shop/t/8/assets/algolia_init.js?v=23687443935956485311591137123) [搜索脚本](https://www.harpercollins.com/cdn/shop/t/8/assets/algolia_instant_search.js?v=169201758373227979831772646031) | 是动态列表；抓完整集合需等待 JS 命中元素并遍历分页。 |
| 每页与分页方式 | 官方前端配置将集合每页命中数设为 16；InstantSearch 使用分页 widget，并把集合 ID 放入过滤条件。[配置脚本](https://www.harpercollins.com/cdn/shop/t/8/assets/algolia_config.js?v=140709743369170977321745508043) [搜索脚本](https://www.harpercollins.com/cdn/shop/t/8/assets/algolia_instant_search.js?v=169201758373227979831772646031) | 不能把首屏或首页轮播视为全集。分页 URL/交互应在试点中从实际渲染 DOM 验证，不应先猜查询参数。 |
| 是否有无需浏览器的发现入口 | 2026-08-09 实测 Atom 返回 HTTP 200、25 个条目；`?page=2` 返回了与第一页相同的首尾产品 ID，且 feed 没有 next link。[Atom feed](https://www.harpercollins.com/collections/new-releases.atom) | 可发现最近一批产品，但不能据此证明达到全量或 90% 覆盖率；必须与渲染集合对账。 |
| 集合 JSON-LD | 2026-08-09 实测集合 HTML 只有一个 `application/ld+json`，内容类型为 `Organization`，没有书目列表。[集合页](https://www.harpercollins.com/collections/new-releases) | JSON-LD 不能承担列表提取。 |
| 产品结构化数据 | 公开的 `/{handle}.js` 返回标题、描述、vendor、formats、SKU/barcode、图片和价格；同一作品可含 Hardcover、Large Print、E-book、Digital Audiobook 多个 ISBN。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js) | 标题和版本 ISBN 可确定性提取；适合实现作品级卡片与版本保留。 |
| 作者 | 产品 JSON 样例没有独立 `author` 字段；当前样例的封面 `alt` 为 `Whistler by Ann Patchett (ISBN)`，handle 也含作者。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js) | 当前可从 `alt` 得到作者，但它只是样例格式，不足以作为 100% 必填字段保证；缺失时必须补全或待验，不能让 LLM猜测。 |
| ISBN | 产品 JSON 的每个 variant 同时有 `sku` 与 `barcode`；当前样例二者均为有效 ISBN-13。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js) | 可用，但需 ISBN-13 校验，并按纸质首发主版本规则选主 ISBN，其他 ISBN 保留为版本。 |
| 出版日期 | 产品 JSON 只有 `published_at`/`created_at`，没有名为 `On Sale` 或图书出版日期的字段；产品 HTML 模板显示真正字段来自 `selected_variant.publish_date`。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js) [产品页](https://www.harpercollins.com/products/whistler-ann-patchett) | 不能把 Shopify `published_at` 直接当作图书出版日期。详情渲染或另一官方目录接口必须提供并验证 `On Sale`，否则官网记录没有自动展示资格。 |
| Cloudflare | 2026-08-09 同一环境中，集合 HTML、Atom 和产品 `.js` 返回 200；产品 HTML 返回 Cloudflare managed challenge，`agents.md` 与旧 RSS 地址返回 403。响应均由 Cloudflare 提供。[集合页](https://www.harpercollins.com/collections/new-releases) [产品页](https://www.harpercollins.com/products/whistler-ann-patchett) [产品 JSON](https://www.harpercollins.com/products/whistler-ann-patchett.js) [agents.md](https://www.harpercollins.com/agents.md) | 风险是路径级、客户端/IP 相关，不能用“一次可访问”推出 GitHub Actions 稳定。结构化轻量端点比详情 HTML 更可靠，但也必须监测。 |
| 历史生产证据 | 工单 #112 记录：HarperCollins 站点路径在生产自 2026-06-22 起零入库，100 条存量普遍缺日期；修复提交因此切回 Google Books。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112) [修复提交](https://github.com/gongyijie85/bookrank/commit/1c1b987c8437b246af3cef92e42811366745d679) | 当前已有“任务显示成功但实际零新增”的静默失效先例，空批次保护和来源级监控是上线必需条件。 |

## 公开发现路径

### 1. 当前规范入口是 collection，不是旧 page

HarperCollins 当前导航把 “New Releases” 指向 `https://www.harpercollins.com/collections/new-releases`；BookRank 旧调研中的 `/pages/new-releases` 不是本次官网导航给出的入口。[HarperCollins 新书集合](https://www.harpercollins.com/collections/new-releases)

集合的首个 200 HTML 响应约 272 KB，但产品命中容器由 Algolia InstantSearch 在浏览器端填充。官方配置启用 collection instant search、设置 16 条/页；官方搜索脚本按当前 collection ID 构造过滤并渲染 pagination widget。[配置脚本](https://www.harpercollins.com/cdn/shop/t/8/assets/algolia_config.js?v=140709743369170977321745508043) [搜索脚本](https://www.harpercollins.com/cdn/shop/t/8/assets/algolia_instant_search.js?v=169201758373227979831772646031)

这解释了为什么只用 `requests` 或从未等待动态 DOM 的解析器会得到标题页却没有产品，也解释了为什么现有“从首页 NEW RELEASES 轮播读取约 16 本”的爬虫不具备集合覆盖率。[现有 HarperCollins 爬虫](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/app/services/publisher_crawler/harpercollins.py#L1-L11)

### 2. Atom 是优先发现入口，但不是完整性证明

集合 HTML 公开声明 Atom feed。2026-08-09 的响应包含 25 个 entry，每个 entry 有产品标题、产品 URL、vendor、简介 HTML、图片、格式及 SKU；例如 `s:variant` 可直接给出 `Hardcover` 与 ISBN-13。[Atom feed](https://www.harpercollins.com/collections/new-releases.atom)

Feed 的 `published`/`updated` 与 Shopify 产品 entry 的更新时间一致，产品 `.js` 也把相近字段命名为 `published_at`/`created_at`；这些字段不是官网详情模板中名为 `On Sale` 的字段，因此不得直接用于 BookRank 的 30 天出版窗口。[Atom feed](https://www.harpercollins.com/collections/new-releases.atom) [产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js) [产品页模板](https://www.harpercollins.com/products/whistler-ann-patchett)

本次对 `?page=2` 的只读请求仍返回与第一页相同的 25 个条目，并且 feed 未声明 `rel=next`；所以把 Atom 定位为“候选发现/变更提示”而非全量目录。覆盖率应以浏览器渲染后的 collection 分页结果为基准对账。[Atom feed](https://www.harpercollins.com/collections/new-releases.atom)

### 3. UCP/MCP 是值得单独验证的官方替代

当前 `robots.txt` 不仅声明公开 HTML 可抓，还要求 agents 优先使用 UCP/MCP 做 catalog、cart 和 checkout；`/.well-known/ucp` 的 2026-04-08 discovery 文档声明 `catalog.search` 与 `catalog.lookup` capability，并公布 MCP endpoint。[robots.txt](https://www.harpercollins.com/robots.txt) [UCP discovery](https://www.harpercollins.com/.well-known/ucp)

本次只读 GET MCP endpoint 得到 403；GET 并不是 MCP 方法调用，因此这只能证明“尚未验证”，不能证明 catalog capability 不可用。后续应另开研究票按其官方 OpenRPC/schema 做只读 `catalog.search`/`catalog.lookup` 验证；若它能稳定给出作者和 `On Sale`，优先级应高于 Crawl4AI。[UCP discovery](https://www.harpercollins.com/.well-known/ucp) [MCP endpoint](https://harpercollins-us.myshopify.com/api/ucp/mcp)

## 字段提取设计

建议的数据路径如下：

1. 从 Atom 收集候选产品 URL，并保存 entry 更新时间，只把它当作发现时间。[Atom feed](https://www.harpercollins.com/collections/new-releases.atom)
2. 渲染 collection，等待 Algolia 产品命中元素，遍历全部分页；用 canonical product URL 去重，并与 Atom 对账。[集合页](https://www.harpercollins.com/collections/new-releases) [Crawl4AI 页面交互](https://docs.crawl4ai.com/core/page-interaction/)
3. 优先请求每个产品 `/{handle}.js`，确定性提取 title、description、variants、SKU/barcode、format 和 cover；不要为了这些字段启动浏览器。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js)
4. 作者只接受独立官网字段、严格 `alt` 格式或可信补全源；ISBN 用校验算法验证。选择纸质主版本用于作品卡片，其他载体 ISBN 保存为关联版本。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js)
5. 仅为缺失的 `On Sale` 尝试详情页普通浏览器渲染；一旦出现 403、验证码或 challenge，立即终止该来源的详情抓取，记录失败并回退，不启用 stealth、代理轮换或模拟绕过。[产品页](https://www.harpercollins.com/products/whistler-ann-patchett) [HarperCollins Terms of Use](https://www.harpercollins.com/pages/terms-of-use)
6. AI 只可在模板未知时生成**候选选择器/候选数据**；常规提取使用 CSS/XPath/JSON。Crawl4AI 官方也建议结构化页面先使用 `JsonCssExtractionStrategy`/`JsonXPathExtractionStrategy`，并指出 LLM 路径更慢、更贵且输出需要验证。[Crawl4AI 无 LLM 提取](https://docs.crawl4ai.com/extraction/no-llm-strategies/) [Crawl4AI LLM 提取](https://docs.crawl4ai.com/extraction/llm-strategies/)

### 自动发布最小字段

一条官网候选只有同时满足以下条件才有自动展示资格：非空 title、至少一名可信 author、publisher、canonical source URL、有效 ISBN-13，以及经验证落在既定 30 天窗口的真实 `On Sale`/publication date。当前公开产品 JSON 只能稳定覆盖其中一部分，所以默认应进入候选批次，而不是直接写入展示库。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js) [BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

## Cloudflare、robots 与使用条款

### robots

2026-08-09 获取到的 `robots.txt` 返回 HTTP 200、`text/plain`，并明确写出公开 product、collection、page、blog、policy 和本地化 HTML 可抓取；规则允许 `/`，同时禁止 checkout、orders、account、内部 services、部分 AJAX、排序和复合过滤陷阱。[robots.txt](https://www.harpercollins.com/robots.txt)

实现应启用 `CrawlerRunConfig(check_robots_txt=True)`，并在每批开始时重新检查规则。Crawl4AI 官方变更记录说明该参数会在抓取前检查 robots，并把 robots 拒绝表现为 403 结果。[Crawl4AI CHANGELOG](https://github.com/unclecode/crawl4ai/blob/v0.9.2/CHANGELOG.md)

现有 `HarperCollinsCrawler._is_url_allowed()` 无条件返回 `True`，其注释仍假设 robots 永远被 Cloudflare 拦截；该假设已与 2026-08-09 的 200 文本响应不符，试点实现不能复用这个绕过。[现有 HarperCollins 爬虫](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/app/services/publisher_crawler/harpercollins.py#L65-L77)

### 使用条款

HarperCollins 条款称网站材料主要归 HCP 或第三方权利人所有，只授权个人、非商业查看/下载，并明确禁止未经事先书面同意的复制、发布和传输。[HarperCollins Terms of Use](https://www.harpercollins.com/pages/terms-of-use)

因此：

- robots 允许访问，不等于允许把封面、简介或其他材料重新发布到 BookRank。[robots.txt](https://www.harpercollins.com/robots.txt) [Terms of Use](https://www.harpercollins.com/pages/terms-of-use)
- 试点只保存验证所需的最小事实型字段、状态码、选择器结果和源 URL；失败页面作为私有短期 artifact，不提交整页副本。[Terms of Use](https://www.harpercollins.com/pages/terms-of-use)
- 若没有书面许可或合规确认，官网结果不得升级成公开生产主来源，尤其不得复制封面和简介。[Terms of Use](https://www.harpercollins.com/pages/terms-of-use)

### Cloudflare 实测矩阵

以下为 2026-08-09 同一 Windows 运行环境、普通 `Invoke-WebRequest`、无代理/无挑战绕过的只读观测；它只描述本次路径，不保证未来状态：

| 路径 | 结果 | 可复现 URL |
| --- | --- | --- |
| `robots.txt` | 200，`text/plain`，Server=cloudflare | [robots.txt](https://www.harpercollins.com/robots.txt) |
| 新书 collection HTML | 200，HTML 约 272 KB，无 challenge 标记 | [collection](https://www.harpercollins.com/collections/new-releases) |
| collection Atom | 200，25 entries | [Atom](https://www.harpercollins.com/collections/new-releases.atom) |
| Whistler 产品 `.js` | 200，约 11 KB JSON/JavaScript | [product.js](https://www.harpercollins.com/products/whistler-ann-patchett.js) |
| Whistler 产品 HTML | managed challenge；普通请求未取得详情 | [product HTML](https://www.harpercollins.com/products/whistler-ann-patchett) |
| `agents.md` | 403 | [agents.md](https://www.harpercollins.com/agents.md) |
| 旧 `/feeds/new-releases.rss` | 403；当前 collection 自声明的是 Atom，不是该 RSS | [旧 RSS](https://www.harpercollins.com/feeds/new-releases.rss) [collection](https://www.harpercollins.com/collections/new-releases) |

该矩阵与 BookRank #112 的生产证据方向一致：同一站点不同客户端/IP 可能得到不同页面或挑战，且“同步任务完成”不代表有效数据入库。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

## GitHub Actions + Crawl4AI 方案与风险

### 当前工程差距

当前 workflow 每次执行 `pip install crawl4ai`，没有固定版本；随后用 `npx playwright install --with-deps chromium` 安装浏览器。[当前 workflow](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/.github/workflows/update-books.yml#L140-L159)

Crawl4AI 官方当前 latest release 是 v0.9.2（2026-07-15）；官方 README 推荐 `crawl4ai-setup`，浏览器故障时使用 `python -m playwright install --with-deps chromium`。[v0.9.2 release](https://github.com/unclecode/crawl4ai/releases/tag/v0.9.2) [官方 README](https://github.com/unclecode/crawl4ai/tree/v0.9.2#-quick-start)

因此试点应至少：

```text
pip install crawl4ai==0.9.2
crawl4ai-setup
# 或按官方说明：python -m playwright install --with-deps chromium
```

版本固定是为了让选择器、浏览器修订和失败证据可复现，不代表 v0.9.2 可以绕过 Cloudflare。[v0.9.2 release](https://github.com/unclecode/crawl4ai/releases/tag/v0.9.2) [官方 README](https://github.com/unclecode/crawl4ai/tree/v0.9.2#-quick-start)

当前 `MixedCrawl4AICrawler` 为每个 URL 新建一个 `AsyncWebCrawler`，只返回 `result.html` 再交给 BeautifulSoup；它没有使用 `wait_for`、结构化 `extracted_content` 或批量 dispatcher。[当前混合爬虫](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/app/services/publisher_crawler/mixed_crawl4ai_crawler.py#L90-L155)

Crawl4AI 官方建议创建一个 `AsyncWebCrawler` 后多次调用 `arun`；批量抓取可用 `arun_many` 和 dispatcher 控制并发、限速与内存，动态页面可用 `wait_for` 等待 CSS/JS 条件。[AsyncWebCrawler](https://docs.crawl4ai.com/api/async-webcrawler/) [`arun_many`](https://docs.crawl4ai.com/api/arun_many/) [CrawlerRunConfig](https://docs.crawl4ai.com/core/browser-crawler-config/)

### 试点配置原则

- 单个来源复用一个普通 headless `AsyncWebCrawler`；详情页并发从 1 开始，最多 2 个页面，配置限速与明确超时。[AsyncWebCrawler](https://docs.crawl4ai.com/api/async-webcrawler/) [`arun_many`](https://docs.crawl4ai.com/api/arun_many/)
- collection 使用 `wait_for="css:..."` 等待真实产品 hit，再确定性提取 canonical URL；只有观察实际 DOM 后才能固化 selector。[CrawlerRunConfig](https://docs.crawl4ai.com/core/browser-crawler-config/) [collection](https://www.harpercollins.com/collections/new-releases)
- 开启 `check_robots_txt=True`；不配置 proxy、stealth、`magic` 或模拟绕过。遇到 challenge 立即标记来源失败并回退。[Crawl4AI CHANGELOG](https://github.com/unclecode/crawl4ai/blob/v0.9.2/CHANGELOG.md) [robots.txt](https://www.harpercollins.com/robots.txt)
- 正常路径使用 Atom + 产品 JSON + CSS/XPath；LLM 每来源每批最多一次模板级候选，不逐书调用。[Crawl4AI 无 LLM 提取](https://docs.crawl4ai.com/extraction/no-llm-strategies/) [Crawl4AI LLM 提取](https://docs.crawl4ai.com/extraction/llm-strategies/)
- 每个结果同时检查 HTTP status、最终 URL、`result.success`、challenge 标记、命中数和必填字段；“HTTP 200 但 0 本”必须算失败。[`arun_many` 结果处理](https://docs.crawl4ai.com/api/arun_many/) [BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

### GitHub Actions 特有风险

1. **出口 IP/浏览器指纹不可控。** 本地同一域不同路径已经出现 200 与 managed challenge，生产历史又出现 Render IP 返回不同页面；GitHub 托管 runner 也必须按独立环境实测，不能从开发机结果外推。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112) [产品页](https://www.harpercollins.com/products/whistler-ann-patchett)
2. **依赖漂移。** 当前 job 既不固定 Crawl4AI，也不记录 `npx` 实际解析到的 Playwright 版本；因此本次调研无法验证所装 Chromium 是否与 Python Playwright 的期望修订一致。应改用 Crawl4AI 官方记录的 Python 安装路径并锁版本。[当前 workflow](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/.github/workflows/update-books.yml#L140-L148) [官方 README](https://github.com/unclecode/crawl4ai/tree/v0.9.2#-quick-start)
3. **资源放大。** 当前 `update_books.py` 对出版社使用与来源数相同的线程池；如果多个线程各自启动 Chromium，内存与目标站并发都会放大。[当前 update_books.py](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/update_books.py#L74-L80) [`arun_many`](https://docs.crawl4ai.com/api/arun_many/)
4. **静默空结果。** #112 已证明同步成功时间戳可掩盖零新增；来源批次必须原子化，空结果不得覆盖上次成功状态。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

## 建议试点与 Go/No-Go 门槛

试点应为独立、无写库的手动 GitHub Actions job：只访问 robots、Atom、collection 和最多 5 个产品；使用普通 headless Chromium、并发 1、无代理、无 stealth。保存状态码、最终 URL、耗时、命中数、字段完整率和 challenge 分类，失败 HTML/截图作为私有 artifact 最多保留 7 天，不提交官网整页。[robots.txt](https://www.harpercollins.com/robots.txt) [Terms of Use](https://www.harpercollins.com/pages/terms-of-use)

连续观察 14 个自然日且至少 10 次计划运行；每次将 Atom、渲染 collection 与产品 JSON 对账。至少人工核验 30 条，不足 30 条则全量核验。该设计针对现有静默失效先例，不以单次成功作为上线证据。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

**Go 条件（全部满足）：**

- 获得站方许可或合规审查明确允许拟保存/展示的字段；公开封面和简介需单独覆盖。[Terms of Use](https://www.harpercollins.com/pages/terms-of-use)
- 自动展示候选的标题、作者、ISBN-13、真实出版日期与 30 天窗口校验为 100%，人工字段准确率至少 95%。[BookRank #116](https://github.com/gongyijie85/bookrank/issues/116)
- 相对官网渲染集合的发现覆盖率至少 90%，不把本次 Atom 观测到的 25 条结果当作全集。[collection](https://www.harpercollins.com/collections/new-releases) [Atom](https://www.harpercollins.com/collections/new-releases.atom)
- 来源运行成功率至少 90%，不得连续失败 3 次；单来源 10 分钟内结束；任何空批次都触发失败与回退。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)
- 403/超时、空列表、DOM 漂移、AI 不可用、部分批次失败和重复批次演练均证明不会污染生产数据。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

**No-Go/保持 Google Books 主来源：**

- 无法取得可用于 30 天窗口的真实 `On Sale`，或只能把 Shopify `published_at` 当替代。[产品 JSON 样例](https://www.harpercollins.com/products/whistler-ann-patchett.js)
- GitHub Actions 普通浏览器持续遇到 challenge，或必须依靠代理/stealth 才能运行。[产品页](https://www.harpercollins.com/products/whistler-ann-patchett) [robots.txt](https://www.harpercollins.com/robots.txt)
- 合规审查不允许拟议的自动采集或公开再发布范围。[Terms of Use](https://www.harpercollins.com/pages/terms-of-use)
- 覆盖率、字段准确率或空批次保护达不到上述门槛。[BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

## 最终推荐

1. **现在不切换生产主通道。** 保持 `HarperCollinsGoogleCrawler`，官网试点默认 `write_enabled=false`。[当前生产映射](https://github.com/gongyijie85/bookrank/blob/fc8d0608390f2a153d0cafaa454c49f78bf3050e/app/services/publisher_data.py#L57-L61)
2. **先验证官方 UCP catalog。** 若能给出作者、版本和真实出版日期，它比浏览器渲染稳定，也符合 robots 中的 agent 指引。[robots.txt](https://www.harpercollins.com/robots.txt) [UCP discovery](https://www.harpercollins.com/.well-known/ucp)
3. **Crawl4AI 只承担缺口。** Atom 做候选发现，产品 `.js` 做确定性字段，Crawl4AI 只补 collection 全分页和允许访问时的 `On Sale`；AI 只生成候选规则，不写生产规则、不猜必填字段。[Atom](https://www.harpercollins.com/collections/new-releases.atom) [产品 JSON](https://www.harpercollins.com/products/whistler-ann-patchett.js) [Crawl4AI 无 LLM 提取](https://docs.crawl4ai.com/extraction/no-llm-strategies/)
4. **把 Cloudflare 当来源不可用条件，不当技术挑战去绕过。** 任一 challenge 都回退 Google Books，并保留上次成功批次。[产品页](https://www.harpercollins.com/products/whistler-ann-patchett) [BookRank #112](https://github.com/gongyijie85/bookrank/issues/112)

在这些约束下，HarperCollins 是一个有价值的 Crawl4AI **观察性试点**，但不是已经证明可上线的“官网权威主来源”。
