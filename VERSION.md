# BookRank 版本信息

**当前版本**：v0.9.86
**发布日期**：2026-07-16
**Python 版本**：3.13
**Flask 版本**：3.1.3

## 版本亮点

### v0.9.86 (2026-07-16) — 依赖安全漏洞修复（Dependabot 36 个 alert）

**背景**：GitHub Dependabot 在默认分支检测到 36 个依赖漏洞（涉及 7 个直接依赖）。本次升级将这些依赖更新到已修复版本，消除已知安全风险。

**关键优化**
- **Werkzeug**：3.1.0 → 3.1.6（修复 Windows 特殊设备名 safe_join 绕过漏洞）
- **Flask-CORS**：4.0.1 → 6.0.0（修复路径匹配正则、大小写敏感、URI 解码相关 CVE）
- **requests**：2.32.3 → 2.33.0（修复临时文件复用与 .netrc 凭证泄露漏洞）
- **python-dotenv**：1.0.1 → 1.2.2（修复 set_key 符号链接跟随导致的任意文件覆盖）
- **Pillow**：11.1.0 → 12.2.0（修复 PSD OOB 写入、PDF 解析死循环、字体整数溢出、FITS GZIP 解压炸弹等）
- **bleach**：6.1.0 → 6.4.0（修复 formaction 属性与 Unicode URI 方案消毒绕过）
- **mistune**：3.2.1 → 3.3.0（修复 parse_link_text 二次时间解析 DoS）
- **同步更新**：`requirements.txt` 与 `requirements-prod.txt` 保持一致。

**质量验证**
- `pytest`：2130 passed，覆盖率 81.55%
- `ruff check app/ tests/`：通过
- `mypy app/`：通过

---

### v0.9.85 (2026-07-16) — v0.9.84 收尾与仓库整理

**背景**：v0.9.84 OSS 社区成熟度升级后，仓库中存在未跟踪的 Agent 文档、审计交付物和 GitHub CLI 缓存；同时需要手动确认 Private Vulnerability Reporting 已启用。本次整理补齐这些遗留项，使仓库状态干净。

**关键优化**
- **Private Vulnerability Reporting 确认**：通过 `gh api repos/gongyijie85/bookrank/private-vulnerability-reporting` 验证已启用（返回 `{"enabled":true}`）。
- **GitHub CLI 缓存忽略**：在 `.gitignore` 新增 `.gh-cache/`，防止本地 `gh` 命令缓存被误提交。
- **Agent 文档入库**：提交 `AGENTS.md` 与 `docs/agents/` 下 `domain.md`、`issue-tracker.md`、`triage-labels.md`，为 Agent 工作流提供规范。
- **审计交付物归档**：提交 `deliverables/bookrank-audit-20260708/`（含桌面端/平板端/移动端三端截图与 `audit-data.json`），归档 v0.9.83 同事反馈 P0-P3 优化的审计产物。

**质量验证**
- `ruff check app/ tests/`：未改动源码，保持通过
- `mypy app/`：未改动源码，保持通过
- `git status`：除已忽略缓存外无未跟踪文件

---

### v0.9.84 (2026-07-13) — OSS 社区成熟度升级（社区文件 / GitHub 配置 / Docker / Issue #8 修复）

**背景**：补齐 BookRank 作为开源项目的社区标准文件、仓库展示、Docker 一键运行和 GitHub 社区能力，使 Community Profile 达到 100%；同时修复 `Dockerfile` 引用已删除 `build.py` 的问题与 Issue #8 的根因。

**关键优化**
- **社区标准文件**：新增 MIT `LICENSE`、CONTRIBUTING.md、SECURITY.md、CODE_OF_CONDUCT.md、ROADMAP.md。
- **GitHub 社区配置**：新增 Bug/Feature Issue Forms、PR 模板、Dependabot 配置；启用 CodeQL 默认配置与 Dependabot Security Updates。
- **Docker 一键运行**：删除 `Dockerfile` 中已失效的 `build.py` 调用；新增 `compose.yaml`，使用 SQLite 持久卷与端口 `8000`。
- **Issue #8 修复**：将 NYT 频率检查放到已安装项目依赖后执行，保留一致/漂移/运行错误三种退出语义，并为不同场景打上对应标签。
- **README 修正**：CI badge 路径由 `test.yml` 改为 `ci.yml`，新增 v0.9.84 最近更新条目。

**质量验证**
- `ruff check app/ tests/` 通过
- `mypy app/` 通过（90 source files 无类型问题）
- `pytest tests/test_nyt_frequency_check.py -q --no-cov`：8 passed
- `docker compose config` 与 `docker compose up --build` 可正常启动

---

### v0.9.83 (2026-07-07) — 同事反馈 P3 优化（代码清理 / 缓存简化 / 构建瘦身 / 服务与响应统一）

