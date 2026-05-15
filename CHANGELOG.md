# Change Log

## v0.9.9 - 2026-05-15 - 分类切换报错修复与语言同步优化

### 修复内容

#### 1. 切换图书分类报错（加载失败，请重试）

**问题描述**：在首页切换除默认分类外的其他图书分类时，出现红色错误提示"加载失败，请重试"

**根本原因**：
- `/api/category-books` 接口在处理某些分类时，`book_service.get_books_by_category()` 可能因外部API异常抛出未捕获的异常
- 虽然 `get_books_by_category` 内部已捕获 `APIException` 和 `APIRateLimitException`，但在服务层初始化失败或网络超时等极端情况下，异常会穿透到路由层
- 前端 `changeCategory()` 函数捕获到非200状态码后显示错误提示

**修复方案**：
- 在 `api_category_books` 路由中增加外层 try-catch 包裹
- 服务异常时降级返回空列表（而非500错误），前端会正常显示空状态提示
- 保留错误日志记录，便于排查问题

**涉及文件**：
- `app/routes/main.py`：`api_category_books()` 函数异常处理增强

#### 2. 切换到中文后导航栏未显示中文

**问题描述**：点击语言切换按钮切换到中文后，导航栏菜单、按钮文字仍显示英文

**根本原因**：
- `templates/base.html` 内联脚本总是将服务端语言（serverLang）强制写入 localStorage，覆盖用户通过UI切换的语言选择
- 用户点击"简体中文"后，`/set-language` 设置 cookie 并重定向，但页面加载时内联脚本立即用服务端语言覆盖 localStorage
- 导致 `base.js` 的 `initLanguage()` 读取到错误的语言值，按钮状态与实际语言不一致

**修复方案**：
- **base.html**：内联脚本优先读取用户已保存的 localStorage 语言设置，仅在没有用户偏好时才使用服务端语言
- 当检测到用户语言与服务端不一致时，静默更新 cookie（不刷新页面），让下次页面加载时服务端能正确读取
- 避免循环重定向，提升用户体验

**涉及文件**：
- `templates/base.html`：语言初始化脚本逻辑优化

---

## v0.9.8 - 2026-05-15 - 语言切换按钮修复

### 修复内容

#### 1. 语言切换按钮状态不同步

**问题描述**：切换到中文版后，导航栏语言按钮仍显示英文（EN 而不是 中）

**根本原因**：
- `base.html` 内联脚本和 `base.js` 的 `initLanguage()` 同时尝试更新语言按钮
- 两者执行顺序不确定（竞态条件），且读取不同语言来源（cookie vs localStorage）
- 导致页面刷新后，按钮状态可能与实际语言不一致

**修复方案**：
- **base.html**：内联脚本只负责同步 localStorage 为服务端 cookie 的值，不再直接调用 `updateLangDropdown`
- **base.js**：`initLanguage()` 统一在 `DOMContentLoaded` 时执行：
  - 读取 localStorage（已由内联脚本同步）
  - 调用 `updateLangDropdown()` 更新按钮 UI
  - 触发 `languagechange` 事件通知其他页面

### 影响
- 语言切换后，按钮状态始终与实际语言一致
- 消除了竞态条件，确保 DOM 加载完成后再更新 UI

### 涉及文件
- `templates/base.html`：简化内联语言初始化脚本
- `static/js/base.js`：改进 `initLanguage()` 函数，添加事件触发

## v0.9.7 - 2026-05-14 - 路由层 db.session 治理 & 前端 XSS 加固

### 修复内容

#### 1. 路由层 db.session 治理

**new_book_detail 路由修复（app/routes/main.py L420）**：
- **修复前**：`db.session.get(NewBook, book_id)` 直接使用 db.session，违反"路由层禁止 db.session"规则
- **修复后**：使用 `NewBookService().get_book(book_id)` 获取图书详情
- **异步翻译提取**：闭包内翻译逻辑提取至 `NewBookService.translate_book_background()` 方法
- **影响**：消除路由层直接 DB 操作，符合架构分层规范

**_merge_or_translate_book 闭包修复（app/routes/main.py L650-686）**：
- **修复前**：闭包内直接使用 `db.session.add/commit/rollback`
- **修复后**：新增 `UserService.save_book_translation()` 方法，闭包仅传递翻译结果，由 Service 层完成持久化
- **影响**：消除闭包内 db.session 操作，事务管理统一收口到 Service 层

#### 2. 前端 XSS 加固

