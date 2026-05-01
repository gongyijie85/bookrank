# Changelog

## [1.7.5] - 2026-05-02

### 模型名称统一
- **翻译状态API显示名称修复**：统一 `api.py` 中两处 `ZhipuAI GLM-4-Flash` 为 `ZhipuAI GLM-4.7-Flash`，保持与实际使用的模型名 `glm-4.7-flash` 一致

### 翻译质量修复
- **翻译标题末尾"译"字残留（P0）**：
  - 问题：所有翻译标题显示为"希望升起译"、"通讯员译"等，末尾残留"译"字
  - 根因：两层故障链——① `quick_clean_translation` 仅在检测到脏标记时才调用 `clean_translation_text`，但"译"不在脏标记列表中；② `Book.to_dict()` 直接返回 `asdict()` 不做任何清洗
  - 修复：
    - `quick_clean_translation` 增加"译"后缀正则检测，命中即调用完整清洗
    - `Book.to_dict()` 和 `AwardBook.to_dict()` 对 `title_zh`、`description_zh`、`details_zh` 应用 `quick_clean_translation`
- **数据库脏数据一次性清理（P1）**：
  - 首次部署启动时，自动扫描 `BookMetadata`、`AwardBook`、`NewBook` 表中的 `title_zh` 字段，修复所有残留"译"字、Markdown标记等脏数据
  - 清理过程在 `_init_database_lazy()` 中执行，不影响正常启动

## [1.7.4] - 2026-05-02

### 稳定性修复
- **邮件发送网络不可达错误处理（P0）**：
  - 问题：Render 免费版阻止 SMTP 出站连接，导致 `[Errno 101] Network is unreachable` 错误，日志大量 ERROR 级别报错
  - 修复：检测 `Network is unreachable` 错误，降级为 WARNING 级别并给出明确提示（周报已保存到数据库，可在网页端查看）
- **周报生成竞态条件（P0）**：
  - 问题：用户首次访问时，7 个分类的数据刷新各自触发 `_notify_data_refreshed()` 回调，导致 7 次并发周报生成请求
  - 修复：增加 5 分钟冷却期（`_REPORT_TRIGGER_COOLDOWN`），同一时间窗口内只允许触发一次周报生成
- **数据库迁移重复执行（P1）**：
  - 问题：每次部署首次请求都重新运行 `flask_migrate.upgrade()`，即使迁移已是最新版本
  - 修复：在执行迁移前先查询 `alembic_version` 表，如果已有版本记录则跳过迁移

## [1.7.3] - 2026-05-01

### 安全修复
- **Admin API 无认证保护（P0）**：
  - 问题：所有管理端点（同步封面、重新生成周报、清理缓存等）仅靠 CSRF Token 保护，缺少身份认证
  - 修复：新增 `admin_required` 装饰器，通过 `ADMIN_SECRET` 环境变量或 session 验证管理员身份；所有 admin 路由添加 `@admin_required`

### 稳定性修复
- **翻译线程竞态条件（P0）**：
  - 问题：`_translation_thread_active` 标志的读写没有加锁，多线程并发时可能重复启动翻译线程
  - 修复：使用 `threading.Lock` 保护 `_translation_thread_active` 的读写，采用双重检查锁模式
- **数据库初始化竞态条件（P0）**：
  - 问题：`run.py` 中 `_db_initialized` 全局变量非线程安全，多线程并发时可能重复初始化
  - 修复：使用 `threading.Lock` 实现双重检查锁，确保数据库初始化只执行一次
- **IP 限流器内存泄漏（P1）**：
  - 问题：`IPRateLimiter._requests` 字典只增不减，长期运行内存膨胀
  - 修复：当记录数超过 10000 时自动清理过期条目，防止内存无限增长

### 性能优化
- **N+1 查询问题（P1）**：
  - 问题：出版社页面循环调用 `pub.books.count()`、获奖页面循环调用 `AwardBook.query.filter_by().count()`，触发 N+1 查询
  - 修复：使用 `sqlalchemy.func.count` + `group_by` 批量查询替代循环计数
- **同步翻译阻塞请求（P1）**：
  - 问题：`_merge_or_translate_book()` 在请求线程中同步调用翻译 API（最多 3 次），导致 3-5 秒延迟
  - 修复：改为仅从数据库读取已有翻译，未翻译的启动后台守护线程异步翻译

