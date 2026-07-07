# BookRank 测试覆盖率审计报告

**审计日期**：2026-07-02  
**审计范围**：`tests/` 全部测试、`app/` 覆盖率  
**审计人**：Trae Agent  

---

## 执行摘要

- 在排除 `test_publisher_crawler.py` 与 `test_publisher_crawler_extended.py` 后，其余 **1993 个用例收集成功，1989 passed，4 xfailed**，**总覆盖率 73%**。
- 73% 超过 `pytest.ini` 中 `--cov-fail-under=60` 的门禁，但**未达成项目目标 80%**。
- **完整测试套件未能一次跑完**：首次全量运行因 `test_publisher_crawler.py` 中的测试用例会真实请求 `example.com/robots.txt` 而几乎停滞在 56%，不得不中止。
- **未发现标记为 `slow` 的测试**，但扩展测试文件普遍体积过大（>500 行）， Publisher Crawler 测试真实访问网络，应被打上 `slow`/`integration` 标记并单独跑。
- 三次完整（除 Publisher Crawler 外）重跑结果完全一致，**未观察到不稳定性**。

**总体 verdict：CONCERNS（覆盖率未达目标，测试可维护性需改进）**

---

## 检查命令与原始输出

### 1. 有效覆盖率运行命令

```powershell
$env:FLASK_ENV='testing'; $env:SECRET_KEY='dummy'
python -m pytest tests/ `
  --ignore=tests/test_publisher_crawler.py `
  --ignore=tests/test_publisher_crawler_extended.py `
  --cov=app --cov-report=term-missing --cov-fail-under=0 -q
```

### 2. 运行结果摘要

```text
================= 1989 passed, 4 xfailed in 449.10s (0:07:29) =================
----------------------------------------------------------------------------------------
TOTAL                                                      11021   2945    73%
```

第二次重跑：

```text
================= 1989 passed, 4 xfailed in 449.25s (0:07:29) =================
----------------------------------------------------------------------------------------
TOTAL                                                      11021   2945    73%
```

### 3. 覆盖率 < 60% 的模块

| 模块 | Stmts | Miss | Cover |
|------|-------|------|-------|
| `app/services/publisher_crawler/mixed_crawl4ai_crawler.py` | 284 | 284 | **0%** |
| `app/services/publisher_crawler/hachette.py` | 178 | 157 | **12%** |
| `app/services/publisher_crawler/google_books.py` | 194 | 170 | **12%** |
| `app/services/publisher_crawler/open_library.py` | 178 | 152 | **15%** |
| `app/services/publisher_crawler/macmillan.py` | 187 | 155 | **17%** |
| `app/services/publisher_crawler/rss_crawler.py` | 213 | 167 | **22%** |
| `app/services/publisher_crawler/harpercollins.py` | 73 | 53 | **27%** |
| `app/services/publisher_crawler/base_crawler.py` | 221 | 148 | **33%** |
| `app/services/publisher_crawler/google_books_publisher.py` | 120 | 82 | **32%** |
| `app/services/publisher_crawler/penguin_random_house.py` | 29 | 14 | **52%** |
| `app/services/publisher_crawler/simon_schuster.py` | 29 | 14 | **52%** |
| `app/services/new_book/translation_pipeline.py` | 65 | 28 | **57%** |
| `app/routes/api/awards.py` | 162 | 72 | **56%** |
| `app/routes/api/cache.py` | 54 | 32 | **41%** |
| `app/routes/cron.py` | 29 | 20 | **31%** |
| `app/initialization/awards.py` | 62 | 57 | **8%** |
| `app/initialization/sample_award_books.py` | 94 | 85 | **10%** |
| `app/initialization/sample_books.py` | 41 | 36 | **12%** |

---

## 发现问题

| 严重等级 | 位置 | 问题 | 证据 | 建议 |
|----------|------|------|------|------|
| **High** | `tests/test_publisher_crawler.py`、`tests/test_publisher_crawler_extended.py` | Publisher Crawler 测试会真实发起网络请求（加载 `robots.txt`），导致全量测试套件几乎无法完成，首次全量运行停滞在约 56%。 | `tests/test_publisher_crawler.py` 中 `_TestCrawler.PUBLISHER_WEBSITE = 'https://example.com'`，而 `BaseCrawler.__init__` 默认 `respect_robots_txt=True` 并调用 `_init_robots_parser()` 读取 `/robots.txt`：<br>```python
if self.config.respect_robots_txt and self.PUBLISHER_WEBSITE:
    self._init_robots_parser()
``` | 在测试 Crawler 中设置 `config=CrawlerConfig(respect_robots_txt=False)`；或统一 mock `requests.Session.get`；将 Publisher Crawler 测试标记为 `slow`/`integration`。 |
| **High** | `pytest.ini` markers | 定义了 `slow` 和 `integration` 标记，但仓库中没有任何测试使用它们。 | `pytest.ini`：<br>```toml
markers =
    unit: 单元测试
    integration: 集成测试
    slow: 慢速测试
    ...