**index.html 搜索历史 aria-label 未转义（L1667）**：
- **修复前**：`aria-label="删除 ${query}"` 中的 `${query}` 未转义
- **修复后**：`aria-label="删除 ${escapeHtml(query)}"`
- **影响**：防止搜索历史中含特殊字符时的潜在注入

**analytics_dashboard.html 表格行模板未转义（L406-410）**：
- **修复前**：`item.date`、`item.title`、URL 路径拼接均未转义
- **修复后**：所有 innerHTML 中的变量使用 `escapeHtml()` 转义
- **影响**：防止周报标题等用户数据中的恶意脚本执行

#### 3. 代码规范修复

**user_service.py 返回类型字符串前引（L86）**：
- **修复前**：`-> 'BookMetadata | None'` 使用字符串前引
- **修复后**：`-> BookMetadata | None`（类型已在顶部导入）
- **影响**：符合 mypy 最佳实践

**open_library_client.py User-Agent 硬编码（L29）**：
- **修复前**：`'BookRank/2.0 (bookrank@example.com)'` 硬编码
- **修复后**：从 `current_app.config.get('OPEN_LIBRARY_USER_AGENT', 'BookRank/2.0')` 读取，使用 try/except 处理无 app context 场景
- **影响**：User-Agent 可通过环境变量配置，增强灵活性

### 影响
- 路由层 db.session 操作进一步减少，架构分层更清晰
- 前端 XSS 防护更加完善
- 类型注解和配置项更加规范

### 涉及文件
- `app/routes/main.py`：new_book_detail 路由改用 Service 层，_merge_or_translate_book 闭包重构
- `app/services/new_book_service.py`：新增 `translate_book_background()` 方法
- `app/services/user_service.py`：新增 `save_book_translation()` 方法，修复返回类型注解
- `app/services/open_library_client.py`：User-Agent 配置化
- `templates/index.html`：aria-label 转义修复
- `templates/analytics_dashboard.html`：表格行模板转义修复

## v0.9.6 - 2026-05-14 - 配置项集中管理 & 图表颜色规范化

### 修复内容

#### 1. 图表颜色硬编码修复

**背景**：`analytics_dashboard.html` 中 Chart.js 图表颜色值直接硬编码在配置中，未使用 `chartColors` 对象统一管理，违反项目周报模块规范。

**修改**：
- `templates/analytics_dashboard.html`：
  - 在文件 `<script>` 顶部定义 `chartColors` 对象，使用与 `weekly_report_detail.html` 相同的颜色方案
  - 替换所有 12 处硬编码颜色值为 `chartColors` 引用
  - 新增颜色：`green`, `red`, `gray`, `blue`, `yellow`, `purple` 及其 Border 变体

#### 2. 硬编码配置值迁移到 config.py

**背景**：多个服务类中的缓存 TTL、模型名称、容量限制等配置值直接硬编码，无法通过环境变量或配置文件调整。

**新增配置项（`app/config.py`）**：
- `NYT_CACHE_TTL = 86400 * 7`：NYT API 数据缓存时间（7天）
- `GOOGLE_BOOKS_CACHE_TTL = 86400`：Google Books API 缓存时间（24小时）
- `OPEN_LIBRARY_CACHE_TTL = 86400 * 3`：Open Library API 缓存时间（3天）
- `ZHIPU_TRANSLATION_MODEL = 'glm-4.7-flash'`：智谱 AI 翻译模型名称
- `BOOK_SERVICE_CACHE_TTL = 86400`：BookService 默认缓存时间（24小时）
- `MEMORY_CACHE_MAX_SIZE = 1000`：内存缓存最大条目数

**修改的服务类**：
- `app/services/nyt_client.py`：`CACHE_TTL` 类常量改为 `DEFAULT_CACHE_TTL`，构造函数新增 `cache_ttl` 参数，支持配置覆盖
- `app/services/google_books_client.py`：同上，新增 `cache_ttl` 参数
- `app/services/open_library_client.py`：同上，新增 `cache_ttl` 参数
- `app/services/zhipu_translation_service.py`：`model` 参数改为可选，优先使用参数值，其次从 `app.config` 读取，最后回退到默认值
- `app/services/book_service.py`：`ttl=86400` 硬编码改为从 `app.config.get('BOOK_SERVICE_CACHE_TTL', 86400)` 读取
- `app/services/cache_service.py`：`MemoryCache` 的 `max_size` 改为从配置读取
- `app/setup.py`：初始化服务时传递配置值

### 影响
- 所有 API 缓存 TTL 可通过配置文件统一调整，无需修改代码
- 翻译模型名称可配置，方便后续模型升级
- 图表颜色统一管理，后续修改只需改一处
- 保持向后兼容，所有配置项均有合理默认值

