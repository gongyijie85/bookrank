# 免费层周报自动总结部署指南

> 适用于 Render 免费层（Free Tier）+ GitHub Actions（免费）

## 为什么需要这个方案

Render 免费层有两个致命限制：

1. **15 分钟无请求即休眠** — 冷启动后 APScheduler 的 30 分钟延迟定时器永远等不到触发
2. **无内置 Cron Job 服务** — 无法像付费版那样添加独立定时任务

本方案通过 **GitHub Actions 外部定时调用 Render webhook** 绕过这些限制，完全零成本。

---

## 部署步骤

### 1. 生成 CRON_SECRET

本地执行：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

复制输出的随机字符串，后面两处都要用到**同一个值**。

### 2. 配置 Render 环境变量

进入 [Render Dashboard](https://dashboard.render.com) → 你的 Web Service → Environment：

| 变量名 | 值 |
|--------|-----|
| `CRON_SECRET` | 上面生成的密钥 |

点击 **Save Changes**，Render 会自动重新部署。

### 3. 配置 GitHub Actions Secret

进入 GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Name | Secret |
|------|--------|
| `CRON_SECRET` | 上面生成的同一个密钥 |

### 4. 验证部署

等 Render 部署完成后，在 GitHub 仓库 → Actions → Trigger Weekly Report → Run workflow 手动触发一次：

```bash
# 或者本地 curl 测试（替换为你的 CRON_SECRET）
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  "https://bookrank-ckml.onrender.com/api/cron/trigger-weekly-report"
```

成功返回示例：
```json
{
  "success": true,
  "message": "周报已生成: 2026年05月25日-2026年05月31日 畅销书周报",
  "data": { "report_id": 2, ... }
}
```

---

## 免费层工作原理

```
每周五 08:00 UTC
       │
       ▼
┌─────────────────┐
│ GitHub Actions  │  ← 免费，运行在 GitHub 服务器上
│ (定时触发器)     │
└────────┬────────┘
         │ curl + Bearer Token
         ▼
┌─────────────────┐
│ Render 免费层    │  ← 可能被唤醒（冷启动 ~10-20s）
│ /api/cron/...   │
└────────┬────────┘
         │ 调用 generate_weekly_report()
         ▼
┌─────────────────┐
│ 生成周报 → 存 DB │  ← 整个过程 ~30-120s
└─────────────────┘
```

### 冷启动防护

工作流已内置三重保护：

1. **预唤醒**：先 ping `/api/health` 触发冷启动，等待 15 秒
2. **自动重试**：最多 3 次尝试，每次间隔 30 秒
3. **兜底检查**：APScheduler `weekly_report_init` 延迟缩短到 2 分钟，应用启动后会自动检查是否需要补生成

---

## 可选：消除冷启动（UptimeRobot）

如果你希望应用**始终在线**（消除冷启动延迟），可以用 [UptimeRobot](https://uptimerobot.com/) 免费版每 5 分钟 ping 一次：

1. 注册 UptimeRobot（免费）
2. 添加 Monitor：
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: BookRank Keepalive
   - **URL**: `https://bookrank-ckml.onrender.com/api/health`
   - **Monitoring Interval**: 5 minutes

> ⚠️ 注意：Render 免费层每月 750 小时额度，24/7 运行约 730 小时/月，刚好够用。如果某个月超出，服务会被暂停到下个月。

---

## 常见问题

### Q: 为什么不用 Render 自己的 Cron Job？
A: Render 免费层不支持 Cron Job 服务，只有付费计划（Starter 及以上）才能添加。

### Q: GitHub Actions 收费吗？
A: Public 仓库完全免费（每月 2000 分钟额度，本工作流每次约 30 秒，一个月 4 次，完全够用）。

### Q: 可以换成其他外部 cron 服务吗？
A: 可以。任何支持 HTTP GET + 自定义 Header 的服务都行，例如 [cron-job.org](https://cron-job.org/)（免费）：
- URL: `https://bookrank-ckml.onrender.com/api/cron/trigger-weekly-report`
- Header: `Authorization: Bearer <CRON_SECRET>`

### Q: 周报生成时应用会不会又休眠了？
A: 不会。请求处理期间应用保持活跃。`generate_weekly_report()` 运行期间（30-120 秒），Gunicorn worker 正在处理请求，Render 不会在此期间休眠。

### Q: 如果生成时间超过 3 分钟怎么办？
A: Gunicorn timeout 设置为 180 秒，curl max-time 240 秒。正常数据在缓存中时生成很快（30-60 秒）。如果某次确实超时，GitHub Actions 会重试，或者你可以手动访问 `/reports/weekly` 页面触发兜底生成。
