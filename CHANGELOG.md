# Changelog

## v0.9.51 - 2026-06-02

### style(css): 网格视图图书卡片封面留白，避免 hover 放大压到下半段文字

**问题**：
畅销书排行网格视图（`.card-image`）的图书封面默认 `object-fit: cover` 铺满 2/3 区域，悬浮时再 `transform: scale(1.05)` 放大，整本封面贴紧下方的 `.card-content` 文字信息，视觉上把"第N名 / 标题 / 作者 / 简介"挤到下沿。

**改动**（仅 `static/css/components.css`）：

#### `.card-image`（行 220-231）
- 新增 `padding: 14px`，封面四周留出 14px 空白
- 新增 `display: flex; align-items: center; justify-content: center;`，封面在容器内居中

#### `.card-image img`（行 257-265）
- `object-fit: cover` → `object-fit: contain`，整本封面完整显示，不再被裁切上下
- 删除 `position: relative`（父级 flex 接管）
- 移除 `transform var(--transition-slow)`（不再做 hover 缩放）

#### `.card:hover .card-image img`（行 281-284）
- `transform: scale(1.05)` → `transform: none`，去掉 hover 放大

#### 桌面端增强块 `@media (min-width: 1400px)`（行 1528-1535）
- `.card-image img` transition 由 `transform` 改为 `opacity`
- `.card:hover .card-image img` `scale(1.08)` → `transform: none`

**说明**：
- 角标（`.card-badge` / `.card-category-tag` / `.rank-change`）位置不动，仍固定在 `.card-image` 四角
- 留白背景沿用现有 `--bg-tertiary` 变量（与 shimmer 动画、`.card-tag` 一致）
- 列表视图（`.list-item-image`，行 1500+ 之后）不受影响，未改动

**验证**：
- [x] 浏览器网格视图：封面居中、四周留白 14px，下半段标题/作者/简介不再被贴近
- [x] 桌面端 hover：封面静止，仅卡片阴影变化
- [x] 角标可读性：排名/分类徽章仍清晰可见

## v0.9.50 - 2026-06-02

### chore(ci): 修复 v0.9.49 推送后 CI 失败的 2 个遗留问题

**背景**：
v0.9.49（排行榜 NYT 风格化）推送后 CI 报错，2 个独立问题：

1. **`ruff format` 检查失败**：`weekly_report_service.py` 2 处 `logger.info` / `threading.Thread` 调用跨多行，但 ruff format 要求单行（≤120 字符），需要重新合并
2. **3 个 pytest 用例失败**：`test_main_routes_extended.py::TestWeeklyReports` 中 3 个用例 `ValueError: not enough values to unpack (expected 2, got 0)`

**根因（pytest）**：
v0.9.47 引入自愈机制时，路由 `weekly_reports()` 改为先调用 `report_service.get_or_trigger_current_week_report()`（返回 `tuple[WeeklyReport|None, bool]`）再调用 `get_reports()`。但 `test_main_routes_extended.py` 的 3 个测试只 mock 了 `get_reports`，没有 mock 新的自愈方法。`MagicMock()` 默认值无法解包成 2-tuple，导致 `latest_report, is_generating = ...` 抛出 `ValueError`。

**修复**：

#### `app/services/weekly_report_service.py` + `tests/test_weekly_report_service_extended.py`
- `ruff format app/ tests/` 自动合并多行调用

#### `tests/test_main_routes_extended.py`（`TestWeeklyReports` 类的 3 个测试）
- `test_with_reports`：新增 `mock_svc.get_or_trigger_current_week_report.return_value = (mock_report, False)`
- `test_empty_reports_triggers_generation`：新增 `mock_svc.get_or_trigger_current_week_report.return_value = (None, True)`
- `test_generation_exception`：新增 `mock_svc.get_or_trigger_current_week_report.return_value = (None, False)`

**验证**：
- [x] `ruff check app/ tests/`：All checks passed!
- [x] `ruff format --check app/ tests/`：156 files already formatted
- [x] `mypy app/ --ignore-missing-imports`：Success: no issues found in 88 source files
- [x] `pytest tests/ -m "not slow" --cov-fail-under=60`：**2073 passed, 4 xfailed**，覆盖率 **81.54%**

---

## v0.9.49 - 2026-06-02

### refactor(frontend): 排行榜 list 视图移除行动按钮（贴近 NYT 风格）