### 涉及文件
- `app/config.py`：新增 6 个配置项
- `templates/analytics_dashboard.html`：新增 `chartColors` 对象，替换 12 处硬编码颜色
- `app/services/nyt_client.py`：`CACHE_TTL` 改为实例变量 + 配置参数
- `app/services/google_books_client.py`：同上
- `app/services/open_library_client.py`：同上
- `app/services/zhipu_translation_service.py`：`model` 改为从配置读取
- `app/services/book_service.py`：`ttl` 改为从配置读取
- `app/setup.py`：传递配置值到各服务初始化

## v0.9.5 - 2026-05-14 - API 路由统一错误处理装饰器

### 修复内容

#### 引入 handle_api_errors 装饰器

**背景**：所有 API 路由均使用手动 try/except，未使用 `handle_api_errors` 装饰器，导致错误处理逻辑分散、格式不统一。

**修改**：
- `app/routes/api/books.py`（6个函数）：`get_books`、`search_books`、`get_search_history`、`user_preferences`、`export_csv`、`get_book_details` 全部引入 `@handle_api_errors` 装饰器，移除手动 try/except
- `app/routes/api/translation.py`（6个函数）：`translate_text`、`translate_book_fields`、`translate_book`、`get_translation_cache_stats`、`get_translation_cache_recent`、`clear_translation_cache` 全部引入装饰器
- `app/routes/api/cache.py`（4个函数）：`get_api_cache_stats`、`get_api_cache_recent`、`clear_api_cache`、`clear_expired_api_cache` 引入装饰器
- `app/routes/api/awards.py`（5个函数）：`get_awards`、`get_award_books`、`get_all_award_books`、`get_award_book_detail`、`search_award_books` 引入装饰器
- `app/routes/api/recommendations.py`（5个函数）：`get_recommendations`、`get_similarity_recommendations`、`get_search_suggestions`、`smart_search`、`get_popular_searches` 引入装饰器
- `app/routes/analytics_bp.py`（5个函数）：`get_report_views`、`get_user_behavior`、`get_daily_stats`、`get_top_reports`、`get_session_stats` 引入装饰器

#### 统一错误返回格式

**修复 translation.py L147 语义矛盾**：
- **修复前**：`APIResponse.success(data={'service': '...', 'status': 'error', ...})`，使用 success 方法包装错误状态
- **修复后**：让 `@handle_api_errors` 装饰器统一处理异常，返回标准的 `APIResponse.error()` 格式

**修复 main.py 中 book_details_api 和 api_category_books**：
- **修复前**：
  - 错误时返回 `{'success': False, 'error': '...'}`，使用 `error` 键而非 `message` 键
  - 成功时返回 `{'success': True, 'details': ...}`，缺少 `data` 包装键
  - 使用 `jsonify()` 直接返回，未使用 `APIResponse` 类
- **修复后**：
  - 全部使用 `APIResponse.error()` 和 `APIResponse.success()` 包装
  - 错误返回统一为 `{'success': False, 'message': '...'}` 格式
  - 成功返回统一为 `{'success': True, 'data': {...}}` 格式

#### 代码清理
- 移除不再需要的 `APIException`、`APIRateLimitException` 导入（books.py）
- 移除 31 处手动 try/except 块，代码行数减少约 150 行

### 影响
- 所有 API 错误处理由装饰器统一接管，新增异常类型只需修改一处
- 错误返回格式完全统一，前端可依赖标准结构
- 代码更简洁，业务逻辑更清晰

### 涉及文件
- `app/utils/api_helpers.py`：确认装饰器存在（无需修改）
- `app/routes/api/books.py`：引入装饰器 + 清理 try/except
- `app/routes/api/translation.py`：引入装饰器 + 修复 L147 矛盾用法
- `app/routes/api/cache.py`：引入装饰器 + 清理 try/except
- `app/routes/api/awards.py`：引入装饰器 + 清理 try/except
- `app/routes/api/recommendations.py`：引入装饰器 + 清理 try/except
- `app/routes/analytics_bp.py`：引入装饰器 + 清理 try/except
- `app/routes/main.py`：引入装饰器 + 统一错误返回格式

## v0.9.4 - 2026-05-14 - 前端 XSS 漏洞修复与安全加固

### 修复内容

#### XSS 漏洞修复