### 其他修复
- **导出路由名实不符**：
  - 问题：`/export/excel` 路由实际导出 CSV 格式
  - 修复：路由改为 `/export/csv`，同步更新前端引用

## [1.7.2] - 2026-05-01

### 修复
- **翻译文本引号替换无效代码**：
  - 问题：`clean_translation_text()` 中 `text.replace('\u201c', '\u201c')` 将字符替换成自身，完全无效
  - 修复：移除两行无效的引号替换代码
- **单字"译"作为脏标记误判**：
  - 问题：`_DIRTY_MARKERS` 包含单字 `'译'`，导致任何含"译"的正常文本（如"翻译""编译"）都被误判为脏数据
  - 修复：从 `_DIRTY_MARKERS` 移除 `'译'`；末尾"译"字后缀清理已由 `clean_translation_text()` 的正则独立处理
- **`_translate_book_info` 未翻译 author 字段**：
  - 问题：系统已支持 `author_zh` 字段，但 `_translate_book_info()` 的翻译字段列表遗漏了 author
  - 修复：在翻译字段列表中增加 `('author', 'author_zh', 'author')`

### 简化
- **清除 `book_service.py` 冗余导入**：移除 `_batch_get_translations`、`save_book_translation`、`get_latest_cache_time` 中重复的局部导入（`BookMetadata`、`db`、`datetime`），统一使用文件顶部导入
- **提取翻译缓存服务共享逻辑**：`ZhipuTranslationService` 和 `HybridTranslationService` 中重复的 `_get_cache_service` 方法，提取为模块级 `_get_shared_cache_service()` 函数，避免重复初始化

## [1.7.1] - 2026-04-30

### 修复
- **书名翻译后错误附加"译"字**：
  - 问题：GLM 模型翻译书名时偶尔在末尾添加"译"字（如"希望升起译"），所有分类的畅销书均受影响
  - 根因：`_DIRTY_MARKERS` 未包含"译"字，导致 `quick_clean_translation()` 误判脏数据为干净，直接返回缓存的脏翻译
  - 修复：将"译"加入 `_DIRTY_MARKERS`；增强 `clean_translation_text()` 正则，处理行尾、换行前、行首各种"译"字变体；在智谱AI Prompt 中明确严禁添加"译"字标记
- **作者名未翻译显示**：
  - 问题：首页畅销书排行榜仅显示英文作者名
  - 修复：`Book` 数据类新增 `author_zh` 字段；`BookMetadata` 表新增 `author_zh` 列；`BookService` 批量获取并赋值作者中文名；首页模板优先显示 `author_zh`

### 新增文件
- `scripts/fix_translation_suffix.py`：数据库脏数据清理脚本，支持 `--dry-run` 预览模式，遍历 `book_metadata`、`translation_cache` 和 `static/data/*.json` 清理"译"字残留

## [1.7.0] - 2026-04-30

### 优化
- **出版社官网直接爬取**：将 Hachette、HarperCollins、Macmillan 三个出版社从 Google Books 间接搜索切换为直接官网爬取（或混合策略），获取更准确、更新的新书数据
  - `HachetteCrawler`：直接爬取 hachettebookgroup.com 首页"New Releases"标签页，进入详情页获取完整数据（ISBN、作者、封面等）
  - `HarperCollinsCrawler`：爬取 harpercollins.com 首页 NEW RELEASES 轮播，从图片 alt 属性提取标题/作者/ISBN 信息
  - `MacmillanCrawler`：采用多印记查询（Macmillan、St. Martin's Press、Tor Books 等8个印记）+ Sitemap ISBN 补充的双路策略，解决官网 Cloudflare 封锁问题
- **爬虫注册与迁移**：更新 `new_book_service.py` 中的默认出版社配置和爬虫迁移映射

### 修复
- **Macmillan 返回旧书**：
  - 问题：Macmillan 爬虫返回 1998-2022 年的旧书，而非近期新书
  - 根因：Sitemap ISBN 补充路径在 `year_from=None` 时跳过年份过滤；`_lookup_isbn` 返回 `publication_date` 为字符串类型（应为 `date` 对象），导致比较失败
  - 修复：统一使用 `min_year` 默认值（当前年-2）进行年份过滤；`_lookup_isbn` 改用 `_parse_date_string` 返回 `date` 对象
