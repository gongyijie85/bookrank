# Changelog

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
