# 安全政策

## 支持的版本

| 版本   | 是否受支持 |
| ------ | ---------- |
| v0.9.84+ | 是          |
| v0.9.83  | 仅关键安全修复 |
| < v0.9.83 | 否         |

## 报告漏洞

BookRank 使用 GitHub Private Vulnerability Reporting 接收安全漏洞报告。

- 请不要在公开 Issue 中披露漏洞细节。
- 请通过仓库的 **Security → Report a vulnerability** 提交私密报告。
- 如有紧急问题，也可发送邮件至 `gongyijie@gmail.com`，标题请注明 `[BookRank Security]`。

## 披露政策

- 收到报告后，维护者会在 7 个工作日内确认。
- 我们会评估影响范围，并在修复完成后发布安全公告。
- 在修复公开前，请避免公开漏洞细节，以保护所有用户。

## 安全配置建议

- 生产环境务必设置强随机 `SECRET_KEY` 与 `ADMIN_SECRET`。
- 使用外部 PostgreSQL 时，避免在日志中打印数据库连接字符串。
- 定期关注 Dependabot 安全更新并及时合并。

## 速率限制与 Worker 数量（重要）

### 默认：进程内存限流（单 worker 前提）

- 未配置 `RATE_LIMIT_REDIS_URL` 时，API 限流器为**进程内存实现**（`app/utils/rate_limiter.py` 的 `IPRateLimiter`），各 Gunicorn worker 进程独立计数。
- 因此**生产环境必须将 `WEB_CONCURRENCY` 固定为 `1`**（已在 `render.yaml` 与 `gunicorn.conf.py` 中固定）。若 `WEB_CONCURRENCY > 1`，攻击者可通过请求分发绕过限流，应用启动时会打印告警日志。

### 可选：Redis 共享限流（支持多 worker）

限流器已支持可插拔的共享后端（安全审计 High #2 根因修复）：

- 设置环境变量 `RATE_LIMIT_REDIS_URL`（如 `redis://user:pass@host:6379/0`）后，限流计数**跨 worker 共享**，此时才可以提高 `WEB_CONCURRENCY`。
- 实现为 Redis ZSET 滑动窗口，**判定与写入在一段 Lua 脚本内完成**（原子），避免多进程并发下"检查再写入"被同时通过。
- **降级语义**：Redis 未安装、地址不可达或调用异常时，自动降级为进程内限流并打印告警（`WARNING`），请求不会被阻断。即降级=回到本节「默认」行为，**不是完全放行**；因此即便启用了 Redis，仍建议监控该告警。
- `redis` 为可选运行时依赖：未配置 `RATE_LIMIT_REDIS_URL` 时不会 import，缺少该包也不影响启动。
- 相关测试见 `tests/test_rate_limiter_redis.py`（本地内存版 Redis 替身，无网络依赖）。

- 管理员接口除限流外还受 `X-Admin-Secret` 鉴权与 CSRF 令牌双重保护。

## CSRF 令牌：当前行为与已接受风险

**签发与校验**

- 令牌由 `GET /api/csrf-token` 签发（该端点按 IP 限流 10 次/分钟），管理员 POST 端点经 `@csrf_protect` 校验。
- **一次性**：`@csrf_protect` 在校验通过后立即删除该令牌记录（`app/utils/api_helpers.py:214-222`），
  因此同一令牌无法用于第二次变更请求。前端 `templates/base.html` 亦在每次变更后清空本地缓存以匹配此语义。
- **有效期**：`_CSRF_TOKEN_TTL = 3600` 秒，过期令牌在校验时即被删除。

**残余风险（已接受）**

令牌**未绑定到会话/用户**：理论上，某会话签发的令牌若在**被使用前**泄露，可被其他客户端使用。

经评估按**低风险接受**，理由：

1. 攻击者要拿到令牌，需能读取 `/api/csrf-token` 的响应；同源策略（SOP）已阻止跨站读取，
   这正是该模式在端点无需鉴权的前提下仍然成立的原因。
2. 一次性语义使令牌在被合法使用后即失效，无法重放。
3. 1 小时 TTL 为未使用令牌的暴露窗口封顶。

**若要进一步收紧（会话绑定）**

需要在 `CSRFToken` 增加 `session_id` 列并做生产迁移，且**会打断不携带 cookie 的调用方**——
`CHANGELOG.md` v0.9.90 记录的运维流程即用 `curl` 直接取令牌后 POST（无 cookie jar）。
方案、风险与开关设计见 issue #170；在确认所有管理员调用方都会携带会话 cookie 之前，不实施。
