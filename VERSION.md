# BookRank 版本信息

**当前版本**：v0.9.18
**发布日期**：2026-05-22
**Python 版本**：3.13
**Flask 版本**：3.1.3

## 版本亮点

### v0.9.18 (2026-05-22) — 项目清理释放磁盘空间
- **删除类型检查缓存**：移除 `.mypy_cache/`（约 17MB）
- **删除应用缓存**：移除 `cache/` 目录
- **删除临时文件**：移除测试数据库、旧数据库、翻译缓存、临时 Excel 文件
- **释放空间**：总计释放约 18MB 磁盘空间

### v0.9.17 (2026-05-19) — 修复 CSRF Token SAWarning + Render 数据库恢复
- **SAWarning 修复**：CSRFToken 模型添加 `__mapper_args__ = {'confirm_deleted_rows': False}`
- **PostgreSQL 时区修复**：移除不支持的 timezone 参数，改用 SQL 语句设置
- **Render 生产环境恢复**：重建数据库并重新部署成功

### v0.9.16 (2026-05-18) — ISBN 格式严格校验 + 详情页硬编码中文修复
- **ISBN 严格格式校验**: ISBN-13 必须以 978/979 开头且 13 位纯数字；ISBN-10 必须 10 位（末位可为 X）
- **出版社黑名单扩展**: 覆盖 NYT API 所有已知无效分类名（精装/平装/虚构/非虚构/青少年/儿童/建议读物等）
- **详情页硬编码中文消除**: toggleOriginal() / switchDetailLang() 改用 t() 翻译函数，新增 hide_original 键值

### v0.9.15 (2026-05-18) — 修复语言按钮不更新 + ISBN 显示问题
- **语言切换按钮即时更新**: 三重保障确保 #lang-current 始终显示正确语言
- **ISBN/出版社数据验证**: 过滤无效值，避免显示分类名等错误数据
- **try-catch 防护**: updateLangDropdown 和 BookI18n 异常不再中断切换流程

### v0.9.14 (2026-05-18) — 修复语言切换中英混杂 Bug
- **修复详情页英文模式下标签显示中文**: 所有 meta-label 添加 data-i18n 属性
- **修复详情页中文模式下书名/描述仍显示英文**: BookI18n.applyLanguage() 支持详情页模式
- **所有页面 languagechange 处理器统一添加 applyPageTranslation() 调用**
- **新增 14 个详情页翻译键值**

### v0.9.13 (2026-05-18) — 前端语言包即时切换 — BookI18n 图书内容语言包全页面集成
- **4个模板页面集成 BookI18n**: awards/new_books/book_detail/weekly_report_detail 全部支持 BookI18n 即时切换
- **languagechange 事件监听**: 所有页面监听语言切换事件，使用 `BookI18n.applyLanguage()` 即时替换
- **缺失翻译自动补全**: `BookI18n.getMissingTranslations('zh')` 检测缺失翻译并后台调用翻译 API
- **保留原有翻译函数作为后备**: BookI18n 不可用时回退到 `translateAllBooks()` / `loadBooks()`
- **翻译结果同步回写**: 翻译 API 成功后通过 `BookI18n.updateTranslation()` 更新内存数据

### v0.9.10 (2026-05-18) — 语言切换完整修复
- **修复语言同步循环问题**: base.html内联脚本优化，确保localStorage与服务端语言一致
- **重新编译翻译文件**: 所有语言包重新编译，确保翻译最新
- **导航菜单翻译同步**: 语言切换后导航菜单完整显示中文/英文

### v0.9.9 (2026-05-15) — 分类切换报错修复与语言同步优化
- **分类切换报错修复**：`/api/category-books` 接口增加异常降级处理，服务异常时返回空列表而非500错误
- **语言同步优化**：`base.html` 内联脚本优先尊重用户 localStorage 语言设置，不再强制覆盖为服务端语言

### v0.9.8 (2026-05-15) — 语言切换按钮修复
- **修复语言切换按钮状态不同步**：切换到中文版后，导航栏语言按钮始终显示正确状态（中/EN）
- **消除竞态条件**：统一语言初始化逻辑，确保 DOM 加载完成后再更新 UI

### v0.9.7 (2026-05-14) — 路由层 db.session 治理 & 前端 XSS 加固
- **路由层 db.session 治理**：`new_book_detail` 路由改用 `NewBookService.get_book`，异步翻译逻辑提取至 `NewBookService.translate_book_background`
- **翻译闭包治理**：`_merge_or_translate_book` 的异步翻译闭包改用 `UserService.save_book_translation`，消除闭包内直接 db.session 操作
- **前端 XSS 加固**：`index.html` 搜索历史 `aria-label`、`analytics_dashboard.html` 表格行模板变量全部使用 `escapeHtml()` 转义
- **User-Agent 配置化**：`open_library_client.py` User-Agent 从配置读取，不再硬编码
- **类型注解修复**：`user_service.py` 返回类型移除字符串前引

