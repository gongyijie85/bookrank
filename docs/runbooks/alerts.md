# BookRank 监控告警 Runbook

**版本**: v1.0  
**生效日期**: 2026-07-02  
**适用范围**: Render 生产环境（`bookrank` Web Service）  
**责任人**: 项目维护者 / On-call 人员

---

## 一、告警来源

当前 BookRank 生产环境依赖以下监控与告警来源：

| 来源 | 用途 | 配置位置 |
|------|------|----------|
| Render 健康检查 | 探测 `/health/ready` 可用性 | `render.yaml` 第 19 行 |
| Sentry（可选） | 未处理异常与分类错误持久化 | `SENTRY_DSN` 环境变量 |
| UptimeRobot / Render 告警 | 外部可用性与响应时间监控 | 在对应平台手动配置 |
| 应用内后台任务告警 | 关键后台任务连续失败通知 | `ALERT_WEBHOOK_URL` 或 `MAIL_ENABLED` |

---

## 二、告警阈值

| 指标 | 阈值 | 严重等级 | 通知渠道 |
|------|------|----------|----------|
| `/health/ready` 不可用 | 连续 2 次探测失败 | Critical | Webhook / 邮件 |
| 5xx 错误率 | > 1%（5 分钟窗口） | High | Webhook / 邮件 |
| P95 响应时间 | > 3 秒 | High | Webhook / 邮件 |
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

---

## 五、值班响应要求

| 严重等级 | 响应时间 | 处理要求 |
|----------|----------|----------|
| Critical | 15 分钟内 | 立即介入，必要时回滚 |
| High | 1 小时内 | 调查根因，制定修复计划 |
| Medium | 4 小时内 | 记录并安排修复 |

---

## 六、配置检查清单

- [ ] `SENTRY_DSN` 已设置（可选但强烈建议）。
- [ ] `ALERT_WEBHOOK_URL` 或 `MAIL_ENABLED` + `MAIL_RECIPIENTS` 已配置。
- [ ] Render 告警已监控 `/health/ready`。
- [ ] UptimeRobot 等外部监控已配置域名与告警通知人。

---

## 七、相关文件

- `render.yaml`：Render 部署与健康检查配置
- `app/routes/health.py`：健康检查端点
- `app/utils/error_tracker.py`：错误追踪与 Sentry 集成
- `app/setup.py`：后台任务失败告警逻辑
- `docs/runbooks/deployment-rollback.md`：回滚 SOP

---

## 八、修订记录

| 版本 | 日期 | 修订内容 | 修订人 |
|---|---|---|---|
| v1.0 | 2026-07-02 | 初始版本，定义阈值、渠道与响应流程 | Trae Agent |