**背景**：基于四位同事反馈与 ponytail-audit，P3 聚焦不改动业务行为的前提下删除 dead code、简化手写缓存与装饰器、移除构建压缩依赖、统一服务访问与 API 响应。

**关键优化**
- **死代码清理**：删除 8 个一次性 `scripts/_*.py` 脚本、周报任务中 5 个邮件相关函数、`build.py` 及全部 minified 产物，减少约 1500 行无效代码。
- **构建瘦身**：从依赖中移除 `rcssmin`，前端直接提供原始 CSS/JS，由平台 gzip/Brotli 压缩；`app/__init__.py` 与模板不再维护 minified 资源存在性配置。
- **缓存简化**：自定义 LRU cache 统一替换为 `functools.lru_cache`。
- **装饰器合并**：`safe_execute` / `safe_call` / `safe_service_call` 合并为单一实现，避免 200+ 行重复包装。
- **服务访问统一**：`app/utils/service_helpers.py` 新增 `get_service` / `require_service` / `_get_or_create_service`，按服务名统一获取/要求单例。
- **响应格式统一**：`APIResponse` 增加 `include_timestamp` 参数；`PublicAPIResponse` 改为向后兼容薄包装。
- **测试清理**：移除周报任务与周报功能测试中已失效的 SMTP/邮件相关用例。

**质量验证**
- `ruff check app/ tests/` 通过
- `mypy app/` 通过（90 source files 无类型问题）
- `pytest --cov=app`：2164 passed，覆盖率 81.36%

---

### v0.9.82 (2026-07-07) — 同事反馈 P2 优化（导航 / SEO / 可访问性 / 数据净化）

**背景**：P1 基础体验优化完成后，P2 聚焦导航简化、SEO 结构化数据、可访问性细节与缺失数据展示兜底。

**关键优化**
- **面包屑导航**：新增 `templates/_breadcrumbs.html` 宏组件，全站 10+ 页面接入面包屑，内嵌 `BreadcrumbList` JSON-LD；`base.html` 简化顶部导航语义结构，移除冗余 ARIA role。
- **SEO 结构化数据**：首页榜单注入 `ItemList` + `Book` schema；书籍详情、新书详情、获奖详情注入完整 `Book` JSON-LD；周报详情注入 `Article` JSON-LD；详情页补齐 `og:image` / `twitter:image`。
- **可访问性**：语言切换同步更新 `<html lang>`；修正标题层级；面包屑与导航当前项添加 `aria-current="page"`；封面 `alt` 增强为“《书名》封面，作者 XXX”；搜索表单语义化为 `<search>` + `<label>` + `<input type="search">`。
- **数据净化**：`app/__init__.py` 新增 `is_invalid_publisher`、`clean_brackets` 等模板过滤器；页数为 `0` / `Unknown` / `N/A` 等占位值时不显示；出版社字段过滤后再写入结构化数据。
- **测试修复**：`tests/test_main_routes_extended.py` 补充 mock 书籍字段，修复 JSON-LD 序列化 `MagicMock` 不可序列化错误。

**质量验证**
- `ruff check app/ tests/` 通过
- `mypy app/` 通过（90 source files 无类型问题）
- `pytest --cov=app`：2164 passed，覆盖率 81.36%

---

### v0.9.81 (2026-07-07) — 同事反馈 P0 阻塞项修复收尾

**背景**：基于四位同事反馈与 ponytail-audit，完成全部 P0 阻塞项修复。

**关键修复**
- P0-1：新书速递页面 ISBN 脏数据清洗（`query_service.py` + `_macros.html`）。
- P0-2：SVG 图标改为内联雪碧图（`base.html` + `templates/icons.svg`）。
- P0-3：CSP 使用 per-request nonce 并移除 `unsafe-inline`（`app/__init__.py` + `base.html`）。
- P0-4：删除旧 minified JS 产物并添加防御式 `getThemeColors`（`static/js/base.js`）。
- P0-5：确认 Vite 开发客户端残留非代码问题。

**质量验证**
- `ruff check app/ tests/` 通过
- `mypy app/` 通过
- `pytest --cov=app`：2164 passed，覆盖率 81.33%

---

### v0.9.80 (2026-06-17) — CODE_WIKI 导入 Obsidian 知识库
- **Obsidian 知识库**：将 `CODE_WIKI.md` 按 18 个章节拆分到 `Code Wiki/` 目录，含索引页 + wikilink 导航
- **拆分脚本**：`scripts/split_wiki.py` 自动化按 `## ` 标题拆分 Markdown，可复用
- **改动文件**：新增 19 个 Markdown 文件 + 1 个拆分脚本

### v0.9.79 (2026-07-05) — 综合审计整改收尾