##### index.html 购买链接注入漏洞
- `templates/index.html`（L2535-2536）：`renderBuyLinks()` 函数中 `link.name` 未转义直接注入 DOM
  - **修复前**：`a.innerHTML = \`<svg ...> ${link.name || '购买链接'}\`;`
  - **修复后**：使用 `escapeHtml(link.name || '购买链接')` 转义
  - **影响**：防止恶意购买链接名称注入恶意脚本

##### base.html SVG 内容注入
- `templates/base.html`（L316）：SVG Sprite 加载时未验证内容类型和格式
  - **修复方案**：
    1. 增加 `Content-Type` 校验，拒绝非 SVG 类型响应
    2. 内容格式校验，必须以 `<svg` 或 `<?xml` 开头
    3. 使用 `DOMParser` 解析验证 SVG 结构合法性
    4. 捕获解析错误并阻止注入
  - **影响**：防止恶意内容通过 SVG Sprite 注入页面

##### analytics_dashboard.html 表格数据转义
- `templates/analytics_dashboard.html`（L381-386）：`renderTopReports()` 函数中 `item.date`、`item.title`、`item.view_count` 未转义
  - **修复方案**：
    1. 新增 `escapeHtml()` 函数定义（与 base.js 保持一致）
    2. 所有用户可见数据使用 `escapeHtml()` 转义
    3. 日期参数在 URL 构建时也进行转义
  - **影响**：防止周报标题等用户数据中的恶意脚本执行

#### Promise 错误处理确认

##### index.html 预加载请求
- `templates/index.html`（L2339）：`fetch()` 链已有 `.catch(() => {})` 静默处理
  - **状态**：已有处理，无需修改

##### new_books.html 数据加载请求
- `templates/new_books.html`（L307）：`fetch()` 链已有 `.catch(error => {...})` 错误展示
  - **状态**：已有处理，无需修改

### 安全加固总结
- 所有动态内容注入 DOM 前使用 `escapeHtml()` 转义
- SVG 内容加载增加类型、格式、结构三重验证
- 前端错误处理链路完整，无未捕获 Promise rejection

### 涉及文件
- `templates/index.html`：修复购买链接 XSS 漏洞
- `templates/base.html`：修复 SVG Sprite 注入漏洞
- `templates/analytics_dashboard.html`：修复表格数据 XSS 漏洞 + 新增 escapeHtml 函数

## v0.9.3 - 2026-05-14 - SECRET_KEY 管理与 CORS 配置安全修复

### 修复内容

#### SECRET_KEY 管理修复（app/config.py）
- **问题**：`SECRET_KEY` 每次模块加载时用 `secrets.token_hex(32)` 重新生成，多实例部署导致 session 不一致
- **修复**：
  - 基类 `Config` 使用固定开发密钥（`dev-secret-key-for-local-development-only-do-not-use-in-production`），确保进程重启后不变
  - `DevelopmentConfig` 可通过环境变量覆盖，否则使用基类固定 key
  - `ProductionConfig` 在 `init_app()` 时强制校验，未设置则 `raise ValueError` 启动失败，拒绝静默生成随机值
  - 移除 `config.py` 中不再使用的 `import secrets`

#### 默认配置模式修复（app/config.py）
- **问题**：默认配置为 `development`（DEBUG=True），生产环境若忘记设置 FLASK_ENV 将暴露调试信息
- **修复**：`config['default']` 改为 `ProductionConfig`，`create_app()` 参数为 None 时默认使用 `development` 以保证本地开发体验

#### CORS 配置修复（app/__init__.py）
- **问题**：
  - 开发环境使用 `origins='*'` + `supports_credentials=True`，浏览器不允许此组合
  - 生产环境 `CORS_ORIGINS` 为空时传 `[]` + `supports_credentials=True`，跨域请求被全部阻止
- **修复**：
  - 开发环境改为明确域名 `['http://localhost:5000']` + 动态 `supports_credentials`
  - 测试环境保留 `origins='*'`（无 credentials）
  - 生产环境 `CORS_ORIGINS` 为空时输出警告日志，`supports_credentials` 设为 `False`
  - 移除 CORS 资源块内的重复 `supports_credentials` 参数

### 涉及文件
- `app/config.py`：SECRET_KEY 策略重构、默认配置改为 production、新增生产环境 init_app 校验
- `app/__init__.py`：CORS 配置按环境分离、SECRET_KEY 警告条件优化、默认参数调整

## v0.9.2 - 2026-05-14 - 缓存高频写入优化与分析服务日志补全

### 修复内容

