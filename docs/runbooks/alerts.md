# BookRank 监控告警 Runbook

**版本**: v1.2  
**生效日期**: 2026-08-13  
**适用范围**: Render 生产环境（`bookrank` Web Service）  
**责任人**: 项目维护者 / On-call 人员

---

## 一、告警来源

当前 BookRank 生产环境依赖以下监控与告警来源：

| 来源 | 用途 | 配置位置 |
|------|------|----------|
| Render 健康检查 | 探测 `/health/ready` 可用性 | `render.yaml` 第 19 行 |
| GitHub Actions 生产探测 | 每 5 分钟探测 `/health/ready` 并测量端到端响应时间 | `.github/workflows/production-monitor.yml` |
| Render Notifications | 失败构建/部署与运行服务变为 unhealthy 时的原生通知 | Render Dashboard → Integrations → Notifications |
| Sentry（可选） | 未处理异常与分类错误持久化 | `SENTRY_DSN` 环境变量 |
| UptimeRobot / Render 告警 | 外部可用性与响应时间监控 | 在对应平台手动配置 |
| 应用内后台任务告警 | 关键后台任务连续失败通知 | `ALERT_WEBHOOK_URL` 或 `MAIL_ENABLED` |

---

## 二、告警阈值

| 指标 | 阈值 | 严重等级 | 通知渠道 |
|------|------|----------|----------|
| `/health/ready` 不可用 | 单次 5 分钟生产探测失败（建议外部监控配置连续 2 次） | Critical | `PRODUCTION_ALERT_WEBHOOK_URL` / Render 通知 |
| 5xx 错误率 | > 1%（5 分钟窗口） | High | Webhook / 邮件 |
| `/health/ready` 响应时间 | > `vars.READY_LATENCY_WARNING_SECONDS` 秒 Warning；> `vars.READY_LATENCY_CRITICAL_SECONDS` 秒 Critical（默认 3 / 10） | High / Critical | `PRODUCTION_ALERT_WEBHOOK_URL` |
| 内存使用 | 连续 10 分钟 > 80% 实例上限；> 90% 为 Critical | High / Critical | 见“Render 指标告警配置” |
| CPU 使用 | 连续 10 分钟 > 80% 可用 CPU；> 95% 为 Critical | High / Critical | 见“Render 指标告警配置” |
| Render 构建或部署失败 | 任意一次 | Critical | Render Notifications（Email / Slack） |
| 后台任务连续失败 | ≥ 2 次 | High | Webhook / 邮件 |
| 数据库连接失败 | 任意一次 | Critical | Webhook / 邮件 |
| 外部 API（NYT/Google Books）配额异常 | 1 小时内调用 > 80% 日配额 | Medium | Webhook / 邮件 |

---

## 三、告警内容格式

### 3.1 Webhook 告警 JSON

```json
{
  "task": "_weekly_report_task",
  "failure_count": 2,
  "error": "Weekly report generation failed: ...",
  "timestamp": "2026-07-02T12:00:00+00:00"
}
```

### 3.2 邮件告警主题

```text
[BookRank 告警] 后台任务 _weekly_report_task 连续失败 2 次
```

---

## 四、收到告警后的处理流程

### 4.1 服务不可用（/health/ready 返回 503）

1. 立即查看 Render Dashboard → Logs，确认错误类型。
2. 检查数据库连接（`DATABASE_URL`、Supabase 连接数）。
3. 若 5 分钟内无法恢复，启动 [部署回滚 Runbook](./deployment-rollback.md)。

### 4.2 后台任务连续失败

1. 查看 Render Logs 中任务名对应的错误堆栈。
2. 检查外部 API 配额（NYT / Google Books / Zhipu）。
3. 若为临时异常，等待下一次调度执行；若连续 3 次失败，手动触发一次并观察。
4. 若为代码缺陷，创建 hotfix 分支修复。

### 4.3 5xx 率或延迟异常

1. 查看 Sentry 或 ErrorTracker 最近错误。
2. 使用 `request_id` 关联日志与请求路径。
3. 识别热点路径（榜单页、搜索、周报生成），必要时临时扩容或限流。

### 4.4 GitHub 邮件 “Production Monitor: All jobs have failed”

该邮件只说明工作流 job 失败，不自动等于生产宕机。先打开对应 run，看 **Probe /health/ready**。Notify 是尽力投递，缺少 webhook 或聊天接口失败不能单独把 job 标红；此邮件若在该约定之后仍出现，以 Probe 步骤为准：