- **HarperCollins robots.txt 误拦截**：
  - 问题：HarperCollins 的 robots.txt 被 Cloudflare 拦截返回 HTML，导致 `RobotFileParser` 无法解析有效规则，`can_fetch()` 始终返回 False
  - 修复：覆盖 `_is_url_allowed()` 方法，绕过无效的 robots.txt 检查
- **Macmillan Google Books 查询覆盖不足**：
  - 问题：仅查询 `publisher:Macmillan`，遗漏旗下 St. Martin's Press、Tor Books 等主要印记
  - 修复：新增 `MACMILLAN_IMPRINTS` 列表，通过 `inpublisher:` 分别查询8个印记
- **Sitemap 采样固定**：
  - 问题：始终检查 sitemap 28-31，ISBN 集合固定导致结果缺乏多样性
  - 修复：扩展至 `range(1, 32)`，每次随机采样6个 sitemap 并打乱 ISBN 顺序

### 新增文件
- `app/services/publisher_crawler/hachette.py`：Hachette 官网爬虫
- `app/services/publisher_crawler/harpercollins.py`：HarperCollins 官网爬虫
- `app/services/publisher_crawler/macmillan.py`：Macmillan 多印记+Sitemap 爬虫

### 修改文件
- `app/services/new_book_service.py`：更新默认出版社爬虫类名和迁移映射
- `app/services/publisher_crawler/__init__.py`：更新模块文档

## [1.6.1] - 2026-04-30

### 项目架构
- **通用工具独立开源**：
  - 从主项目提取 `IPRateLimiter` 为独立 Python 包 `flask-ip-limiter`
  - 从主项目提取 `BaseCrawler` 为独立 Python 包 `web-crawler-base`
  - 两个通用工具采用 MIT 许可证发布到 GitHub
  - 主项目 BookRank 保持私有闭源（业务属性、法律风险）
  - 开源仓库地址：
    - https://github.com/gongyijie85/flask-ip-limiter
    - https://github.com/gongyijie85/web-crawler-base
- **清理工作**：
  - 恢复主项目 `.gitignore` 到初始状态
  - 删除主项目中的 LICENSE、CONTRIBUTING.md 等开源准备文件
  - 保留 `open-source-tools/` 目录作为本地开源工具的工作区

### 说明
- 主项目闭源理由：属于给上海外文图书有限公司的业务项目，包含出版社数据、奖项收录规则、周报格式等商业机密
- 通用工具开源理由：限流器、爬虫基类等模块无业务逻辑，适合展示技术能力、积累社区贡献

## [1.6.0] - 2026-04-30

### 新功能
- **Google Books 出版社搜索爬虫**：
  - 新增 `GoogleBooksPublisherCrawler` 基类，通过 Google Books API 的 `inpublisher:` 语法按出版社名搜索新书
  - 新增 `SimonSchusterGoogleCrawler`：Simon & Schuster 出版社新书搜索
  - 新增 `HachetteGoogleCrawler`：Hachette 出版社新书搜索（含子出版社 Grand Central、Little Brown、Orbit 等）
  - 新增 `HarperCollinsGoogleCrawler`：HarperCollins 出版社新书搜索
  - 新增 `MacmillanGoogleCrawler`：Macmillan 出版社新书搜索
  - 优势：比 HTML 爬虫稳定可靠，不受网站结构变化和反爬措施影响

- **RSS Feed 爬虫**：
  - 新增 `PublisherRSSCrawler` 基类，支持 RSS 2.0 和 Atom 格式解析
  - 新增企鹅兰登、HarperCollins、Simon & Schuster 的 RSS 爬虫子类
  - 作为 HTML 爬虫的备选方案

- **自动迁移机制**：
  - `init_publishers()` 方法增加爬虫迁移逻辑
  - 自动将失效的 HTML 爬虫（SimonSchusterCrawler、HachetteCrawler、HarperCollinsCrawler、MacmillanCrawler）迁移到 Google Books 搜索爬虫
  - 无需手动干预，应用启动时自动完成

### 优化
- **get_crawler 方法**：支持所有 Google Books 系列爬虫的 API Key 注入
- **爬虫注册表**：新增 7 个爬虫类到统一注册入口

### 修复
- **Google Books API 返回未来占位日期**：
  - 问题：Google Books API 常返回 `2030-12-30`、`2030-12-31` 等占位日期，被当作有效新书数据
  - 根因：`_is_recent_book` 方法只检查年份下限（>= min_year），未检查上限
  - 修复：增加上限检查，过滤掉超过当前年份+1年的占位日期
  - 修复文件：`app/services/publisher_crawler/google_books.py`