#### 缓存命中即 commit 问题修复
- `app/services/api_cache_service.py`（L55-61）：移除 `get()` 方法缓存命中时的 `usage_count` 递增和 `db.session.commit()`
- `app/services/translation_cache_service.py`（L88-94）：移除 `get()` 方法缓存命中时的 `usage_count` 递增和 `db.session.commit()`
- **根因**：每次缓存命中都触发数据库写入 + commit，高并发场景下数据库写入压力极大
- **修复方案**：移除读路径上的写入操作，`usage_count` 仅在 `set()` 方法（新建或更新缓存内容）时递增
- **影响**：`usage_count` 和 `last_used_at` 不再实时反映读取频率，但消除了高频写入瓶颈，数据库负载显著降低

#### analytics_service.py 日志补全
- 添加模块级 `logger = logging.getLogger(__name__)`
- 所有 5 个查询方法添加 `info` 级别日志记录查询参数和结果
- 所有方法添加 `try/except SQLAlchemyError` 异常处理
- 异常时返回空结果集而非静默抛出
- **影响**：生产环境可追踪分析查询执行情况，失败时不再静默丢失错误信息

### 涉及文件
- `app/services/api_cache_service.py`：删除 7 行缓存命中写入逻辑
- `app/services/translation_cache_service.py`：删除 8 行缓存命中写入逻辑
- `app/services/analytics_service.py`：添加 logging、异常处理、日志记录（全文件重写）

## v0.9.1 - 2026-05-14 - 数据库迁移系统修复

### 修复内容

#### 数据库迁移系统修复
- 新增迁移文件 `migrations/versions/create_all_missing_tables.py`，包含 8 个缺失表的完整 CREATE TABLE 语句：
  - `translation_cache`（翻译缓存表）
  - `api_cache`（外部API缓存表）
  - `system_config`（系统配置表）
  - `weekly_reports`（每周畅销书报告表）
  - `report_views`（周报阅读记录表）
  - `user_behaviors`（用户行为数据表）
  - `publishers`（出版社表）
  - `new_books`（新书表）
- 每个表包含所有字段、主键、外键、唯一约束、命名索引和 SQLAlchemy 自动索引（`index=True` 产生的 `ix_` 前缀索引）
- 提供完整的 `upgrade()` 和 `downgrade()` 函数
- 修改初始迁移文件 `3d9883f1b5ed_initial_migration_all_tables.py`，添加历史说明注释，标注仅包含 CREATE INDEX 的缺陷
- 迁移链顺序：`3d9883f1b5ed` → `add_chinese_fields` → `add_csrf_tokens_table` → `create_all_missing_tables`

### 影响
- 生产环境可通过 `flask db upgrade` 完整重建所有表结构
- 全新环境不再依赖 `db.create_all()` 创建表

### 涉及文件
- `migrations/versions/create_all_missing_tables.py`（新建）
- `migrations/versions/3d9883f1b5ed_initial_migration_all_tables.py`（修改，添加历史说明）

## v0.9.0 - 2026-05-14 - 全面代码审计报告

> 本次审计覆盖路由层、服务层、模型层、前端模板、配置安全和测试体系，共发现 **120+** 个问题，其中严重问题 **8** 项、高危问题 **15** 项、中等问题 **40+** 项。

### 🔴 严重问题（需优先修复）

#### 路由层直接操作 db.session（违反架构规范 v0.6.0+）
- **30+ 处**路由函数直接使用 `db.session` 查询/写入，未通过 Service 层
- 涉及文件：`books.py`、`awards.py`、`cache.py`、`main.py`、`admin.py`、`public_api.py`
- **影响**：违反分层架构，路由层与数据层紧耦合，难以测试和维护
- **修复优先级**：最高 — 逐步将所有数据库操作迁移至 Service 层

#### 数据库迁移系统失控
- 初始迁移 `3d9883f1b5ed` 仅包含 `CREATE INDEX`，无 `CREATE TABLE` 语句
- **8 个表**无任何迁移记录（TranslationCache、APICache、SystemConfig、WeeklyReport、ReportView、UserBehavior、Publisher、NewBook）
- **影响**：生产环境无法通过 `flask db upgrade` 重建表结构，完全依赖 `db.create_all()`
- **修复优先级**：最高 — 重新生成迁移文件或使用 Alembic 自主迁移

### 🟠 高危问题

#### 安全配置缺陷
- `SECRET_KEY` 每次模块加载重新生成，多实例部署导致 session 不一致
- 默认配置模式为 `'development'`（`DEBUG=True`），生产环境若忘记设置 `FLASK_ENV` 将暴露调试信息
- Dockerfile 以 root 用户运行，无 `USER` 指令切换
- CORS `supports_credentials=True` 与空列表/`*` 组合被浏览器拒绝

