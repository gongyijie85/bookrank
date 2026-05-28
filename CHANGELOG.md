# Changelog

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

### test: 重写 recommendation_service 测试（26 个用例）

**重写文件**：`tests/test_recommendation_service.py`

**测试类与覆盖场景**：
- `TestExtractKeywords`（5 个）：正常文本、空文本、停用词过滤、短词过滤、混合过滤
- `TestGenerateRecommendationReason`（4 个）：有作者、有分类、两者都有、两者都无
- `TestGetSmartRecommendations`（5 个）：有 session_id、无 session_id、上限钳位 50、下限钳位 1、空个性化结果降级
- `TestGetSimilarityRecommendations`（5 个）：by book_id、by isbn、by award_id、by category、无参数热门降级
- `TestGetPersonalizedRecommendations`（3 个）：无浏览历史降级、有浏览历史个性化、结果不足补充热门
- `TestFormatAwardBook`（2 个）：正常格式化、无分类时显示"获奖作品"
- `TestGetPopularRecommendations`（2 个）：有数据返回、空数据库返回空列表

**验证**：ruff 0 错误 | pytest 26 passed

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