**背景**：
排行榜默认 list 视图（`books-list` 段）右侧原本有「收藏 / 分享 / 购买」三个按钮。参照 NYT 榜单设计（[https://www.nytimes.com/books/best-sellers/](https://www.nytimes.com/books/best-sellers/)）的极简风格，决定移除这些按钮，让 list 行更接近 NYT 原版的视觉密度。

**用户操作不受影响**：
- 收藏 / 分享 / 购买功能在图书详情页（`/book/<index>`）仍然可用
- 网格视图（grid）原本就没有这些按钮（保持原样）
- 用户偏好记录（`view_mode` 切换）保持原状，可自由在 grid / list 间切换

**变更**：

#### `templates/index.html` (lines 263-285)
- 删除 `books-list` 段中每个 `.list-item` 内的 `<div class="list-item-actions">` 块
- 包含三个按钮：`.btn-favorite`、`.btn-share`、`.btn-amazon`（条件渲染）

#### `static/js/index.js` (lines 801-808)
- 删除 `renderBooks` 函数中 list 视图模板字符串里的 `.list-item-actions` 块
- 防止动态刷新时重新插入按钮

#### `static/css/index.css` (lines 748-752)
- 删除孤儿 CSS `.list-item-actions { display: flex; ... }`（无元素引用后清理）
- 不影响 grid 视图样式

**Grid 视图**：未改动，仍使用原有 `.card` 容器（封面 + 信息），无行动按钮。

**验证清单**：
- [x] 模板渲染：list 行内不再有 action 按钮 HTML
- [x] JS 动态渲染：`renderBooks()` 也不会插入按钮
- [x] CSS：无未引用规则
- [x] 收藏 / 分享 / 购买：详情页路径不变
- [x] 视图切换：grid / list 按钮可正常切换

---

## v0.9.48 - 2026-06-02

### fix(update-books): 修复 45 分钟超时取消 + 升级 Node.js 24

**问题**：
- Update Books Data #322 运行 45 分 18 秒后被 GitHub Actions 自动取消（撞上 45min timeout）
- 7 个出版社爬虫串行执行总耗时 ~48 分钟 > 45min 上限
- 工作流使用 Node.js 20 弃用警告（GitHub 公告：2026-06-16 强制 Node.js 24，2026-09-16 完全移除 Node.js 20）

**变更**：

#### `update_books.py`
- `sync_all_publishers()` 改为 `ThreadPoolExecutor` 并行（max_workers=7）
- 抽出 `_sync_one()` 内部函数封装单 publisher 同步逻辑
- 失败隔离：单个 publisher 异常不影响其他
- 爬虫是 IO 密集型（HTTP 请求），线程足够，无需 multiprocessing

#### `.github/workflows/update-books.yml`
- `timeout-minutes: 45` → `60`（并行优化后通常 15-20 分钟，留足余量）
- 新增 `env: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'`（升级 Node.js 24，零侵入）
- `setup-python` 加 `cache: 'pip'`（依赖缓存，省 5-8 分钟）

**预期效果**：
| 指标 | 修复前 | 修复后（预估） |
|------|--------|---------------|
| 总耗时 | ~48 min | ~15-20 min（取决于最慢单 publisher）|
| 超时风险 | 高（45min 上限）| 低（60min 上限 + 并行）|
| 依赖安装 | 5-8 min | 1-2 min（缓存命中）|
| Node.js 警告 | 每次运行都警告 | 消失 |

**回滚**：
- `update_books.py` 可单独 revert，恢复串行执行
- workflow 文件可单独 revert，恢复 45min timeout + 无缓存

---

## v0.9.47 - 2026-06-02

### feat(weekly-report): 周报自愈机制（三重保险）

**背景**：
2026-05-29 GitHub Actions 定时任务漏跑，导致 05-25 至 05-31 周报缺失，依赖手动 `workflow_dispatch` 触发才能补生成。Render 免费版 15 分钟休眠 + GitHub Actions 免费层 cron 队列延迟是根本原因。

**变更**：

#### 新增辅助函数
- `app/tasks/weekly_report_task_helpers.py`（新文件）：
  - `compute_expected_week_range(today)` - 复用周区间计算逻辑
  - 业务规则：周一/二/三期望上周周报，周四/五/六/日期望本周周报

#### 服务层
- `app/services/weekly_report_service.py`：
  - 新增 `get_or_trigger_current_week_report()` 方法
    - 检查 expected week 周报是否存在
    - 缺失时启动后台线程调用 `generate_weekly_report()`
    - 复用 `_weekly_report_lock` + 300s 冷却时间防止重复触发
  - 新增 `is_current_week_report_ready()` 轻量查询方法
  - 返回 `(latest_report, is_generating)` 元组供路由层使用

#### 路由层
- `app/routes/main.py`：
  - `weekly_reports` 路由改为调用 `get_or_trigger_current_week_report()`
  - 移除旧的"reports 为空时阻塞生成"逻辑（已被自愈机制替代）
  - 新增 `GET /api/weekly-report/status` 轻量轮询端点
    - 仅查 DB，不调 NYT API
    - 返回 `has_current_week`、`expected_week_end`、`latest_week_end`

#### 任务层
- `app/tasks/weekly_report_task.py`：
  - 重构 `generate_weekly_report()` 使用 `compute_expected_week_range()` 辅助函数
  - 消除 11 行重复代码

#### 前端
- `templates/weekly_reports.html`：
  - 顶部黄色横幅（`is_generating=True` 时显示）
  - 30 秒轮询 `/api/weekly-report/status`，生成完成自动 `location.reload()`
  - 轮询失败用 `console.debug` 静默处理，不阻塞页面

#### CI
- `.github/workflows/trigger-weekly-report.yml`：
  - cron 从 `0 8 * * 5` 改为 `0 8 * * 5,6,0`（周五/六/日 08:00 UTC 三次兜底）

**三重保险机制**：
1. **GitHub Actions** 多时间点 cron（周五/六/日）
2. **数据刷新回调** `book_service.on_data_refreshed`（v0.9.40+ 已有）
3. **应用层自愈** 用户访问 `/reports/weekly` 时自动补生成

**测试**：
- `tests/test_weekly_report_task.py`：新增 6 个 `compute_expected_week_range` 测试（周一~周日全覆盖）
- `tests/test_weekly_report_service_extended.py`：新增 7 个自愈机制测试
  - 正常存在 → 返回 False
  - 缺失 + 冷却中 → 不启动新线程
  - 缺失 + 冷却外 → 启动后台线程
  - 异常 → 降级返回 False

**回滚**：
- 所有改动**向后兼容**，新增方法/端点不破坏现有调用
- 可单独 revert 服务层或路由层，HTML 横幅无影响

---

## v0.9.45 - 2026-06-02

### chore(ci): 修复 v0.9.45 CI 失败的 3 个遗留问题

**背景**：
v0.9.45 commit 触发的 CI 失败（#95）：Code Quality (Ruff)、Type Check (mypy)、Unit Tests 三项均失败。

**修复**：
- **Ruff format check 失败**（3 个文件未格式化）：
  - `app/initialization/sample_award_books.py` — `init_sample_award_books` 修复分支
  - `app/routes/api/awards.py` — admin 端点 + 新增 `fix-award-book-titles-by-ids`
  - `app/services/award_book_service.py` — 之前 v0.9.43 修复时的格式遗留
  - 处理：`ruff format` 自动修复
- **mypy 失败**（2 个 pre-existing 错误）：
  - `app/initialization/sample_award_books.py:570` — `int(award.id)` 中 `award.id` 推断为 `object`，无 overload 匹配 → 改用 `cast('tuple[int, int]', ...)` 显式标注
  - `app/__init__.py:419` — `import bleach` 缺 type stubs → 在 `pyproject.toml` 的 mypy overrides 中加 `bleach.*`
  - 新增 `from typing import cast` 到 `sample_award_books.py`
- **Unit Tests 失败**（1 个 pre-existing 错误）：
  - `tests/test_app_init.py::TestSecurityHeaders::test_csp_nonce_injected` 期望 CSP 含 `nonce-`，但 v0.9.42 决策已移除 nonce（用 `'unsafe-inline'` 替代）
  - 修复：测试改为验证 `'unsafe-inline'` 在 `script-src` 和 `style-src` 中都存在（反映 v0.9.42 的设计决策）

**验证**：
- `ruff check app/ tests/`: All checks passed ✓
- `ruff format --check app/ tests/`: 155 files already formatted ✓
- `mypy app/`: Success: no issues found in 87 source files ✓
- `pytest tests/`: 2060 passed, 4 xfailed, 0 failed ✓

## v0.9.45 - 2026-06-02

### fix(awards): 修复详情页 `title_zh` 字段被错误写入 ISBN（v0.9.44 未根治）
**问题**：
- v0.9.44 修复后，`/award-book/1` 详情页仍显示 ISBN "9780385550369" 而非 "James"
- `/awards` 列表页（grid view 和 list view）依然异常
- 生产数据库实际状态：`title` 字段正确（"James"），但 `title_zh` 字段被填入 ISBN "9780385550369"
- 全 38 本书中，**33 本** 的 `title_zh` 字段值是 13 位 ISBN 数字（不是中文书名）

**根因（v0.9.44 错位）**：
- 模板渲染 `{{ book.title_zh or book.title }}`：**优先使用 `title_zh`**
- v0.9.44 只修复了 `title` 字段（因为旧脏数据是 `title` 存了 ISBN）
- 但实际生产数据**反过来**：`title_zh` 存了 ISBN，`title` 是正确的
- v0.9.44 的 `init_sample_award_books` 修复逻辑只检查 `existing.title`，没检查 `existing.title_zh`
- admin 端点 `fix-award-book-titles` 同样只修复 `title` 字段
- 历史脏数据来源（推测）：早期版本 `translate_book_info` 链路上某处把 `isbn13` 误写入了 `title_zh`

**API 验证**：
```bash
curl https://bookrank-ckml.onrender.com/api/award-books/1
# 返回 {"id":1,"title":"James","title_zh":"9780385550369","isbn13":"9780385550369",...}
# 模板中 {{ book.title_zh or book.title }} 因 title_zh 非空，显示 ISBN
```

**修复**：
- `app/initialization/sample_award_books.py::init_sample_award_books`：
  - 新增 `need_fix_title_zh` 条件分支：当 `existing.title_zh` 为空/等于 ISBN/等于 title/看起来像 ISBN 时，用 seed `title_zh` 修复
  - 触发时机：app 启动时自动跑
- `app/routes/api/awards.py::fix_award_book_titles`（admin 端点）：
  - 增加 `field` 字段到返回的 `fixed` 列表（区分 `title` 和 `title_zh` 修复）
  - 新增 `title_zh` 修复分支（条件同上）

**触发修复**：
```bash
curl -X POST https://bookrank-ckml.onrender.com/api/admin/fix-award-book-titles \
  -H "X-Admin-Token: BookRank2026Fix978"
# 预期返回: {"data":{"fixed":[{id:1,field:"title_zh",from:"9780385550369",to:"詹姆斯"},...], "fixed_count": 33}, ...}
```

**验证**：
- 访问 `/award-book/1` 标题应显示 "詹姆斯"（中文优先，英文 fallback 到 "James"）
- 访问 `/awards` 所有书的中文标题都是正确的中文书名

## v0.9.44 - 2026-06-02

### fix(awards): 修复详情页书名显示为 ISBN 的历史脏数据

**问题**：
- 访问 `/award-book/1`（"James" - 普利策奖 2025 小说）详情页，标题位置显示 ISBN 编号 "9780385550369" 而不是 "James"
- `/awards` 列表页 grid view 和 list view 同样问题

**根因**：
- 生产数据库 `award_books` 表存在历史脏数据：title 字段被填为 ISBN（不是书名）
- `init_sample_award_books` 旧版只按 `award_id + year + title` 过滤 existing，对于 title=ISBN 的脏数据永远查不到，新数据被 add，但脏数据 `is_displayable=True` 仍可见
- `get_award_book_by_id(book_id)` 不过滤 `is_displayable`，详情页直接返回脏数据
- 详情页和列表页都渲染 `{{ book.title_zh or book.title }}`，脏数据 title=ISBN 时直接显示 ISBN

**修复**：
- `app/initialization/sample_award_books.py`：
  - 新增 `_looks_like_isbn(text)` 工具函数（检测 10/13 位纯数字字符串）
  - `init_sample_award_books` 改用 `award_id + year + isbn13` 精确匹配 existing（之前用 title 匹配）
  - 增加**主动修复**逻辑：当 existing.title 异常（为空/等于 ISBN/看起来像 ISBN）时，用 seed 数据更新
  - cleanup 步骤只在 title 看起来像 ISBN 时才标记 deprecated（之前无条件标记）
- `app/routes/main.py`：`award_book_detail` 路由增加 `is_displayable` 过滤（脏数据 `is_displayable=False` 返回 error.html）
- `app/routes/api/awards.py`：新增 `POST /api/admin/fix-award-book-titles` 端点
  - 鉴权：请求头 `X-Admin-Token` 必须匹配环境变量 `ADMIN_TOKEN`
  - 无 ADMIN_TOKEN 配置时拒绝（403）
  - 触发后立即遍历 seed 数据，修复生产数据库历史脏数据

**使用 admin 端点修复**（推荐）：
```bash
# Render 环境变量添加 ADMIN_TOKEN=你的随机密钥
# 然后用 curl 触发修复：
curl -X POST https://bookrank-ckml.onrender.com/api/admin/fix-award-book-titles \
  -H "X-Admin-Token: 你的随机密钥"
```

**自动修复路径**：
- 修复后的 `init_sample_award_books` 在 `init_awards_data` 末尾调用，下次部署启动时自动修复
- 不依赖 admin 端点

**验证**：
- 访问 `/award-book/1` 标题应显示 "James"（不是 "9780385550369"）
- 访问 `/awards` 所有书的标题都是正确书名
- 控制台 `Unchecked runtime.lastError` 是 Chrome 扩展消息通道警告（uBlock/翻译扩展等），与本应用无关，可忽略

## v0.9.43 - 2026-06-02

### fix(api): 修复获奖书单图书翻译 404 错误

**问题**：
- 访问 `/awards` 页面时，控制台批量报错 `POST /api/translate/book/<isbn> 404 (Not Found)`
- 受影响 ISBN 示例：`9781668068458`、`9780224099790`、`9780525535799` 等 20+ 个

**根因**：
- `app/routes/api/translation.py` 的 `translate_book` 路由只查询 `book_service.get_book_by_isbn()`
- 该方法只查 NYT 分类的 books 缓存和 `BookMetadata` 表
- 获奖书单数据存储在 `AwardBook` 表（`app/models/schemas.py:199`），不在查询范围
- 所有获奖书单的 ISBN 都返回 404 "图书不存在"

**修复**：
- `app/services/award_book_service.py`：
  - 新增 `get_award_book_by_isbn(isbn)` 方法（按 isbn13 / isbn10 查询 AwardBook）
  - 新增 `save_award_book_translation(isbn, title_zh, description_zh)` 方法（写翻译回 AwardBook 表；AwardBook 模型无 `details_zh` 字段，只写 title_zh 和 description_zh）
- `app/routes/api/translation.py`：
  - `translate_book` 路由添加 AwardBook fallback
  - 当 `book_service.get_book_by_isbn` 找不到时，回退查询 `AwardBook` 表
  - 翻译结果同时写回 `BookMetadata`（保持语言包一致）和 `AwardBook`
  - 移除"图书服务不可用 503"硬错误，允许在 book_service 缺失时仅用 award_book_service 工作

**验证**：
- 访问 `/awards` 页面，控制台不再有 404 翻译请求
- 首次访问时翻译 API 成功，标题显示中文
- 二次访问走数据库缓存，无 API 调用

## v0.9.42 - 2026-06-02

### fix(frontend): 修复生产环境控制台 CSP 违规 + BookI18n.updateBatch 缺失

**问题**：
- 浏览器控制台报错 `BookI18n.updateBatch is not a function`（`index.js:52`）
- 浏览器控制台报错 `Applying inline style violates the following Content Security Policy directive`（`style-src` 中 nonce 存在时 unsafe-inline 被忽略，导致所有 `el.style.xxx` 被阻止）
- 浏览器控制台报错 `Executing inline event handler violates ...`（`script-src` 不允许内联事件）
- 浏览器警告 `static/icons.svg` 预加载未使用（`base.html:50` 冗余的 `<link rel="preload">`）

**修复**：
- `static/js/book-i18n.js`：新增 `updateBatch(items)` 批量更新方法（items 形如 `[{isbn, language, data}]`，循环调用 `updateTranslation`）
- `static/js/book-i18n.min.js`：同步新增 `updateBatch` 并暴露到 return 对象
- `app/__init__.py`：调整 CSP 配置
  - `script-src` 移除 nonce，保留 `'unsafe-inline'`（内联事件处理器不再被阻止）
  - `style-src` 移除 nonce，保留 `'unsafe-inline'`（`el.style.xxx` 正常工作）
  - 移除 `set_csp_nonce` before_request 与 nonce 注入逻辑
  - 保留 `inject_csp_nonce` context processor（返回空字符串），兼容 29 处模板 `{{ csp_nonce() }}` 引用
- `templates/base.html`：删除第 50 行 `<link rel="preload" href="...icons.svg" as="image">`（与 favicon link 重复，且未真正被 preload 消费）

**权衡**：
- 移除 `style-src` 的 nonce 会让 `'unsafe-inline'` 生效，XSS 防护强度略有下降
- 原因：项目有 49 处 `el.style.xxx` 操作（如 `display = 'none'` / `width = '50%'`），全部重构为 `classList.toggle` 工作量大
- 后续如需恢复严格 CSP：把所有 `.style.xxx` 改为类名切换 + 配套 CSS

**验证**：
- 刷新页面后控制台应不再有 CSP 报错
- 切换中英文不再抛 `BookI18n.updateBatch is not a function`
- icons.svg 预加载警告消失

## v0.9.41 - 2026-05-28

### feat(awards): 2026年获奖书单数据修复与补种机制

**修复内容**：
- `app/initialization/sample_award_books.py`：
  - 修正2026年4本获奖图书的ISBN数据（Open Library验证）：
    - Angel Down: `9781982168322` → `9781668068458`
    - Flesh: `9781668052541` → `9780224099790`
    - The Big Empty: `9780593419601` → `9780525535799`
  - 新增4本2026年图书的中文标题和描述（天使陨落/肉体/台湾漫游录/空城）
  - `init_sample_award_books()` 改为逐条补种模式：不再仅在空库时初始化，而是检查每条 `award_id + year + title` 缺失则补种
- `app/routes/admin.py`：新增 `POST /api/admin/awards/seed` 端点，支持手动触发补种

## v0.9.40 - 2026-05-28

### fix(ci): 修复 update-books 工作流并发运行导致超时问题

**问题**：
- `push` 触发器导致每次代码推送都触发新的爬取任务，多个任务并发运行
- 并发任务同时请求 Google Books API，触发 429 限流
- 爬取耗时超过 30 分钟限制，任务被取消

**修复内容**：
- `.github/workflows/update-books.yml`：
  - 移除 `push` 触发器，仅保留 `schedule`（每周一）和 `workflow_dispatch`（手动触发）
  - 添加 `concurrency` 配置，防止多个爬取任务同时运行
  - `timeout-minutes` 从 30 增加到 45 分钟
  - 定时任务从每天改为每周一执行（减少 API 调用频率）

## v0.9.39 - 2026-05-28

### feat: 更新2025-2026年国际图书大奖数据

**更新内容**：
- `app/initialization/sample_award_books.py`：更新预置获奖图书数据
  - 新增2026年已公布大奖：普利策小说奖（Angel Down）、国际布克奖（Taiwan Travelogue/台湾漫游录）、爱伦·坡奖（The Big Empty）
  - 修正2025年数据：诺贝尔文学奖改为László Krasznahorkai、布克奖改为Flesh、爱伦·坡奖改为The In Crowd、国际布克奖改为Heart Lamp
- `app/services/wikidata_client.py`：Wikidata查询年份范围扩展至2026
- `app/services/award_book_service.py`：刷新服务年份范围扩展至2026

**已确认的2025年获奖信息**：
| 奖项 | 获奖作品 | 作者 |
|------|----------|------|
| 普利策小说奖 | James | Percival Everett |
| 雨果奖最佳长篇 | The Tainted Cup | Robert Jackson Bennett |
| 诺贝尔文学奖 | 代表作Satantango | László Krasznahorkai |
| 爱伦·坡奖最佳小说 | The In Crowd | Charlotte Vassell |
| 国际布克奖 | Heart Lamp | Banu Mushtaq |

**已确认的2026年获奖信息**：
| 奖项 | 获奖作品 | 作者 |
|------|----------|------|
| 普利策小说奖 | Angel Down | Daniel Kraus |
| 国际布克奖 | Taiwan Travelogue（台湾漫游录） | Yáng Shuāng-zǐ（杨双子） |
| 爱伦·坡奖最佳小说 | The Big Empty | Robert Crais |
| 布克奖 | Flesh | David Szalay（2025年颁奖） |

**尚未公布**：
- 2026年雨果奖（LACon V，2026年8月27-31日）
- 2026年诺贝尔文学奖（通常10月公布）
- 2026年星云奖最佳长篇

## v0.9.39 - 2026-05-28

### fix: 修复 update-books 工作流 API 限流和密钥缺失问题

**问题**：
- Google Books API 大量 429 限流错误（请求过于频繁无延迟）
- NYT API Key / 智谱 AI API Key 未配置（`app/__init__.py` 导入时自动启动 APScheduler 后台任务）

**修复内容**：
- `.github/workflows/update-books.yml`：
  - 添加 `DISABLE_BACKGROUND_THREADS=true` 防止启动 APScheduler 后台任务
  - 添加 `FLASK_ENV=testing` 避免自动初始化奖项数据
  - 传递 `NYT_API_KEY`、`ZHIPU_API_KEY`、`GOOGLE_API_KEY` 环境变量（从 GitHub Secrets 读取）
- `app/services/publisher_crawler/google_books.py`：
  - `get_new_books()` 翻页请求间添加 `request_delay` 延迟
  - 增加 429 限流重试逻辑（等待递增后重试）
  - 增加请求异常重试机制

## v0.9.38 - 2026-05-28

### fix: 修复 CI test.yml 工作流 pytest-timeout 缺失导致测试失败

**问题**：
- `test.yml` 工作流使用 `--timeout=60` 参数但未安装 `pytest-timeout` 插件
- 报错：`pytest: error: unrecognized arguments: --timeout=60`

**修复内容**：
- `requirements.txt`：新增 `pytest-timeout>=2.3.0` 开发依赖
- `.github/workflows/test.yml`：安装依赖步骤中显式安装 `pytest-timeout`（双重保险）

## v0.9.37 - 2026-05-28

### test: 新增智谱翻译服务和智能搜索服务扩展测试（107 个用例）

**新增文件**：
- `tests/test_zhipu_translation_extended.py`（55 个用例）
- `tests/test_smart_search_service.py`（52 个用例）

**覆盖率提升**：
- `zhipu_translation_service.py`：57% → 87%（+30%）
- `smart_search_service.py`：64% → 96%（+32%）

**test_zhipu_translation_extended.py 测试类与覆盖场景**：
- `TestGetClientErrorPaths`（6 个）：ImportError / ConnectionError / RuntimeError / 无 API Key / 成功创建 / 已缓存客户端
- `TestGetCacheServiceErrorPaths`（3 个）：导入失败 / 已初始化 / 成功获取
- `TestTranslateRateLimiting`（2 个）：需要等待 / 间隔已过
- `TestTranslateRetryLogic`（5 个）：异常返回 None / 连接错误重试 / 空响应 / 成功更新时间戳
- `TestTranslateBatch`（6 个）：缓存命中 / 空文本 / 进度回调 / 缓存读取异常 / 不可用回退 / 翻译返回 None 回退原文
- `TestTranslateBookFields`（13 个）：空字段 / 缓存命中 / 无客户端回退 / JSON 响应 / Markdown 包裹 / JSON 解码失败 / 异常回退 / 缓存读取异常 / 缓存写入成功/异常 / 速率限制 / 仅未缓存字段 / 空响应
- `TestPostprocessTranslation`（1 个）：委托给 clean_translation_text
- `TestHybridGetClientErrorPaths`（3 个）：备用服务成功 / 导入失败 / 已初始化
- `TestHybridGetCacheServiceErrorPaths`（2 个）：导入失败 / 已初始化
- `TestHybridRunWithContext`（2 个）：无 app 直接调用 / 有 app 上下文
- `TestHybridTranslateExtended`（4 个）：缓存错误处理 / 缓存写入成功 / 缓存写入异常 / field_type 传递
- `TestHybridTranslateBatchExtended`（4 个）：缓存+翻译 / 空文本 / 进度回调 / 缓存读取异常
- `TestHybridTranslateBookFields`（1 个）：委托给智谱
- `TestHybridTranslateAuthorName`（1 个）：委托给智谱
- `TestTranslateBookInfoViaZhipu`（2 个）：翻译书籍信息 / 自定义目标语言
- `TestHybridTranslateBookInfo`（1 个）：委托给辅助函数

**test_smart_search_service.py 测试类与覆盖场景**：
- `TestSanitizeKeyword`（8 个）：空字符串 / None / 空格 / 特殊字符 / 中文 / 连字符 / 多空格 / 长度截断
- `TestEmptySearchResult`（1 个）：返回结构验证
- `TestFormatBook`（2 个）：有奖项 / 无奖项
- `TestFormatNewBook`（2 个）：有出版社 / 无出版社
- `TestSearch`（7 个）：空关键词 / 关键词清洗 / limit 钳制 / offset 钳制 / 异常处理 / has_more 分页 / 格式化结果
- `TestApplyAwardSearchConditions`（5 个）：all / title / author / publisher / 特殊字符转义
- `TestApplyNewBookSearchConditions`（4 个）：all / title / author / publisher（用 isbn13）
- `TestGenerateSuggestions`（3 个）：历史搜索建议 / 去重 / 异常
- `TestGetSuggestions`（7 个）：空前缀 / limit 钳制 / 标题建议 / 作者建议 / 出版社建议 / 去重 / 异常
- `TestGetPopularSearches`（4 个）：正常返回 / limit 钳制 / 异常 / None 时间处理
- `TestSaveSearchHistory`（3 个）：保存成功 / 空关键词 / 异常回滚
- `TestGetSearchHistory`（4 个）：返回关键词 / 去重 / limit 钳制 / 异常
- `TestClearSearchHistory`（2 个）：清空成功 / 异常回滚

**Mock 策略**：
- 智谱 API：使用 `MagicMock` 模拟 `zhipuai.ZhipuAI` 客户端，避免真实 API 调用
- 缓存服务：使用 `Mock` 模拟 `TranslationCacheService` 的 get/set 方法
- SQLAlchemy 查询链：使用 `sqlalchemy.text()` 创建虚拟条件表达式，配合 `patch` 模拟 `or_()` 和 `ilike`
- Flask 应用上下文：使用 `conftest.py` 的 `app` fixture 包裹需要上下文的测试

---

## v0.9.36 - 2026-05-28

### test: 新增 admin.py 原始路由测试（65 个用例）

**新增文件**：
- `tests/test_admin_routes.py`（65 个用例）

**覆盖路由处理器**（10 个，Stage 1-3 原始部分）：
- `TestSyncAwardCovers`（7 个）：同步成功、默认 batch_size、batch_size 钳制上限/下限、无 Google Client 自动创建、异常处理、未授权
- `TestGetAwardCoversStatus`（4 个）：状态查询成功、无 Google Client 回退、异常处理、未授权
- `TestRegenerateWeeklyReport`（8 个）：成功、缺少日期、无效日期格式、未来日期、BookService 不可用、生成失败、异常处理、未授权
- `TestRegenerateAllWeeklyReports`（6 个）：无问题周报、有问题周报、生成失败、BookService 不可用、空数据库、未授权
- `TestCleanupCategories`（6 个）：GET 预览、POST 预览、执行清理、无脏分类、未授权、空数据库
- `TestCleanReportBrackets`（8 个）：GET 预览、POST 预览、执行清理、JSON content 修复、无可修复记录、无效 JSON、未授权、异常处理
- `TestFixTruncatedTitles`（7 个）：GET 预览、执行修复、无截断标题、无 content、无效 JSON、未授权、异常处理
- `TestCleanupTranslations`（8 个）：GET 预览、POST 预览、执行清理、元数据清理、无脏翻译、空数据库、未授权、异常处理
- `TestViewErrors`（4 个）：查看成功、空错误、异常处理、未授权
- `TestClearErrors`（3 个）：清空成功、异常处理、未授权
- `TestCleanReportText`（4 个）：空文本、双书名号、Markdown 粗体、Markdown 斜体

**Mock 策略**：
- 服务层：通过 `app.extensions` 和 `@patch` mock `book_service`、`cache_service`、`google_books_client`
- 模型层：使用 SQLite 测试数据库直接插入数据（`db` fixture）
- 本地导入类：通过 `patch` 源模块路径 mock `AwardCoverSyncService`、`WeeklyReportService`、`NewBookService._sanitize_category`
- SQLAlchemy query descriptor：使用 `patch.object` mock 异常路径

**发现的源码问题**：
- `admin.py:cleanup_categories` 调用 `NewBookService._sanitize_category`，但该方法不存在于 `NewBookService`（应在 `SyncEngine` 上）

---

## v0.9.35 - 2026-05-28

### test: 新增 main.py 和 public_api.py 路由扩展测试（138 个用例）

**新增文件**：
- `tests/test_main_routes_extended.py`（82 个用例）
- `tests/test_public_api_extended.py`（56 个用例）

**修改文件**：
- `pyproject.toml`：`[tool.ruff.lint.per-file-ignores]` 新增 `tests/*` 忽略 N803（mock 参数命名）和 F841（未使用变量）

**test_main_routes_extended.py 测试类与覆盖场景**：
- `TestCachedImage`（4 个）：有效文件名 404、无效短 hash、无扩展名、路径遍历
- `TestAwardBookCover`（3 个）：封面解析成功、失败回退原始 URL、失败无原始 URL
- `TestAwardsPage`（11 个）：默认渲染、列表视图、无效视图、有效年份、年份过旧/过远、无效年份、搜索、奖项列表异常、年份列表异常、书籍加载异常、奖项名过滤
- `TestNewBooksPage`（14 个）：默认、出版社过滤、分类过滤、天数参数、天数钳制、搜索、分页、分页钳制、视图切换、数据种子失败、出版商异常、分类异常、统计异常、获取书籍异常、搜索路径
- `TestNewBookDetail`（5 个）：书籍未找到、需要翻译、已翻译、无翻译服务、部分翻译
- `TestAwardBookDetail`（2 个）：找到、未找到
- `TestBookDetail`（4 个）：有效索引、无效分类回退、无 ISBN 跳过、服务为 None
- `TestBookDetailsApi`（3 个）：成功、未找到、缺少 ISBN
- `TestApiCategoryBooks`（4 个）：成功、服务返回 None、服务异常、外层异常
- `TestWeeklyReports`（3 个）：服务不可用、有报告、空报告触发生成、生成异常
- `TestWeeklyReportDetail`（5 个）：服务不可用、未找到、成功查看、回退日期查询、查看异常
- `TestExportWeeklyReport`（7 个）：服务不可用、无效日期、未找到、不支持格式、PDF 导出成功、PDF 缓冲区为空、Excel 缓冲区为空、导出异常
- `TestSetLanguage`（5 个）：设置 en cookie、设置 zh cookie、无效语言默认 en、默认语言、不安全重定向
- `TestIndexRoute`（5 个）：ExternalAPIError 降级、搜索截断、出版社过滤、排序、出版商列表提取

**test_public_api_extended.py 测试类与覆盖场景**：
- `TestGetAllBestsellersExtended`（3 个）：成功返回、limit 钳制 50、异常 500
- `TestGetBestsellersByCategoryExtended`（5 个）：成功、无效分类、服务不可用、limit 钳制、异常 500
- `TestSearchBestsellersExtended`（5 个）：长关键词、中文关键词、服务不可用、异常 500、limit 钳制
- `TestGetAllAwardsExtended`（3 个）：成功、异常 500、空奖项
- `TestGetAwardBooksExtended`（4 个）：成功、未找到、年份过滤、异常 500
- `TestGetAwardBooksByYearExtended`（4 个）：成功、未找到、无书籍、异常 500
- `TestGetBookDetailsExtended`（5 个）：畅销书找到、奖项找到、服务不可用、异常 500、ISBN10 格式
- `TestGetWeeklyReportsExtended`（4 个）：服务不可用、成功、异常 500、limit 钳制
- `TestGetLatestWeeklyReportExtended`（4 个）：服务不可用、无报告、成功、异常 500
- `TestGetWeeklyReportByDateExtended`（4 个）：服务不可用、未找到、成功、异常 500
- `TestGetNewBooksExtended`（3 个）：异常 500、publisher_id 过滤、per_page 钳制
- `TestGetNewBooksByPublisherExtended`（3 个）：异常 500、找到成功
- `TestGetRecommendationsExtended`（2 个）：异常 500、带 limit 成功
- `TestSerializeNewBookHelper`（4 个）：基本序列化、带中文标题、带 publisher 对象、带字符串 publisher
- `TestApiInfoExtended`（4 个）：版本号、端点数量、速率限制、文档链接

**覆盖率提升**：
- `app/routes/main.py`：57% → 95%（+38 个百分点）
- `app/routes/public_api.py`：53% → 97%（+44 个百分点）

## v0.9.34 - 2026-05-28

### test: 新增 setup.py 与 award_book_service.py 扩展测试（98 个用例）

**新增文件**：
- `tests/test_setup_extended.py`（56 个用例）
- `tests/test_award_book_service_extended.py`（42 个用例，含 4 个 xfail）

**修改文件**：
- `tests/conftest.py`：新增 `award_service`、`sample_award`、`sample_award_book` fixture

**test_setup_extended.py 测试类与覆盖场景**：
- `TestInitNytClient`（3 个）：成功初始化、使用配置值、异常返回 None
- `TestInitGoogleClient`（2 个）：成功初始化、异常返回 None
- `TestInitImageCache`（2 个）：成功初始化、异常返回 None
- `TestInitTranslationService`（2 个）：成功初始化+注册、异常返回 None
- `TestInitBookService`（5 个）：无 NYT 客户端、无缓存服务、成功、注册回调、异常返回 None
- `TestStartBackgroundTasks`（10 个）：TESTING 模式跳过、DISABLE_BACKGROUND_THREADS、创建调度器、各服务存在/不存在时的任务注册、调度器已运行跳过、Render 环境延迟
- `TestSchedulerWrapper`（3 个）：调用任务、捕获异常、保留函数名
- `TestShutdownSchedulerExtended`（2 个）：未运行时跳过、设置为 None
- `TestWeeklyReportTask`（3 个）：正常调用、None 报告、异常处理
- `TestAutoSyncTask`（3 个）：最近同步跳过、旧数据同步、异常处理
- `TestNytRankingSyncTask`（5 个）：无 book_service 跳过、最近同步跳过、旧数据同步、部分失败、异常处理
- `TestCoverSyncTask`（5 个）：success/complete/other 状态、创建客户端、异常处理
- `TestTranslationCacheCleanupTask`（3 个）：成功、无缓存服务、异常处理
- `TestLogFailure`（2 个）：成功、异常处理
- `TestInitServicesExtended`（3 个）：服务注册、调用所有 init 辅助函数、book_service 为 None 时仍调用后台任务

**test_award_book_service_extended.py 测试类与覆盖场景**：
- `TestInitExtended`（2 个）：无 app 初始化、有 app 初始化
- `TestShouldRefreshExtended`（2 个）：无效日期、自定义刷新间隔
- `TestGetRefreshStatusExtended`（1 个）：无效日期
- `TestGetCoverUrl`（2 个）：返回 URL、无封面返回 None
- `TestProcessSingleBook`（10 个）：无 ISBN 失败、创建新书、跳过现有书、更新封面、默认封面跳过、Google 封面回退、默认封面设为 None、ISBN10、长描述优先、作者回退
- `TestProcessAwardBooks`（4 个，含 3 个 xfail）：新奖项创建（xfail-源码 bug）、已有奖项、未知奖项（xfail）、失败计数（xfail）
- `TestRefreshAwardBooksExtended`（3 个）：有数据刷新（xfail）、Wikidata 错误、处理异常
- `TestFetchMissingCoversExtended`（5 个）：获取封面、无 ISBN 跳过、URL 为 None、默认封面、异常处理
- `TestQueryMethodsExceptionPaths`（9 个）：各查询方法的 DB 异常处理
- `TestGetAwardBooksExtended`（3 个）：分类过滤、特殊字符、下划线
- `TestGetDistinctYearsExtended`（2 个）：带 award_id、不存在的 award_id
- `TestUpdateTime`（1 个）：更新值

**覆盖率提升**：
- `app/setup.py`：39% → 95%（+56 个百分点）
- `app/services/award_book_service.py`：53% → 90%（+37 个百分点）

**发现的源码 bug**：
- `_process_award_books` 第 202 行尝试创建 `Award(award_key=, category=)` 但 Award 模型无此列，导致新增奖项路径无法执行（4 个测试标记为 xfail）

**验证**：pytest 94 passed, 4 xfailed

## v0.9.33 - 2026-05-28

### test: 新增 book_detail_service 测试（67 个用例）

**新增文件**：`tests/test_book_detail_service.py`

**测试类与覆盖场景**：
- `TestIsValidIsbn`（22 个）：ISBN-13/10 有效格式、979 前缀、X 校验位、连字符/空格分隔、None/空字符串、无效前缀/长度/字符
- `TestUpdateBookFromGoogleBooks`（28 个，mock `translate_field_async`）：details/page_count/publication_dt/language/publisher/cover/isbn13/isbn10 更新与跳过逻辑、描述翻译触发条件、完整字段更新、空 details 场景
- `TestFetchGoogleBooksDetails`（9 个，mock 缓存与 API 客户端）：缓存命中、缓存未命中 API 成功/失败/返回 None、无客户端、无 book_service、缓存读写异常降级
- `TestMergeOrTranslateBook`（8 个，mock UserService + 翻译服务）：完整/部分翻译元数据命中、未命中需翻译、无翻译服务、无需翻译字段、跳过占位描述、UserService 异常处理

**验证**：py_compile OK | pytest 67 passed

## v0.9.32 - 2026-05-28

### feat: 质量收官 — 测试覆盖率 61% → 84.12%

**覆盖率提升**：
- 新增 14 个测试文件，1047 个新测试用例（987 → 2034 passed）
- 覆盖率从 61% 提升至 84.12%（目标 ≥80%）

**新增测试文件**：
- `test_publisher_crawler_extended.py`：127 个测试，覆盖 11 个爬虫模块
- `test_admin_routes.py`：65 个测试，覆盖原始管理路由
- `test_main_routes_extended.py`：82 个测试，覆盖主页路由未测路径
- `test_public_api_extended.py`：56 个测试，覆盖公共 API 未测路径
- `test_api_helpers_extended.py`：81 个测试，覆盖 API 工具函数
- `test_weekly_report_service_extended.py`：76 个测试，覆盖周报服务
- `test_setup_extended.py`：56 个测试，覆盖 setup.py 初始化函数
- `test_award_book_service_extended.py`：42 个测试，覆盖奖项服务
- `test_zhipu_translation_extended.py`：55 个测试，覆盖翻译服务
- `test_smart_search_service.py`：52 个测试，覆盖搜索服务
- `test_book_detail_service.py`：67 个测试
- `test_translation_cache_service.py`：70 个测试
- `test_award_cover_sync_service.py`：30 个测试
- `test_weekly_report_task.py`：50 个测试

**Bug 修复**：
- `test_service_helpers.py`：修复 `app.extensions` 修改未恢复导致的测试隔离污染
- `test_routes.py`：修复 CSRF token 未 mock 导致翻译 API 测试失败
- `test_setup_app.py`：修复 session-scoped app fixture 与新建 app 实例冲突
- `test_setup_extended.py`：修复 `_nyt_ranking_sync_task` 缺少 `get_book_service` mock

**代码清理**：
- 移除 `award_book_service.py` 中 TODO 注释
- `pyproject.toml`：新增 `RUF059`/`SIM117`/`B011` 测试文件忽略规则
- `ruff format` + `ruff check` 全部通过

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 2034 passed, 4 xfailed | 覆盖率 84.12%

## v0.9.31 - 2026-05-28

### feat: 管理增强 — 爬虫管理、系统监控、数据备份

**爬虫管理 API**：
- `POST /api/admin/crawler/run/<publisher>` 手动触发爬虫（支持 category、max_books 参数）
- `GET /api/admin/crawler/status` 查看所有出版社爬虫状态（活跃数、上次运行时间）
- 内存中跟踪爬虫运行状态（running/completed/failed）

**系统监控**：
- `GET /api/admin/system/status` 返回进程指标（RSS内存、VMS内存、CPU、线程数）
- 数据库类型检测（sqlite/postgresql/mysql）
- 缓存命中率统计、错误日志统计、进程运行时间

**数据备份 API**：
- `GET /api/admin/backup/export` 导出全库为 JSON 文件（awards、award_books、weekly_reports 等6张表）
- `POST /api/admin/backup/import` 从 JSON 导入数据（跳过 id/timestamp 字段避免冲突）

**依赖变更**：
- 新增 `psutil>=5.9.0`（系统监控指标采集）

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 987 passed

### fix(ci): ruff format 修复

- 运行 `ruff format` 修正 10 个文件的格式问题
- CI Code Quality (Ruff) format check 从失败变为通过

## v0.9.30 - 2026-05-27

### feat: 功能补全 — 收藏持久化、公共API、搜索扩展

**收藏持久化**：
- 新建 `UserFavorite` 模型（session_id + isbn + created_at）
- `POST /api/favorites` 添加收藏 | `DELETE /api/favorites/<isbn>` 取消收藏
- `GET /api/favorites` 获取收藏列表 | `GET /api/favorites/check/<isbn>` 检查状态
- 前端 `toggleFavorite` 对接后端 API，替换原有 console.log 占位

**新书公共 API**：
- `GET /api/public/new-books` 获取新书列表（支持分页、分类、出版社筛选）
- `GET /api/public/new-books/<publisher>` 按出版社获取新书

**推荐公共 API**：
- `GET /api/public/recommendations` 智能推荐（自动降级到热门推荐）

**搜索扩展**：
- SmartSearchService 同时搜索 AwardBook + NewBook 两个数据源
- 搜索结果合并，每条结果标注 `source: 'award'` 或 `'new_book'`

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.11%

## v0.9.29 - 2026-05-27

### refactor: 前端瘦身 — CSS/JS 提取与模板精简

**CSS 提取**：
- `templates/index.html` 1093 行内联 CSS → `static/css/index.css` 独立文件
- 通过 `{% block extra_css %}` + `<link>` 标签引用，保留 CSP nonce

**JS 提取**：
- `templates/index.html` 1250 行内联 JS → `static/js/index.js` ES Module
- Jinja2 模板变量（defaultCover、currentCategory）提取到 `window.APP_CONFIG` 配置对象
- 通过 `<script type="module">` 加载，保留 CSP nonce

**模板瘦身**：
- `index.html` 从 2703 行减至约 580 行（减少 78%）
- 保留最小化内联 script 块传递服务端配置变量

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.46%

## v0.9.28 - 2026-05-27

### chore: 地基修复 — 统一 Python 版本与 CI 门禁

**render.yaml**：
- `PYTHON_VERSION` 3.11.0 → 3.13.0
- 构建命令改用 `requirements-prod.txt`（减少生产环境内存占用）

**CI 工作流统一**：
- `test.yml`：Python 3.11 → 3.13；移除 `--exit-zero`，lint 错误阻断构建
- `update-books.yml`：Python 3.10 → 3.13
- `ci.yml`：已为 3.13，无需修改

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed

## v0.9.27 - 2026-05-27

### refactor: 服务注入标准化（阶段3完成）

**增强 `service_helpers.py`**：
- `get_translation_service()` 添加返回类型 `HybridTranslationService | None`
- 新增 `register_service(app, name, service)` 统一服务注册
- 新增 `require_cache_service()`、`require_translation_service()`、`require_image_cache_service()` 非空 getter

**替换直接 `app.extensions` 访问**：
- `setup.py`：5 处 `app.extensions['xxx'] = ...` → `register_service()`
- `setup.py`：5 处 `app.extensions.get('xxx')` → 类型安全 getter 函数
- `scripts/batch_translate.py`：3 处 `app.extensions.get('book_service')` → `get_book_service()`
- `app/utils/__init__.py`：导出新增的 5 个函数

**保留未替换**：
- `app/utils/exceptions.py`：`safe_service_call` 使用动态 key，保持原样
- `migrations/env.py`：Flask-Migrate 扩展，保持原样

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.46%

## v0.9.26 - 2026-05-27

### refactor: 大文件拆分（阶段2完成）

**NewBookService 拆分为子模块**：
- `app/services/new_book/publisher_manager.py`（81行）：PublisherManager 类
- `app/services/new_book/sync_engine.py`（416行）：SyncEngine 类
- `app/services/new_book/translation_pipeline.py`（105行）：TranslationPipeline 类
- `app/services/new_book/query_service.py`（159行）：NewBookQueryService 类
- `app/services/new_book/__init__.py`（154行）：NewBookService 门面类，保持向后兼容
- 原 `new_book_service.py` 改为重导出（3行），所有公开 API 签名不变

**main.py 辅助函数提取**：
- `app/utils/book_filters.py`（60行）：filter_books_by_search, filter_books_by_publisher, filter_books_by_weeks, sort_books
- `app/utils/date_helpers.py`（28行）：validate_date, parse_report_content
- `app/services/book_detail_service.py`（214行）：fetch_google_books_details, merge_or_translate_book, translate_field_async, update_book_from_google_books, is_valid_isbn
- `app/routes/main.py`：972行 → 677行（减少 295行，-30.4%）

**Bug 修复**：
- 移除重复 `@staticmethod` 装饰器
- 统一 `_GOOGLE_BOOKS_CRAWLERS` 定义
- mypy 类型注解修复：门面类类级别注解、SQLAlchemy filter 表达式 type ignore

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.72%