- **Simon & Schuster、Hachette、HarperCollins、Macmillan 数据为空**：
  - 根因：HTML 爬虫的 CSS 选择器不匹配网站当前结构，且存在反爬和 JS 渲染问题
  - 修复：切换到 Google Books API 按出版社名搜索，数据源从 0 变为有数据

### 新增文件
- `app/services/publisher_crawler/google_books_publisher.py`：Google Books 出版社搜索爬虫
- `app/services/publisher_crawler/rss_crawler.py`：RSS Feed 爬虫
- `scripts/migrate_publishers.py`：出版社爬虫迁移脚本

### 修改文件
- `app/services/publisher_crawler/__init__.py`：注册新爬虫
- `app/services/new_book_service.py`：更新默认出版社配置和迁移逻辑、get_crawler 支持新爬虫
- `app/services/publisher_crawler/google_books.py`：修复未来占位日期过滤逻辑

## [1.5.1] - 2026-04-30

### 修复
- **周报详情书名截断（BUG-13）**：
  - 问题：周报详情页书名显示为截断形式（如《天》应为《天堂十八日》）
  - 根因：_format_book_title 函数中的正则误将书名末尾中文识别为作者名并删除
  - 修复：移除会导致书名截断的正则表达式
  - 修复文件：app/services/weekly_report_service.py、app/routes/api.py

- **图书详情页未翻译**：
  - 问题：部分详情页显示英文标题，即使数据库已有翻译
  - 根因：_merge_or_translate_book 提前返回条件过于宽泛
  - 修复：将提前返回条件改为三个字段都有翻译才跳过
  - 修复文件：app/routes/main.py

- **Analytics session-stats 500错误**：
  - 问题：/api/analytics/session-stats 返回500
  - 根因：SQL嵌套聚合函数 avg(count(...)) 在PostgreSQL中不合法
  - 修复：拆分为子查询 + Python计算
  - 修复文件：app/services/analytics_service.py

### 优化
- **清理调试代码**：
  - 移除 main.py 周报详情路由中的 traceback.format_exc() 调试输出
  - 移除 _parse_report_content 中已禁用的书名清理注释代码
  - 恢复正常的错误页面渲染

## [1.5.0] - 2026-04-29

### 修复
- **CSP阻止Chart.js source map**：
  - 问题：控制台报错 `Connecting to 'https://cdn.jsdelivr.net/npm/chart.umd.min.js.map' violates Content Security Policy directive: "connect-src 'self'"`
  - 修复：将 `connect-src 'self'` 改为 `connect-src 'self' https://cdn.jsdelivr.net`
  - 修复文件：`app/__init__.py`

- **Service Worker路径不匹配**：
  - 问题：`/sw.js` 返回404，实际文件在 `/static/service-worker.js`
  - 修复：注册路径改为 `/static/service-worker.js`
  - 修复文件：`static/js/app.js`

- **新书分类数据污染**：
  - 问题：企鹅兰登的书籍分类显示为营销文案（如 `what type of reader is your child? take the quiz! learn more >`）
  - 修复：添加分类校验方法 `_sanitize_category`，过滤长度超30字符、包含营销关键词、特殊字符的无效分类
  - 新增：数据库清洗脚本 `scripts/cleanup_categories.py`
  - 新增：管理员API端点 `/api/admin/categories/cleanup`（支持预览和执行模式）
  - 修复文件：`app/services/new_book_service.py`、`app/routes/api.py`

- **周报书名重复书名号**：
  - 问题：书名显示为 `《《难民》》`（数据库已含《》，代码又加了一层）
  - 修复：添加 `_format_book_title` 函数，先去除已有书名号再统一添加
  - 修复：添加 `_clean_double_brackets` 后处理函数，对AI生成的摘要统一清理双书名号
  - 修复：添加 `clean_brackets` Jinja2模板过滤器，对已存储的周报summary进行渲染时清理
  - 修复：周报生成时对content JSON中的书名统一应用 `_format_book_title`
  - 新增：管理员API端点 `/api/admin/reports/clean-brackets`（支持预览和执行模式，清理已有数据库记录）
  - 修复文件：`app/services/weekly_report_service.py`、`app/__init__.py`、`templates/weekly_report_detail.html`、`app/routes/api.py`