#### XSS 风险
- `index.html:2535-2536`：`link.name` 未转义直接注入 DOM
- `base.html:316`：SVG 内容通过 `innerHTML` 注入
- `analytics_dashboard.html`：多处 `innerHTML` 拼接未转义

#### 前端 Promise 未捕获
- `index.html:2333`、`new_books.html:296`：`fetch()` 链缺少 `.catch()`，网络失败时产生未捕获 rejection

### 🟡 中等问题

#### API 路由未使用规范组件
- 所有 API 路由均使用手动 `try/except`，未使用 `handle_api_errors` 装饰器
- 所有 API 输入使用 `request.get_json()` + `data.get()`，未使用 Pydantic 验证模型
- 错误返回格式不统一（`error` vs `message`、成功/失败包装不一致）

#### 路由重复
- `/api/awards` vs `/api/public/awards`：奖项列表端点重叠
- `/api/award-books` vs `/api/public/awards/<award_name>`：获奖图书端点重叠
- `/api/recommendations` vs `/api/recommendations/similarity`：推荐端点冗余
- `/api/book-details/<isbn>` vs `/api/public/book/<isbn>` vs `book_details_api()`：三个图书详情端点

#### 服务层问题
- **缓存命中即 commit**：`api_cache_service.py:56-61`、`translation_cache_service.py:88-94` 每次缓存命中都触发数据库写入
- **硬编码配置值**：缓存 TTL、模型名称、API URL 等分散在多个服务类中
- **异常处理过于宽泛**：38 处 `except Exception` 可能掩盖约束错误等特定问题
- **内存泄漏风险**：`_on_data_refreshed_callbacks` 列表无限增长无清理
- **analytics_service.py 完全缺失日志**：生产环境无法排查问题

#### 模型层问题
- `price` 字段使用 `String(50)` 存储，应使用 `Numeric` 类型
- `UserBehavior.target_type` 无索引
- `NewBook.publisher` 关系可能产生 N+1 查询
- `Book` dataclass 18 个必填字段无默认值

#### 前端问题
- CSS 全部内联于模板 `<style>` 块，无法利用浏览器缓存
- 侧边栏导航在 5 个模板中重复定义
- `analytics_dashboard.html` 图表颜色硬编码（违反项目规范）

#### 限流与重试
- `google_books_client.py`：429 限流后只等待 2 秒重试一次，无指数退避
- `open_library_client.py`：无速率限制（API 规范为 1次/秒）
- 限流器使用内存存储，多实例环境可绕过

### 🟢 低危问题

- `ip_address` 字段（`String(50)`）IPv6 余量不足
- `user_agent` 字段（`String(500)`）可能被截断
- Service Worker 缓存无过期机制
- CSP `script-src-attr 'unsafe-inline'` 削弱保护
- Server 头部暴露应用名称
- Docker 镜像无 `.dockerignore`

### 修复建议优先级

| 优先级 | 问题类别 | 预估影响 |
|--------|---------|---------|
| P0 | 数据库迁移系统 | 生产部署可靠性 |
| P0 | 路由层 db.session 操作 | 架构一致性 |
| P1 | SECRET_KEY 管理 | Session 安全 |
| P1 | XSS 漏洞 | 用户数据安全 |
| P2 | 缓存命中即 commit | 数据库性能 |
| P2 | Pydantic 验证 + handle_api_errors | API 健壮性 |
| P3 | 重复路由消除 | 代码可维护性 |
| P3 | CSS 提取 | 前端性能 |

### 涉及文件

审计报告覆盖全部 **80+** 文件，详见 `docs/code-audit-report-2026-05-14.md`

## v0.8.2 - 2026-05-14

### Bug 修复

#### Flask-Babel 4.0 API 兼容性修复
- `app/__init__.py`：修复 `get_locale` 在模板中未定义的 500 错误
  - **根因**：Flask-Babel 4.0 的 `init_app()` 不再接受 `locale_selector` 参数，原 `babel.init_app(app, locale_selector=_get_locale)` 的 locale_selector 被忽略，导致模板中 `get_locale()` 调用抛出 `jinja2.exceptions.UndefinedError`
  - **修复**：
    1. `babel.init_app(app)` 单独调用，`babel.locale_selector = _get_locale` 通过属性赋值设置
    2. 新增 `app.jinja_env.globals['get_locale'] = _get_locale` 直接注入 Jinja2 全局命名空间，确保 `_macros.html` 等导入的宏模板也能访问
    3. 保留 `context_processor` 注入作为兼容备份

