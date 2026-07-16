# BookRank 监控与告警审计报告

**审计日期**：2026-07-02  
**审计范围**：健康检查端点、错误追踪、日志格式、外部监控工具、告警阈值、后台任务失败通知  
**审计人员**：Trae Agent  
**Verdict**：FAIL（生产级监控与告警能力严重不足）

---

## 一、执行摘要

BookRank 当前监控体系仅覆盖最基础的“服务是否存活”层面。健康检查端点 `/api/health` 被 Render 用于存活探测，但不检查数据库及外部依赖；`ErrorTracker` 完全基于内存，无法跨进程/重启保留错误，也没有主动告警；日志缺乏统一的 request_id 和结构化输出；未接入 Sentry、UptimeRobot、Prometheus 等外部监控服务；后台任务失败仅写入系统配置和日志，不会通知运维人员。

---

## 二、Findings 明细表

| 严重程度 | 位置 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| **Critical** | `render.yaml` 第 19 行 + `app/routes/api/__init__.py` 第 28-33 行 | Render 健康检查路径 `/api/health` 仅返回静态 `{"status":"healthy"}`，不验证数据库、缓存或外部 API | `healthCheckPath: /api/health` 命中 `/api/health`，该端点只返回固定 JSON | 将 Render 健康检查路径改为 `/health/ready` 或让 `/api/health` 执行真实依赖检查（DB SELECT 1、关键服务可用性） |
| **Critical** | `app/utils/error_tracker.py` 第 6-16 行 | `ErrorTracker` 使用内存双端队列（maxlen=500），进程重启/多 worker 环境下错误记录全部丢失 | `self._records: deque[dict[str, Any]] = deque(maxlen=cls._MAX_RECORDS)` | 将错误持久化到数据库或接入外部错误追踪服务（Sentry 免费版、Logtail 等） |
| **High** | `app/routes/health.py` 第 42-51 行 | `/health/ready` 在数据库异常时仍返回 HTTP 200 和 `"status":"ready"`，仅附带 warning 字段，会误导负载均衡器和监控 | `except Exception` 后返回 `{"success":true,"status":"ready","warning":"db_warming_up"}` | 数据库不可用时返回 HTTP 503，明确标记 not ready；仅在启动预热阶段允许 503 |
| **High** | 全局日志配置 | 日志缺少 request_id、user_id、trace_id 等上下文，且多为纯文本格式 | `gunicorn.conf.py` 第 39 行为默认 Nginx 格式；`error_handler.py` 第 52 行仅输出 `[category] message` | 在 Flask 请求入口注入 `request_id` 并贯穿日志；统一使用 JSON 结构化日志 |
| **High** | 项目全局 | 未接入任何外部监控/告警服务（Sentry、UptimeRobot、Datadog、Prometheus 等） | 代码中无相关 SDK 或集成；`docs/` 中监控相关内容为规划而非实现 | 至少接入 Sentry（免费版）捕获未处理异常，并配置 UptimeRobot 或 Render 自带告警监控 `/health/ready` |
| **High** | `app/setup.py` 后台任务包装器 | 后台任务失败仅写入日志和 `SystemConfig`，无主动通知 | `_scheduler_wrapper` 第 331-336 行捕获异常后仅 `log_error`；`_log_failure` 第 554-559 行写入数据库 | 任务连续失败时通过邮件/飞书/Slack 发送告警；关键任务增加失败计数和熔断 |
| **Medium** | `app/routes/health.py` 第 28-39 行 | `/health` 与 `/health/detailed` 都是静态响应，未检查任何依赖 | 两个端点直接返回固定 JSON，无 DB/Redis/API 探测 | 合并或增强 detailed 检查，至少包含 DB、外部 API、磁盘/缓存状态 |
| **Medium** | `gunicorn.conf.py` 第 34-36 行 | 访问日志和错误日志仅输出到 stdout/stderr，未按级别分离，也未留存 | `accesslog = '-'`、`errorlog = '-'` | 保留 stdout 输出以便 Render 收集，同时增加文件轮转或外部日志聚合 |
| **Medium** | `scripts/check_api_health.py` | 健康检查脚本为手动运维工具，未纳入 CI 或定时调度 | 脚本位于 `scripts/`，无调用方 | 在 CI 中定期运行或配置 Render Cron Job 每日执行，并将结果推送通知 |
| **Low** | `app/utils/error_tracker.py` 第 10 行 | 内存错误队列上限 500，高并发场景下可能快速滚动丢失 | `_MAX_RECORDS = 500` | 若继续使用内存队列，至少按错误类型分桶并提高保留上限；长期必须持久化 |