- **表单无障碍标签缺失**：
  - 问题：多个输入框缺少 `aria-label` 属性，控制台警告 `No label associated with a form field`
  - 修复：为新书页面、周报页面、出版社页面的输入框添加 `aria-label` 和 `for` 属性
  - 修复文件：`templates/new_books.html`、`templates/weekly_reports.html`、`templates/publishers.html`

- **周报邮件发送失败 `current_app` 未定义**：
  - 问题：`_embed_covers_in_html` 函数第337行使用 `current_app` 但未导入，导致周报邮件发送失败
  - 修复：在函数内部添加 `from flask import current_app` 导入
  - 修复文件：`app/tasks/weekly_report_task.py`

- **书名翻译污染（作者名、描述、markdown混入）**：
  - 问题：AI翻译返回过长内容（如 `**书名：** 《养兔记》 **作者：** ...`、`思考，快与慢 丹尼尔·卡尼曼译`、`《掌控习惯》詹姆斯·克利尔 这是一本关于习惯养成的实用指南...`），直接存入数据库
  - 根因1：翻译缓存读取时未应用后处理函数 `clean_translation_text`，旧缓存中的脏数据直接返回
  - 根因2：前端 `/api/translate` 调用未传递 `field_type` 参数，导致书名翻译未经过 `_clean_title_text` 清理
  - 修复：
    - `HybridTranslationService.translate` 和 `translate_batch`：缓存命中时也应用 `clean_translation_text`
    - `ZhipuTranslationService.translate_batch`：缓存命中时也应用 `clean_translation_text`
    - 新增 `_clean_title_text` 函数：处理作者名混入（间隔号分割）、长描述截断、双书名号等
    - `clean_translation_text`：`field_type='title'` 时调用 `_clean_title_text` 替代 `_add_book_title_marks`
    - `/api/translate` 端点：新增 `field_type` 参数，传递给翻译服务
    - 前端 `api.js`：`translateText` 方法新增 `fieldType` 参数
    - 前端 `index.html`：`translateSingleBook` 为标题/描述/详情分别传递 `field_type='title'/'description'/'details'`
    - 新增管理员API `/api/admin/translations/cleanup`：清理已有脏翻译缓存和BookMetadata数据
    - `is_dirty` 检测增强：新增间隔号+书名号组合模式、书名号后长尾内容、多行长文本检测
  - 修复文件：`app/services/zhipu_translation_service.py`、`app/utils/api_helpers.py`、`app/routes/api.py`、`static/js/api.js`、`templates/index.html`

## [1.4.9] - 2026-04-29

### 修复
- **API限流过严导致首页429错误**：
  - 问题：全站API限流默认值20次/60秒，首页加载时需发送约52个请求（7个分类预加载 + 45个翻译请求），导致大量429错误
  - 修复：将 `API_RATE_LIMIT` 默认值从20提高到100
  - 优化：轻量级接口（`/api/csrf-token`、`/api/health`）排除在限流之外
  - 修复文件：
    - `app/config.py`：`API_RATE_LIMIT` 默认值从20改为100
    - `app/__init__.py`：添加排除路径检查，轻量级接口不计入限流

- **周报Markdown未渲染**：
  - 问题：周报详情页和列表页直接显示原始Markdown文本（#、##、-、**等语法符号）
  - 修复：引入 `mistune` 库，注册Jinja2过滤器 `markdown`，将Markdown转换为HTML
  - 修复文件：
    - `requirements.txt`：添加 `mistune==3.2.0`
    - `app/__init__.py`：添加 `_register_jinja_filters` 函数，注册 `markdown` 过滤器
    - `templates/weekly_report_detail.html`：使用 `{{ report.summary | markdown | safe }}` 渲染
    - `templates/weekly_reports.html`：使用 `{{ report.summary | markdown | striptags | truncate(200) }}` 渲染摘要

## [1.4.8] - 2026-04-29