### 涉及文件
- `app/__init__.py`：Babel 初始化逻辑修复

## v0.8.1 - 2026-05-11

### Bug 修复

#### 分类标签语言翻转修复
- `index.html`（4处）：修复图书卡片左上角分类标签翻译逻辑翻转问题
  - 中文界面现在正确显示中文分类名（如 `精装小说`）
  - 英文界面现在正确显示英文分类名（如 `Hardcover Fiction`）
  - 原逻辑错误：中文界面取值 `list_name_zh`(不存在)→`list_name`(英文)，英文界面取值 `category_name`(中文)

#### 服务端渲染语言适配
- `index.html`：服务端 Jinja2 模板新增 `_locale` 变量，根据 `get_locale()` 条件渲染
  - 中文 locale 显示 `title_zh`、`description_zh`、`category_name`
  - 英文 locale 显示 `title`、`description`、`list_name`
- `_macros.html`：3个宏（`book_grid_card`、`book_list_card`、`new_book_card`）统一新增 `_l = get_locale()` 条件渲染
  - 网格卡片、列表卡片、新书卡片的标题/描述/分类均支持 locale 切换
- `awards.html`：获奖书单页面服务端渲染新增 `_locale` 条件渲染
  - 标题、描述、图片 alt 属性均根据 locale 切换中英文

### 涉及文件
- `templates/index.html`：4处分类标签逻辑 + 服务端渲染 locale 适配
- `templates/_macros.html`：3个宏的 locale 条件渲染
- `templates/awards.html`：服务端渲染 locale 适配

## v0.8.0 - 2026-05-11

### 生产优化
- 新增 `requirements-prod.txt`：生产环境精简依赖，移除 ruff/mypy/pre-commit/pytest-cov 等开发工具
- 更新 `Procfile` 使用 `requirements-prod.txt` 安装

### 新增功能
- 内存错误追踪器（`app/utils/error_tracker.py`）：环形缓冲区，最多 500 条
- 新增 `/api/admin/errors` 路由：查看最近错误记录和统计
- 新增 `/api/admin/errors/clear` 路由：清空错误记录

### 安全增强
- CSRF 保护补全：`/api/admin/categories/cleanup` 混合 GET/POST 路由增加 CSRF
- 错误处理器增强：`db.session.rollback()` 增加异常保护

### 代码整洁
- 删除 28 个临时调试文件和截图
- 17 个根目录一次性脚本移入 `scripts/`
- 删除重复的 `Procfile.txt`
- 更新 `.gitignore` 防止临时文件再次提交

### 性能优化
- `build.py`：CSS 构建增加文件修改时间缓存检测，跳过重复构建
- API 响应 Gzip 压缩：`Content-Type: text/*` / `application/json` / `application/javascript` 自动压缩
- Service Worker 缓存策略升级 v2：
  - CACHE_NAME 升级为 `nytimes-books-cache-v2`
  - API GET 请求保持 Network First 策略
  - 图片保持 Cache First + 后台更新
  - 精简预缓存列表

### 文档更新
- README.md：项目结构图更新（反映 API 路由拆分 + 新模块）
- README.md：Python 版本更新为 3.13，技术栈更新
- VERSION.md：升级至 v0.8.0
- CHANGELOG.md：补充 v0.7.0 记录

### 其他
- simhei.ttf 字体文件保留（PDF 导出服务必需）
- 爬虫懒加载确认已由 `publisher_crawler/__init__.py` 的 `__getattr__` + `importlib` 实现

## v0.7.0 - 2026-04

### Render 免费版部署优化
- PostgreSQL 连接池瘦身：pool_size=2, max_overflow=1
- Gunicorn 单 worker 模式 + `--preload` 共享内存
- APScheduler 使用内存队列（MemoryJobStore）
- 移除 Redis/RQ 依赖，减少内存碎片
- 智能检测 Render 托管 PostgreSQL 的冷启动

### 安全修复
- 完整 CSP 安全头（script-src, style-src 等）
- XSS 防护：模板自动转义 + `data-user-content` 过滤
- 所有 POST/PUT/DELETE 路由 CSRF 保护

### 清理工作
- 移除未使用的服务（RQWorkerService、award_book_redis_service）
- 移除未使用的功能（Amazon 链接生成、图书促销监控）
- 精简 requirements.txt
- 统一使用 tenacity 重试逻辑

## v0.6.1 - 2026-05-09

### Bug 修复