### v0.9.6 (2026-05-14) - 配置项集中管理 & 图表颜色规范化
- **配置项迁移**：6 个配置项（TTL、模型名称、缓存容量）迁移到 `config.py`
- **图表颜色规范化**：`analytics_dashboard.html` 所有图表颜色统一由 `chartColors` 对象管理

### v0.9.5 (2026-05-14) - API 路由统一错误处理装饰器
- **装饰器统一接管**：31 个 API 函数引入 `@handle_api_errors`，错误返回格式统一
- **代码简化**：移除 31 处手动 try/except，减少约 150 行代码

### v0.9.4 (2026-05-14) - 前端 XSS 漏洞修复
- **购买链接 XSS 修复**：`index.html` 中 `link.name` 未转义直接注入 DOM，现使用 `escapeHtml()` 转义
- **SVG 注入防护**：`base.html` SVG Sprite 加载增加类型、格式、结构三重验证
- **数据表格转义**：`analytics_dashboard.html` 所有用户可见数据使用 `escapeHtml()` 转义

### v0.9.3 (2026-05-14) - SECRET_KEY 管理与 CORS 配置修复
- **SECRET_KEY 固定化**：开发环境使用固定密钥，生产环境强制环境变量校验
- **CORS 配置修复**：开发/测试/生产环境分离，credentials 组合合规

### v0.9.2 (2026-05-14) - 缓存高频写入优化
- **缓存命中即 commit 修复**：`api_cache_service.py` 和 `translation_cache_service.py` 读路径移除数据库写入
- **日志补全**：`analytics_service.py` 添加 logging 和异常处理

### v0.9.1 (2026-05-14) - 数据库迁移系统修复
- **8 个缺失表迁移**：新增 `create_all_missing_tables.py`，包含完整 CREATE TABLE 语句
- **迁移链修复**：迁移链顺序正确，支持 `flask db upgrade` 完整重建

### v0.9.0 (2026-05-14) - 全面代码审计
- **全项目代码审计**：覆盖路由层、服务层、模型层、前端模板、配置安全和测试体系
- **发现 120+ 问题**：8 项严重、15 项高危、40+ 项中等、57 项低危
- **审计报告输出**：详见 `CHANGELOG.md` 和 `docs/code-audit-report-2026-05-14.md`
- **修复优先级矩阵**：P0-P3 四级优先级，指导后续修复工作

### v0.8.2 (2026-05-14) - Flask-Babel 4.0 兼容性修复
- **修复生产环境 500 错误**：`get_locale()` 在模板中未定义问题
- **Flask-Babel 4.0 API 适配**：`locale_selector` 改为属性赋值 + Jinja2 globals 注入

### v0.8.1 (2026-05-11) - 语言切换 Bug 修复
- **分类标签语言翻转修复**：中英文界面分类标签显示正确
- **服务端渲染语言适配**：`index.html`、`_macros.html`、`awards.html` 服务端渲染根据 locale 切换内容

### v0.8.0 (2026-05-11) - 全线优化升级
- **生产依赖精简**：新增 `requirements-prod.txt`，移除开发工具减少内存占用
- **错误监控**：内置内存错误追踪器（`/admin/errors` 路由）
- **CSRF 保护全量覆盖**：所有 POST 路由已有 CSRF 保护
- **代码整洁**：删除 28 个临时调试文件，17 个脚本移入 `scripts/`
- **性能优化**：CSS 构建缓存检测 + Gzip 响应压缩 + SW 缓存策略 v2
- **文档同步**：README/VERSION/CHANGELOG 更新至当前状态

### v0.7.0 (2026-04) - Render 部署优化
- PostgreSQL 连接池极致优化（pool_size=2, overflow=1）
- Gunicorn 单 worker 模式 + `--preload` 共享内存
- APScheduler 内存队列调度
- 智能处理 Render 数据库冷启动
- SQLAlchemy 2.0 兼容就绪

### v0.6.0 (2026-03) - 代码架构升级
- API 路由拆分为子模块
- 周报模块标准化
- 代码质量工具链集成（Ruff + mypy + pre-commit）

### v0.5.0 (2026-02) - 功能扩展
- 新书速递爬虫系统
- 智谱AI翻译服务
- 每周报告生成

### v0.4.0 (2026-01) - 基础完善
- 缓存系统
- 奖项书单
- 数据导出功能