### 修复
- **翻译系统全面修复（"译"后缀、Markdown格式、未翻译内容）**：
  - **问题1：标题带"译"后缀**：GLM-4-Flash模型翻译时输出"希望升起译"、"通讯员译"等，后处理未清除
  - **问题2：详情页描述未翻译**：`book_detail.html` 直接使用 `book.description` 而非翻译版本
  - **问题3：获奖书单卡片未翻译**：`awards.html` 的卡片和列表描述显示英文原文
  - **问题4：Markdown格式残留**：翻译描述中出现 `**粗体**`、`*斜体*` 等markdown标记
  - **问题5：周报详情页alt属性未翻译**：封面图片alt属性显示英文标题
  - **问题6：详情API返回英文**：`/api/book-details/{isbn}` 端点不包含翻译逻辑
  - **修复文件**：
    - `app/utils/api_helpers.py`：增强 `clean_translation_text` 函数，新增 `_strip_markdown` 辅助函数，清除Markdown格式、"译"后缀、翻译前缀
    - `templates/book_detail.html`：简介和详细信息优先使用 `description_zh` 和 `details_zh`
    - `templates/awards.html`：卡片和列表描述优先使用 `description_zh`
    - `templates/weekly_report_detail.html`：所有封面图片alt属性使用翻译标题
    - `app/routes/api.py`：`/api/book-details/{isbn}` 端点增加数据库翻译查询和同步翻译能力，返回 `details_zh` 字段
    - `fix_translation_data.py`：增强脏数据检测，新增"译"后缀和Markdown格式检测
  - **说明**：新增 `_strip_markdown` 函数清除 `**粗体**`、`__粗体__`、`*斜体*`、`` `代码` ``、`# 标题`、`[链接](url)` 等格式；脏数据清理脚本已增强，部署后需运行 `python fix_translation_data.py` 清理数据库中已有脏数据

## [1.4.7] - 2026-04-28

### 修复
- **页面书名/简介翻译显示问题**：
  - 问题：模板中直接使用 `book.title` 和 `book.description`，未优先使用翻译后的 `book.title_zh` 和 `book.description_zh`
  - 问题：从 Render 页面看到 "身体决定分数译" 等翻译质量差且带"译"字污染
  - 修复文件：
    - `templates/index.html`：网格视图和列表视图的书名、简介优先使用翻译版本
    - `templates/_macros.html`：宏模板中的书名、简介优先使用翻译版本
    - `templates/weekly_report_detail.html`：周报详情页所有书籍列表使用翻译书名
    - `templates/emails/weekly_report.html`：邮件模板使用翻译书名
  - 说明：当 `title_zh` 或 `description_zh` 存在时优先显示中文翻译，否则回退到英文原文

## [1.4.6] - 2026-04-28

### 修复
- **出版社爬虫 403 + Crawl4AI 失败（Render 兼容性问题）**：
  - 问题：Macmillan、Simon & Schuster、Hachette、HarperCollins、Penguin Random House 官网均有 Cloudflare 防护，requests 直接 403
  - 问题：Render 免费版未安装 Playwright，Crawl4AI 降级方案报错 `Executable doesn't exist at /home/runner/.cache/ms-playwright/...`
  - 解决方案：5 个出版社爬虫全部改为继承 `GoogleBooksCrawler`，使用 Google Books API 的 `publisher:` 查询筛选
  - Macmillan：`publisher:Macmillan`
  - Simon & Schuster：`publisher:"Simon & Schuster"`
  - Hachette：`publisher:Hachette`
  - HarperCollins：`publisher:HarperCollins`
  - Penguin Random House：`publisher:"Penguin Random House"`
  - 所有爬虫添加 `orderBy: newest` 参数，优先返回最新出版的书籍
  - 优点：无需浏览器、不受 Cloudflare 影响、在 Render 免费版上稳定运行

## [1.4.5] - 2026-04-27

### 修复
- **邮件封面图缺失（根因修复）**：
  - `book_row()` 函数只对 `cover.startswith('http')` 的封面生成 `<img>` 标签，但 `ImageCacheService` 返回的是相对路径 `/cache/images/xxx.jpg`，导致所有缓存封面被跳过显示为占位符
  - 修改为：对所有有 cover 值的封面都生成 `<img>` 标签，后续 `_embed_covers_in_html` 统一处理
- **邮件 Base64 嵌入增强**：`_embed_covers_in_html` 新增本地文件读取优先策略——相对路径图片先从本地文件系统读取转 Base64，再尝试拼接 `BASE_URL` 下载
- **图片缓存目录不一致**：`weekly_report_task.py` 中 `ImageCacheService(cache_dir=Path('static/cache'))` 与路由 `/cache/images/` 读取目录 `cache/images/` 不一致，修正为 `Path('cache/images')`
- **周报数据保存原始图片 URL**：`book._original_cover` 保存 NYT 原始图片 URL，写入周报 content JSON 中，作为缓存图片加载失败的兜底
- **网页周报封面兜底**：详情页 JavaScript 为所有 `.book-cover` 图片添加 `onerror` 回调，本地缓存图片 404 时自动切换到 NYT 原始 URL
- **邮件模板封面兜底**：`emails/weekly_report.html` 使用 `cover or original_cover` 确保有兜底图源

