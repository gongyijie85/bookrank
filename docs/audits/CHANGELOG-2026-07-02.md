# BookRank 审计变更日志

**版本**：v1.1.0-audit  
**修改时间**：2026-07-02 (Asia/Shanghai)  
**修改人**：Trae Agent

---

## 新增文件

1. `docs/audits/audit-code-quality-2026-07-02.md`
   - 代码质量审计报告。
   - 覆盖 Ruff、mypy、上帝对象、重复异常装饰器、`except Exception: pass`、路由层 `db.session` 直接调用、mypy override 过度禁用。
   - Verdict：CONCERNS。

2. `docs/audits/audit-test-coverage-2026-07-02.md`
   - 测试覆盖率审计报告。
   - 覆盖 pytest 全量运行、覆盖率统计、<60% 模块、slow 标记缺失、测试文件过大、flakiness 重跑。
   - Verdict：CONCERNS。

3. `docs/audits/audit-deployment-2026-07-02.md`
   - 部署与回滚审计报告。
   - 覆盖 CI/CD、Render 配置、Dockerfile、Gunicorn、回滚流程、Staging 环境。
   - Verdict：FAIL。

2. `docs/audits/audit-monitoring-2026-07-02.md`
   - 监控与告警审计报告。
   - 覆盖健康检查、ErrorTracker、日志、外部监控工具、告警阈值、后台任务通知。
   - Verdict：FAIL。

3. `docs/audits/audit-security-2026-07-02.md`
   - 安全审计报告（OWASP Top 10）。
   - 覆盖访问控制、加密、注入、XSS、安全配置、脆弱组件、限流、CORS。
   - Verdict：CONCERNS。

4. `docs/audits/audit-config-env-2026-07-02.md`
   - 配置与环境审计报告。
   - 覆盖环境变量一致性、配置类一致性、依赖版本一致性、Render/Dockerfile 构建一致性、生产安全开关。
   - Verdict：CONCERNS。

5. `docs/runbooks/deployment-rollback.md`
   - 部署回滚标准作业程序（Runbook）。
   - 包含触发条件、回滚步骤、数据库迁移处理、验证清单和常见问题。

6. `docs/audits/CHANGELOG-2026-07-02.md`
   - 本变更日志，记录本次审计新增的全部文档。

---

## 关键发现摘要

- **代码质量**：
  - 路由层仍有 13 处直接调用 `db.session`（`new_books.py`、`api/awards.py`、`api/__init__.py`、`health.py`），违反服务层隔离。
  - `safe_call` / `safe_service_call` / `safe_execute` 三套异常装饰器重复，且生产代码几乎未使用。
  - `pyproject.toml` 中对 30+ 模块禁用 12 种 mypy 错误码，类型检查价值被严重削弱。
  - 存在多个 >500 行文件（`main.py`、`admin.py`、zhipu_translation_service 等）及 6 处 `except Exception: pass`。
- **测试覆盖**：
  - 排除 Publisher Crawler 测试后总覆盖率 73%，18 个模块 < 60%。
  - `test_publisher_crawler.py` 真实请求 `robots.txt`，导致全量 suite 无法完成。
  - 未使用 `@pytest.mark.slow` / `@pytest.mark.integration`，且多个测试文件超过 500 行。
- **部署**：Render `autoDeploy: true` 与 CI 解耦，缺少回滚 SOP 和 Staging 环境。
- **监控**：健康检查不验证真实依赖，ErrorTracker 仅内存存储，无外部监控与告警。
- **安全**：
  - 部分管理员 POST 端点（`clean_report_brackets`、`fix_truncated_titles`、`cleanup_translations`）缺少 `@csrf_protect`。
  - IP 限流器为进程内存实现，多 Gunicorn worker 下会失效。
  - `requirements-prod.txt` 缺少 `bleach`，生产环境 HTML 净化降级为正则回退。
  - CSRF 令牌未与会话绑定。
- **配置环境**：
  - `.env.example` 缺少 `ADMIN_SECRET` 示例。
  - `API_RATE_LIMIT_WINDOW` 在 `.env.example` 中声明但 `config.py` 未读取。
  - `requirements-prod.txt` 与 `requirements.txt` 中 `mistune` 版本不一致（3.2.0 vs 3.2.1）。

---

## 待办事项

1. 将 `new_books.py`、`api/awards.py`、`api/__init__.py`、`health.py` 中的 `db.session` 调用迁移到 Service 层。
2. 合并/废弃 `safe_call` / `safe_service_call` / `safe_execute` 重复装饰器。
3. 清理 `pyproject.toml` 中过度宽松的 mypy override。
4. 修复 `test_publisher_crawler.py` 真实网络请求问题，并为慢测试添加 `@pytest.mark.slow`。
5. 拆分超过 500 行的测试文件，提升低覆盖模块（Publisher Crawler、initialization、cache、cron）的测试。
6. 关闭 Render autoDeploy，改为 CI 成功后触发 Deploy Hook。
7. 创建 Staging 环境。
8. 修复 `/health/ready` 在数据库异常时返回 HTTP 503。
9. 接入 Sentry 等外部错误追踪服务。
10. 优化 Dockerfile 与 Gunicorn worker 配置。
11. 为 `admin.py` 中缺失 CSRF 保护的三个端点添加 `@csrf_protect`。
12. 实现跨进程限流（Redis/Memcached）或限制 `WEB_CONCURRENCY=1`。
13. 在 `requirements-prod.txt` 中补充 `bleach==6.1.0` 并对齐 `mistune` 版本。
14. 在 `.env.example` 中补充 `ADMIN_SECRET`、`IMAGE_TIMEOUT`、`NYT_RANKING_SYNC_DAYS`、`SQLALCHEMY_ECHO` 等变量。
15. 让 `API_RATE_LIMIT_WINDOW` 支持环境变量读取或从 `.env.example` 移除。
