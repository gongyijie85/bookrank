# 死适配器清理 — 设计文档

**日期**: 2026-08-14
**范围**: 删除 8 个死爬虫适配器，注册表收敛为生产活跃类
**策略**: 纯删除（grilling 决策树已与维护者确认），1 个 ticket
**上游决策**: 架构评审候选 #7

---

## 问题

注册表加载 15 个爬虫类，其中 8 个生产不可达：

- legacy 站点爬虫 4 个（生产已迁移到 Google Books 出版社通道 / PRH 官方 API）：
  HachetteCrawler、HarperCollinsCrawler、SimonSchusterCrawler、
  PenguinRandomHouseCrawler；
- RSS ×3（注册但无任何生产引用）；
- MixedCrawl4AICrawler（未注册、零子类、411 行）。

删除测试（deletion test）：删除它们不产生任何复杂度转移——生产调用路径
完全不经过这些类。

## 删除清单

- app/services/publisher_crawler/hachette.py
- app/services/publisher_crawler/harpercollins.py
- app/services/publisher_crawler/simon_schuster.py
- app/services/publisher_crawler/penguin_random_house.py
- app/services/publisher_crawler/rss_crawler.py
- app/services/publisher_crawler/mixed_crawl4ai_crawler.py

## 保留清单（生产活跃 8 类）

OpenLibraryCrawler、GoogleBooksCrawler、PrhApiCrawler、MacmillanCrawler、
SimonSchusterGoogleCrawler、HachetteGoogleCrawler、HarperCollinsGoogleCrawler、
MacmillanGoogleCrawler。

## CRAWLER_MIGRATION 保留

publisher_data.CRAWLER_MIGRATION 是旧类名→新类名的字符串映射，
init_publishers 用它改写存量库行；与类本身无关，保留不动。
删除后若某行仍绑旧类名，get_crawler_class 返回 None → 同步快速失败
（“爬虫不可用”），可观测、不静默。

## 变更文件

- 删除 6 个适配器文件
- app/services/publisher_crawler/__init__.py：注册表收敛为 8 条 + 模块文档更新
- tests/test_publisher_crawler.py：删除 legacy 相关测试；注册表断言改为 8 类精确清单；
  get_crawler_class 类型断言改用 PrhApiCrawler
- tests/test_publisher_crawler_extended.py：删除 TestHachetteCrawler /
  TestHarperCollinsCrawler / TestPenguinRandomHouseCrawler / TestSimonSchusterCrawler /
  TestPublisherRSSCrawler / TestMixedCrawler* 全部死类测试
- CONTEXT.md：爬虫适配器术语更新为活跃数据源

## 行为保持不变量

- 活跃适配器的接口形状不变（CrawlRequest/CrawlOutcome）。
- OpenLibraryCrawler 的内联 Crawl4AI 降级保持现状（独立于本 spec）。
- 同步语义、回填判定、API Key 注入均不受影响。

## 测试策略

- 死类测试随删；注册表断言从“至少含”收紧为“精确等于 8 类”。
- 验收门：全量 pytest、ruff check、mypy 通过。

## 术语

见根目录 CONTEXT.md。