## [1.4.4] - 2026-04-27

### 修复
- **邮件封面图仍不显示（根本原因）**：
  - 发现问题：`ImageCacheService.get_cached_image_url()` 返回的是相对路径（如 `/cache/images/abc.jpg`），邮件客户端无法访问
  - 修复 `_embed_covers_in_html`：自动将相对路径补全为完整 URL（使用 `BASE_URL` 配置或 `request.url_root`）
  - 新增 `BASE_URL` 配置项：`config.py` 和 `.env.example` 中添加网站基础 URL 配置
  - 保留 Base64 内联：补全后的完整 URL 仍然会被转换为 Base64 内联嵌入

## [1.4.3] - 2026-04-27

### 修复
- **邮件封面图仍不显示**：
  - Google Books 图片反爬：添加 `Referer: https://books.google.com/` 和完整 User-Agent
  - 空值处理：`book_row()` 中 cover 字段添加 `or ''` 兜底，检查 `startswith('http')`
  - 调试日志：`_embed_covers_in_html` 添加成功/失败计数日志，方便排查
  - 内容类型校验：确保 URL 返回的是图片内容（`Content-Type: image/*`）

## [1.4.2] - 2026-04-27

### 修复
- **邮件封面图不显示**：邮件客户端默认阻止加载外部图片，将封面图从外部 URL 改为 Base64 内联嵌入（`_fetch_image_as_base64` + `_embed_covers_in_html`），确保 Gmail/Outlook 等客户端正常显示封面

## [1.4.1] - 2026-04-27

### 修复
- **数据库连接池耗尽**：`SQLALCHEMY_ENGINE_OPTIONS` pool_size 从 1 增加到 2，避免并发查询时连接池耗尽（Render 日志：`QueuePool limit of size 1 overflow 1 reached`）
- **周报重复生成**：添加 `_weekly_report_lock` 线程锁，防止数据刷新回调在短时间内多次触发导致重复生成和邮件发送
- **邮件认证错误提示**：检测到 Gmail `BadCredentials` 错误时，日志明确提示用户生成"应用专用密码"(App Password) 并给出操作步骤
- **env.example 邮件密码说明**：添加详细注释说明 Gmail 应用专用密码的获取步骤

## [1.4.0] - 2026-04-26

### 新增
- `MAIL_RECIPIENTS` 配置项：支持逗号分隔多个收件人邮箱
- `.env.example` 邮件服务配置区块：SMTP 服务器、端口、用户名、密码、收件人等完整说明
- BookService 数据刷新回调机制：`on_data_refreshed()` + `_notify_data_refreshed()`，排行榜数据刷新后自动触发周报生成

### 优化
- 周报生成时机：去掉"仅在周五生成"限制，改为排行榜数据刷新后自动触发；周一/二/三生成上周周报，周四及以后生成本周周报（NYT排行榜周三更新）
- 后台线程：周报从"每日86400秒轮询"改为"启动检查一次+回调驱动"
- 周报邮件封面图：默认摘要5个区块（重要变化/新上榜/排名上升/持续上榜/推荐书籍）全部添加封面图（max-width:60px按比例缩放），每区块从3本扩展到5本
- Jinja 模板推荐书籍区块添加封面图（flex布局，无封面显示📖占位）
- 周报生成完成后自动调用 `send_weekly_report_email()` 发送邮件到配置的收件人
- 健壮化 SMTP 收件人读取：空字符串和空格不报错

### 删除
- 删除废弃的 `email_service.py`（使用 Flask-Mail 但从未被调用）

### 测试
- 新增 7 个测试：SMTP 配置(3)、数据刷新回调(2)、周报封面图(2)
- 替换废弃的 `TestEmailService` 为 `TestSmtpEmailConfig`

## [1.3.0] - 2026-04-26

### 重构
- 企鹅兰登爬虫迁移到 MixedCrawl4AICrawler 基类：从 529 行缩减到 94 行，消除约 435 行重复代码（Crawl4AI降级逻辑、数据提取方法、业务流程方法）