---

## 三、详细检查项结论

### 1. 健康检查端点是否检查 DB 与依赖

- **状态**：FAIL。
- `/api/health`（`app/routes/api/__init__.py` 第 28-33 行）被 Render 用作探测路径，但只返回固定 `status: healthy`。
- `/health/ready`（`app/routes/health.py` 第 42-51 行）会执行 `SELECT 1` 检查数据库，但异常时仍返回 HTTP 200，无法被外部监控正确识别为不可用。
- `/health` 与 `/health/detailed` 为静态响应，未探测外部依赖（NYT API、Google Books API、翻译服务、缓存）。

### 2. ErrorTracker 是否仅内存存储

- **状态**：FAIL。
- `ErrorTracker` 使用 `collections.deque(maxlen=500)` 存储在单例中。
- Render 免费层每次部署或容器回收都会清空内存记录；多 worker 之间也无法共享错误。
- 不满足生产排障和审计需求。

### 3. 日志格式与上下文

- **状态**：CONCERNS。
- `gunicorn.conf.py` 第 39 行 access log 为默认格式，无请求耗时、request_id。
- `error_handler.py` 第 36-65 行按 category 记录错误，但缺少 path、method、user、request_id。
- 项目规则要求“生产环境启用 Flask-Talisman 安全头”，但日志侧未见与 WAF/安全事件的联动。

### 4. 外部监控工具

- **状态**：缺失。
- 代码中无 Sentry、UptimeRobot、Datadog、Prometheus、Grafana 等集成。
- `app/routes/health.py` 注释提到“用于 UptimeRobot 等监控服务”，但实际未配置。

### 5. 告警阈值与通知渠道

- **状态**：缺失。
- 无 5xx 率阈值、P95/P99 延迟阈值、错误率阈值。
- 无邮件、Slack、飞书、PagerDuty 等通知渠道配置。

### 6. 后台任务失败通知

- **状态**：CONCERNS。
- `app/setup.py` 第 324-339 行 `_scheduler_wrapper` 会捕获任务异常并调用 `log_error`。
- 第 554-559 行 `_log_failure` 将失败时间写入 `SystemConfig`。
- 但没有任何主动通知机制，运维人员需要主动查看日志才能发现失败。

---

## 四、Verdict

**FAIL**

关键原因：
1. Render 使用的健康检查路径不验证真实依赖，无法识别数据库/服务故障。
2. 错误追踪完全依赖内存，生产环境不可恢复、不可查询、不可告警。
3. 缺少外部监控与告警服务，后台任务失败无通知。

---

## 五、Next Steps

1. **立即（24 小时内）**：将 `render.yaml` 的 `healthCheckPath` 改为 `/health/ready`，并修复该端点在 DB 异常时返回 HTTP 503。
2. **本周内**：接入 Sentry（免费版）或类似服务，替换/增强内存 `ErrorTracker`，确保未处理异常和分类错误都能被持久化。
3. **本周内**：为 Flask 请求增加 `request_id` 中间件，并在 `error_handler.py` 和 Gunicorn access log 中统一输出该 ID。
4. **本周内**：配置 UptimeRobot/Render 告警，监控 `/health/ready` 的可用性和响应时间。
5. **两周内**：定义告警阈值（如 5xx 率 > 1%、P95 延迟 > 3s、关键后台任务连续失败 2 次），并配置邮件或 IM 通知渠道。
6. **持续**：将 `scripts/check_api_health.py` 纳入 CI 定时任务或 Render Cron，每日检查外部 API 可用性。