```<br>全局搜索 `@pytest.mark.slow` / `@pytest.mark.integration` 无结果。 | 为所有涉及真实网络、数据库迁移、大型文件 IO 的测试添加 `@pytest.mark.slow` 或 `@pytest.mark.integration`；CI 中拆分为 `unit` 与 `slow` 两个 job。 |
| **Medium** | `app/initialization/*.py`、`app/routes/api/cache.py`、`app/routes/cron.py`、`app/services/new_book/translation_pipeline.py`、`app/services/publisher_crawler/*.py` | 多个模块覆盖率低于 60%，尤其是初始化脚本与 Publisher Crawler。 | 上表列出的 18 个模块覆盖率均 < 60%；Publisher Crawler 模块几乎未被测试覆盖。 | 为初始化脚本添加单元测试（或明确标记为一次性脚本并排除出覆盖率统计）；补充 Publisher Crawler 各站点的分支测试（使用 mocked HTTP）。 |
| **Medium** | `tests/test_weekly_report_service_extended.py`（1177 行）<br>`tests/test_admin_routes.py`（1176 行）<br>`tests/test_main_routes_extended.py`（1128 行）<br>`tests/test_publisher_crawler_extended.py`（1078 行）<br>`tests/test_translation_cache_service.py`（812 行）<br>`tests/test_setup_extended.py`（786 行）<br>等 19 个测试文件 | 测试文件行数超过 500 行，定位失败用例与维护成本高。 | 行数统计（节选）：<br>```text
1177 D:\BookRank3\tests\test_weekly_report_service_extended.py
1176 D:\BookRank3\tests\test_admin_routes.py
1128 D:\BookRank3\tests\test_main_routes_extended.py
1078 D:\BookRank3\tests\test_publisher_crawler_extended.py
826 D:\BookRank3\tests\test_public_api_extended.py
812 D:\BookRank3\tests\test_translation_cache_service.py
``` | 按测试子域拆分为多个小文件（例如 `test_admin_routes_auth.py`、`test_admin_routes_books.py`）。 |
| **Low** | `tests/test_award_book_service_extended.py` | 存在 4 个已知失败的 `xfail` 测试，反映源码与模型字段不匹配。 | 运行输出：<br>```text
1989 passed, 4 xfailed
```<br>对应源码注释：<br>```python
@pytest.mark.xfail(reason='源码 _process_award_books 使用 Award(award_key=, category=) 但模型无此列')
``` | 修复模型字段或调整 `_process_award_books` 逻辑，移除过期的 `xfail`。 |
| **Low** | 全量覆盖率 | 总覆盖率 73%，高于 60% 门禁但低于 80% 目标。 | 运行输出：`TOTAL 11021 2945 73%` | 针对低覆盖模块补充测试，目标在下一迭代达到 80%。 |

---

## 不稳定性（Flakiness）检查

- **第一轮**（排除 Publisher Crawler 测试）：`1989 passed, 4 xfailed`，耗时 449.10s。
- **第二轮**（相同范围）：`1989 passed, 4 xfailed`，耗时 449.25s。
- **第三轮**（相同范围）：`1989 passed, 4 xfailed`，耗时 449.95s。
- 三次结果完全一致，未出现失败或状态跳变，**未观察到不稳定性**。

> 注：完整测试套件（含 Publisher Crawler）因网络请求问题未能在合理时间内完成，因此不稳定性检查基于“非 Publisher Crawler 子集”。

---

## Verdict

**CONCERNS**

测试基础设施基本可用，但 Publisher Crawler 测试真实访问网络、缺少 `slow`/`integration` 标记、低覆盖模块集中，导致 suite 无法可靠跑完全量，覆盖率也未达 80% 目标。

---

## 下一步行动

1. **立即**：修复 `test_publisher_crawler.py` 中的测试 Crawler，禁用 `respect_robots_txt` 或 mock HTTP 请求，确保全量 suite 能在 CI 时间内完成。
2. **立即**：为所有网络/IO 密集型测试添加 `@pytest.mark.slow` 或 `@pytest.mark.integration`。
3. **本周**：拆分超过 500 行的测试文件，提高失败定位效率。
4. **两周内**：补充 `app/initialization/*.py`、`app/routes/api/cache.py`、`app/routes/cron.py`、`app/services/new_book/translation_pipeline.py` 及 Publisher Crawler 的测试，将总覆盖率提升至 ≥80%。
5. **两周内**：处理 `test_award_book_service_extended.py` 中的 4 个 `xfail`，消除已知模型不匹配。
