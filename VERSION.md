# BookRank 版本信息

**当前版本**：v0.9.69
**发布日期**：2026-06-17
**Python 版本**：3.13
**Flask 版本**：3.1.3

## 版本亮点

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