1. Probe 成功（HTTP 200）：生产可用。若耗时超过 Warning 阈值（默认 3s），run 会带 `::warning::` 注解，但 job 应成功。仓库未配置 `PRODUCTION_ALERT_WEBHOOK_URL` 时只会跳过即时消息，不再把 Warning 延迟标成失败。
2. Probe 失败：`/health/ready` 非 200，或耗时超过 Critical 阈值（默认 10s）。按 4.1 处理。这才是需要按 Critical 响应的生产探测失败。
3. 通知步骤是尽力投递：缺少 Secret 或 webhook 接口失败不应单独当作生产事故。需要值班即时消息时，在仓库 Secrets 中配置 `PRODUCTION_ALERT_WEBHOOK_URL`。

---

## 五、值班响应要求

| 严重等级 | 响应时间 | 处理要求 |
|----------|----------|----------|
| Critical | 15 分钟内 | 立即介入，必要时回滚 |
| High | 1 小时内 | 调查根因，制定修复计划 |
| Medium | 4 小时内 | 记录并安排修复 |

---

## 六、Render 指标告警配置

Render 的 Metrics 页面会显示 CPU 和内存使用率，但目前 Render 仅向 **Pro 及以上**工作区提供 OpenTelemetry 指标流；响应时间百分位指标同样需要 Pro 及以上。免费/Hobby 实例不能仅凭 `render.yaml` 自动把这些指标送到 webhook。

### 当前免费层必须完成（维护者在控制台操作）

1. Render Dashboard → **Integrations → Notifications**：将默认服务通知设为 **Only failure notifications**，并连接 Email 或 Slack。这会覆盖构建/部署失败和运行服务变为 unhealthy。
2. GitHub repository → **Settings → Secrets and variables → Actions**：新增 Secret `PRODUCTION_ALERT_WEBHOOK_URL`，值为飞书机器人 webhook。该 workflow 使用飞书 `msg_type: text` 格式；使用 Slack 时请改为 Slack 的 `text` payload，或改由 Render Slack 集成通知。
3. Actions → **Production Monitor**：手动运行一次，确认 `/health/ready` 的 `200` 结果。不要把 webhook URL 写入仓库或 Actions variable。
4. Render Dashboard → service → **Metrics**：每周查看一次 CPU 与内存曲线；达到 Warning 阈值即建立扩容/迁移决策记录。

### 升级到 Pro 后

1. 在 Render Dashboard → **Observability → Metrics Stream** 配置一个 OpenTelemetry 兼容的告警后端。
2. 为 `render.service.memory.usage / render.service.memory.limit` 和 CPU 使用率建立上表阈值告警；响应时间使用 `render.service.http.requests.latency` 的 P95。
3. 将告警通知投递到值班 webhook，并发送一次测试告警，记录时间戳。该路径是 #52 的付费部署决策的一部分。

## 七、配置检查清单

- [ ] `SENTRY_DSN` 已设置（可选但强烈建议）。
- [ ] `ALERT_WEBHOOK_URL` 或 `MAIL_ENABLED` + `MAIL_RECIPIENTS` 已配置。
- [ ] GitHub Secret `PRODUCTION_ALERT_WEBHOOK_URL` 已配置，并已手动运行 Production Monitor 验证。
- [ ] Render Notifications 已设为 Only failure notifications，并已连接 Email 或 Slack。
- [ ] Render 告警已监控 `/health/ready`。
- [ ] UptimeRobot 等外部监控已配置域名与告警通知人。

---

## 八、相关文件

- `render.yaml`：Render 部署与健康检查配置
- `app/routes/health.py`：健康检查端点
- `app/utils/error_tracker.py`：错误追踪与 Sentry 集成
- `app/setup.py`：后台任务失败告警逻辑
- `.github/workflows/production-monitor.yml`：5 分钟就绪与延迟探测
- `docs/runbooks/deployment-rollback.md`：回滚 SOP

---

## 九、修订记录

| 版本 | 日期 | 修订内容 | 修订人 |
|---|---|---|---|
| v1.0 | 2026-07-02 | 初始版本，定义阈值、渠道与响应流程 | Trae Agent |
| v1.1 | 2026-08-13 | 增加生产探测、Render 原生失败通知与免费层/Pro 指标边界 | Codex |
| v1.2 | 2026-08-26 | 区分 Probe 失败与 Notify 失败；缺少 webhook 不再把 Warning 延迟当成生产宕机 | Gong |