**背景**：基于 2026-07-02 全维度综合审计，完成代码质量、测试覆盖、安全、性能、配置环境、部署回滚、监控告警、数据库、文档与用户体验 10 个维度的审计与关键整改。

**关键整改**
- **代码质量**：完成全量代码质量审计；路由层直接 `db.session` 调用逐步下沉 Service 层；Ruff / mypy 持续保持通过。
- **测试覆盖**：识别 18 个低覆盖率模块；封堵爬虫测试真实网络请求；当前总覆盖率 ≥73%，CI 阈值 ≥70%。
- **安全**：完成 OWASP Top 10 安全审计；`admin.py` 三个管理端点补齐 `@csrf_protect`；安全头、admin_auth、依赖漏洞已处理。
- **性能**：完成性能审计；修复 `BookService.sync_all_categories` 与 `AwardBookService._process_award_books` 两处 N+1 查询，使用 `selectinload` / 批量操作降低查询次数。
- **配置环境**：`.env.example` 补全 `ADMIN_SECRET`、`IMAGE_TIMEOUT`、`NYT_RANKING_SYNC_DAYS`、`SQLALCHEMY_ECHO`、`SENTRY_DSN`、`ALERT_WEBHOOK_URL`、`CORS_ORIGINS` 等变量；`app/config.py` 支持 `API_RATE_LIMIT_WINDOW` 与 `CORS_ORIGINS` 过滤。
- **部署回滚**：`render.yaml` 关闭自动部署（`autoDeploy: false`）、健康检查改为 `/health/ready`、强制 `WEB_CONCURRENCY=1`；新增 `docs/runbooks/deployment-rollback.md` 回滚 SOP。
- **监控告警**：`app/utils/error_tracker.py` 接入 Sentry DSN；`app/setup.py` 增加后台任务连续失败告警；`health.py` 就绪检查返回 503；新增 `docs/runbooks/alerts.md`。
- **数据库**：完成数据库模型、索引、迁移历史、连接池审计；补充 `migrations/versions/create_all_missing_tables.py` 修复初始迁移缺少 CREATE TABLE 的问题；新增 `docs/runbooks/database-backup-restore.md` 备份恢复手册。
- **文档**：新增/更新 10 份审计报告与 3 份 Runbook；更新 README、CHANGELOG、VERSION、onboarding、API 文档。
- **用户体验**：完成 UX 审计，输出 3-5 项优先级改进建议（骨架屏、统一错误页、语言切换反馈、暗色主题对比度、搜索入口可达性）。

**验证**
- `make check` 通过（Ruff lint + format check + mypy）。
- `pytest tests/` 全量通过，覆盖率 ≥73%。

---

### v0.9.78 (2026-06-26) — 移动端详情页 Tab 化 + Tab 改名 + 语言切换
- **详情页 Tab 化**：书籍详情和获奖图书详情都加"图书简介 / 详细信息"两个 Tab，与电脑端一致；切换"详细信息"时懒加载 Google Books 详细介绍
- **删除放大镜**：首页顶部 nav 去掉搜索图标，只保留"书榜"标题
- **Tab 改名**：底部 4 个 Tab 改为 首页 / 获奖书单 / 出版社 / 我的
- **删除返回按钮**：详情页底部"返回榜单"按钮去掉（保留顶部 m-header 返回箭头）
- **加语言切换器**：顶部右上角加地球图标，点击下拉切换"简体中文 / English"，复用 `book-i18n.js`，持久化到 `localStorage.bookrank_language`
- **质量验证**：ruff check / mypy 全部通过；2136 passed, 4 xfailed；移动端测试从 20 个增至 30 个
- **改动文件**：6 个（2 个模板 + CSS + JS + 2 个测试相关）

### v0.9.77 (2026-06-26) — 移动端 UI v2.0 视觉优化
- **设计风格升级**：按 v2.0.0 设计稿全面优化移动端现有页面，墨绿主色 + 暖橙强调 + 米白背景，更清爽
- **底部 Tab Bar**：手写 SVG 实心/描边两套图标，激活态墨绿色，首页图标 28px 视觉重心
- **首页**：顶部导航栏 + 搜索图标；分类 Tab 改为底部指示条；卡片阴影更柔和
- **书籍详情**：封面区渐变过渡；内容简介段落化、行高 1.8；详情信息改为单列列表；底部新增"返回榜单"按钮
- **获奖图书详情**：与书籍详情布局统一，奖项名和年份用徽章展示
- **周报列表**：左右布局卡片，左侧 Wxx 周数指示器，右侧日期/统计 + 箭头
- **周报详情**：Hero 统计 4 列水平布局，推荐书籍理由改为气泡样式
- **搜索页**：搜索表单结构优化，热门搜索标签样式统一
- **个人中心**：收藏/搜索历史空状态加图标装饰
- **触控规范**：按钮/分页最小高度 44px
- **质量验证**：ruff check / mypy / 20 个移动端测试全部通过
- **改动文件**：11 个（CSS + 9 个模板 + 测试）