### 修复
- 修复 SimonSchusterCrawler `__init__` 重复定义 bug：合并两个 `__init__`，恢复 `respect_robots_txt = False` 配置
- 修复 MacmillanCrawler `__init__` 重复定义 bug：合并两个 `__init__`，统一 `request_delay = 1.3`，恢复 `respect_robots_txt = False`

### 优化
- 统一爬虫注册机制：删除 `new_book_service.py` 的 `CRAWLER_MAP`（29行重复映射），统一使用 `publisher_crawler.__init__` 的 `CRAWLER_REGISTRY`
- `__init__.py` 注册机制增强：使用 `_CRAWLER_MODULES` 模块映射表驱动，`__getattr__` 延迟导入也由映射表驱动
- 清理 OpenLibraryCrawler 中 `unittest.mock.Mock` 的生产代码依赖，替换为 `SimpleResponse` 轻量包装类

### 删除
- 删除废弃的 `crawl4ai_base.py`（`Crawl4AICrawler` 和 `HybridCrawlerMixin` 无使用方，220行死代码）

### 测试
- 新增 `tests/test_publisher_crawler.py`，44个测试覆盖：BaseCrawler通用方法(16)、BookInfo(3)、SimpleResponse(3)、企鹅兰登迁移(3)、__init__修复(4)、注册机制(3)、GoogleBooks解析(7)、OpenLibrary解析(4)

## [1.2.0] - 2026-04-26

### 新增
- 字段感知提示词策略：按 title/description/details/author/text 使用差异化 prompt，从源头减少 AI 输出污染
- 翻译结果质量校验 `_validate_translation()`：检测污染标记和未翻译内容，拦截脏数据写入缓存
- 智谱AI翻译 tenacity 重试机制：3次重试，指数退避，应对网络抖动
- Google备用翻译重试机制：2次重试，线性退避
- 翻译缓存版本控制 `CACHE_VERSION=2`：旧版本缓存自动失效，确保翻译质量升级后旧数据不残留

### 优化
- 统一翻译后处理逻辑：消除 `zhipu_translation_service.py`、`api_helpers.py`、`fix_translation_data.py` 三处重复代码，建立 `api_helpers.py` 为权威入口
- `HybridTranslationService.translate_batch()` 改为缓存预检+并行翻译（默认 max_workers=2 适配 Render 免费 512MB）
- `translate_author_name()` 使用 `field_type='author'` 获取专用作者名翻译提示词
- 后处理增强：新增"翻译：/译文："前缀清理、字段内容智能提取、统一引号、多余空行去除

### 修复
- 添加 `deep-translator>=1.11.0` 到 requirements.txt（此前备用翻译链路因缺少依赖可能断裂）

### 测试
- 翻译测试从12个扩展至35个，新增：后处理统一函数测试(10)、字段感知提示词测试(5)、质量校验测试(5)、缓存版本测试(1)、免费翻译服务测试(2)

## [1.1.0] - 2026-04-24

### 删除
- 移除 `multi_translation_service.py`（未被任何代码引用的废弃文件）
- 移除 `translation_service.py`（已被 `zhipu_translation_service.py` 完全替代）
- 移除 `free_translation_service.py` 中已停运的 `LibreTranslatePublicService` 类及4个不可用的公共实例

### 修复
- 修复模型名称不一致：全量统一为 `glm-4.7-flash`（涉及 schemas.py、translation_cache_service.py、api.py、zhipu_translation_service.py）
- 修复 `translation_cache_service.py` 中 `search()` 方法的SQL注入风险（用户输入未转义LIKE通配符）
- 修复 `new_books.py` 4个POST路由缺少CSRF保护的问题
- 修复 `api.py` 中 `request.json.get()` 在请求体为空时抛出 `AttributeError` 的bug
- 修复 `api.py` 中两处 `WeeklyReportService` 构造函数传参错误（多余参数）
- 修复 `weekly_report_service.py` 对已删除 `translation_service.py` 的导入引用

### 重构
- 将 `csrf_protect`/`get_csrf_token`/`validate_csrf_token` 从 `api.py` 提取到 `utils/api_helpers.py` 作为公共工具
- 将 `_clean_translation_text` 从 `main.py` 提取到 `utils/api_helpers.py`（重命名为 `clean_translation_text`），消除重复代码
- 更新 `utils/__init__.py` 导出列表，增加 `csrf_protect`/`get_csrf_token`/`clean_translation_text`