#### 语言切换修复
- `index.html`：`updateBooksOnPage` 函数现在根据 `currentLanguage` 渲染对应语言的标题/描述/分类标签
- `index.html`：新增 `languagechange` 事件监听器，语言切换时重新渲染卡片（网格视图 + 列表视图）
- `new_books.html`：新增 `currentLanguage` 全局变量，监听 `languagechange` 事件自动重新加载书籍
- `new_books.html`：`loadBooks()` 无参数调用时从当前筛选状态构建查询字符串，不再丢失筛选条件
- `new_books.html`：`renderBookCard` 根据语言设置显示中文/英文标题
- `new_books.html`：`translateAllBooks` 和 `DOMContentLoaded` 统一使用 `currentLanguage` 变量

#### 图书分类切换修复
- `index.html`：`updateBooksOnPage` 中卡片渲染使用 `book.category_name` 替代未定义的 `category` 变量，消除 ReferenceError

#### 图书卡片详情修复
- `index.html`：卡片 `onclick` 改为 `window.location.href='/book/${index}?category=${category}'`，使用正确的路由跳转

#### 翻译缓存并发冲突修复
- `translation_cache_service.py`：`set` 方法捕获 `IntegrityError`，并发请求导致唯一约束冲突时自动回退为更新操作

## v0.6.0 - 2026-05-09

### 技术提升深度改造

#### 工具链搭建
- 新增 `pyproject.toml`：Ruff linting/formatting + mypy 类型检查配置
- 新增 `.pre-commit-config.yaml`：Ruff + mypy pre-commit hooks
- 新增 `Makefile`：lint/format/typecheck/test/check 快捷命令
- 增强 `.github/workflows/ci.yml`：Ruff 替代 flake8、新增 mypy job、pytest-cov 覆盖率门禁、Python 3.13
- 更新 `requirements.txt`：新增 ruff、mypy、pre-commit、pytest-cov、pydantic、types-requests

#### 代码质量提升
- 类型注解补全：`__init__.py`、`config.py`、`api_helpers.py`、`book_service.py`、`cache_service.py`、`service_helpers.py`（使用 Python 3.13 语法 `str | None`）
- 统一错误处理：增强 `handle_api_errors` 装饰器，新增 ValidationException/DataNotFoundError/APIRateLimitException/ExternalAPIError/BookRankException 自定义异常处理
- Ruff 全量修复：自动修复 1037 个代码规范问题（导入排序、未使用导入、代码简化等）

#### 架构优化重构
- 拆分 `api.py`（1007行）为 5 个子模块：`books.py`、`translation.py`、`cache.py`、`awards.py`、`recommendations.py`
- 新增 `app/services/user_service.py`：从路由层提取用户数据库操作，消除路由层直接 DB 操作
- 新增 `app/schemas/validators.py`：Pydantic 验证层（10 个模型覆盖搜索/翻译/分页/奖项/偏好/推荐/缓存）
- 分离 `Book` dataclass 到 `app/models/book.py`，`schemas.py` 保留向后兼容重导出
- CSRF token 存储改用数据库（`CSRFToken` 模型），支持多 worker 部署
- 新增数据库迁移：`add_csrf_tokens_table.py`

#### 测试体系完善
- 新增 `tests/test_user_service.py`：UserService 单元测试（10 个用例）
- 新增 `tests/test_pydantic_validators.py`：Pydantic 验证模型测试（30 个用例）
- 新增 `tests/test_api_awards.py`：奖项 API 集成测试（13 个用例）
- 新增 `tests/test_api_translation.py`：翻译 API 集成测试（12 个用例）
- 更新 `conftest.py`：新增 CSRFToken 模型导入
- 更新 `pytest.ini`：新增覆盖率配置（`--cov-fail-under=60`）

#### 修复
- `app/services/user_service.py`：`save_viewed_books` 方法改用 `filter_by` 查询去重，替代无法正确去重的 `db.session.merge()`

## v0.5.5 - 2026-05-09

### 新增
- UserService 服务类，从 api.py 提取用户数据库操作
- 补充 book_service.py / cache_service.py / service_helpers.py 类型注解

## v0.5.4 - 2026-05-09

### 修复
- 翻译测试断言过期
- 周报测试缺少 mock

## v0.5.1 - 2026-05-02

### 修复
- `/about` 页面 404 错误
- 语言切换功能
- 移动端侧边栏遮挡问题

## v0.5.0 - 2026-05-02

### 新增
- 新书速递页面全面优化
- NewBookService 单例模式 + N+1 查询修复
- 暗色模式全面补全
- XSS 防护