### v0.9.76 (2026-06-26) — 周报列表页 + 详情页（bookrank-draft 设计稿）
- **weekly-report-list.html**：全新周报列表页，5 张示例卡片（W25-W21），含空状态占位
- **weekly-report.html**：完全重写周报详情页，Hero 渐变区 + 4 列统计 + 榜单变化 + 推荐书籍语气泡 + 分享按钮
- **设计系统统一**：CSS 变量内联、Tailwind CDN v4、Lucide 图标、底部 Tab Bar 规范、data-dom-id 命名
- **改动文件**：2 个（1 新增 + 1 重写）

### v0.9.69 (2026-06-17) — 新书速递模块修复
- **统计栏占位符修复**：移除 `data-i18n` 属性，直接使用 Jinja2 翻译，解决 `{count}` 占位符未替换问题
- **分类数据中英文统一**：添加 `CATEGORY_EN_TO_ZH` 映射表（20 个常见分类），`sanitize_category` 函数应用映射
- **数据迁移接口**：新增 `/migrate-categories` 管理接口，批量更新已有书籍分类数据
- **CSV 公式注入防护**：`_sanitize_csv_field` 处理 `=+-@\t\r` 前缀字段
- **CSV 导出速率限制**：每 IP 10 秒冷却,多 worker 安全
- **卡片标签兜底**：`publication_date/category` 缺失时显示"分类未公开 / 日期未公开"占位
- **统计区间扩展**：`get_statistics` 同时返回 `recent_books_7d` + `recent_books_30d`
- **搜索端点过滤对齐**：`/api/new-books/search` 支持 `publisher_id/category/days` 过滤
- **翻译诊断日志**：`_translate_book` 失败时打印 id+长度上下文
- **测试覆盖**：新增 16 个测试用例(CSV 注入、速率限制、搜索过滤、统计字段)
- **质量验证**：ruff check / mypy / pytest (118 passed) 全部通过
- **改动文件**：11 个

### v0.9.68 (2026-06-14) — 修复 CI 依赖冲突
- **根因**：v0.9.67 添加的 `PyJWT>=2.13.0` 与 `zhipuai==2.1.5.20250825`（约束 `pyjwt<2.9.0,>=2.8.0`）冲突，CI 三个 Job 在 `pip install` 阶段失败
- **修复**：从 `requirements.txt` 移除 `PyJWT>=2.13.0`（代码零引用、prod 也未包含）
- **改动文件**：3 个（`requirements.txt`、`CHANGELOG.md`、`VERSION.md`）

### v0.9.67 (2026-06-14) — 安全审计：CSRF 全覆盖 + 依赖漏洞修复
- **S1 admin_auth 中间件**：确认已完善（rate limit + 失败计数 + 持久化 + 审计日志）
- **S2 CSRF 保护全覆盖**：为 `favorites` / `awards` / `books` 模块的 8 个 POST/DELETE 端点添加 `@csrf_protect`
- **S3 安全头检查**：确认已手动实现 CSP/HSTS/X-Frame-Options
- **S4 密钥轮换 SOP**：确认环境变量管理规范已就绪
- **S5 依赖漏洞修复（pip-audit）**：mistune 3.2.0 → 3.2.1（修复 2 个 XSS 漏洞），添加 PyJWT>=2.13.0（修复 6 个漏洞）
- **S6 静态扫描修复（bandit）**：MD5 哈希添加 `usedforsecurity=False` 参数
- **质量验证**：ruff check / mypy / pytest 全部通过（48/48 测试）
- **改动文件**：5 个（`app/routes/api/favorites.py`、`app/routes/api/awards.py`、`app/routes/api/books.py`、`app/services/api_utils.py`、`requirements.txt`）

### v0.9.64 (2026-06-14) — 多 worker 安全锁 + CSV 文件名国际化
- **L1 多 worker 安全锁**：`app/routes/new_books.py` 使用 `current_app.extensions` 存储同步锁和时间戳，替代全局变量，确保跨 worker 同步操作安全
- **L2 CSV 文件名 RFC 5987 国际化**：CSV 导出使用 `filename*=UTF-8''` 格式，同时提供 ASCII 备用名，修复中文文件名乱码问题
- **L3 var → const/let 统一**：`templates/new_books.html` 将 `var card` / `var bookCard` 替换为 `const`，符合 ES6 规范
- **L5 全局图片错误处理验证**：`static/js/base.js` 的 `initImageErrorHandler` 已实现基于 `data-fallback` 属性的统一监听
- **M7/M8 详情页 i18n 通用化**：确认 v0.9.62 已完成，无需改动
