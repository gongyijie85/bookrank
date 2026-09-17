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

## 依赖漏洞现状（pip-audit）

CI 已接入 `pip-audit`（`Dependency Vulnerability Audit` job），**已是 branch protection 的必需检查**。

门禁语义为 **triage gate（例外登记）**：漏洞按公告 ID 逐一登记，
**未登记的漏洞 → job 失败 → 阻塞合并**；已登记的说明已评估，仅在日志中输出
`N ignored` 保持可见，**不会被静默吞掉**。例外清单维护在
`.github/workflows/ci.yml` 的 `dependency-audit` job 中（与理由放在一起，便于评审）。

**基线**：初次扫描 3 个包 / 12 条 → 升级 mistune 后 2 个包 / 11 条 → 移除 deep-translator 后
**1 个包 / 10 条记录（pyjwt，对应 6 个不同公告 ID，pip-audit 存在重复计数；均不可达，见下）**。

### ✅ 已处理

| 包 | 问题 | 处理 |
|---|---|---|
| mistune 3.3.0 | CVE-2026-76098（GitHub 评级 **high**，Mistune DoS RecursionError） | 升级至 **3.3.4**（修复在 3.3.3）。用于 Jinja `markdown` 过滤器，输出还经 bleach 消毒（纵深防御）。升级后 Dependabot open 告警归零 |
| deep-translator 1.11.4 | **PYSEC-2022-252（供应链投毒）** | **已从 requirements 中移除** |

### 🔴 关于 deep-translator：不是普通漏洞，是被投毒的包

OSV 原文（`https://osv.dev/vulnerability/PYSEC-2022-252`）：

> The deep-translator project on PyPI was taken over via user account compromise via a
> phishing attack and a new malicious release made which contained code which
> ... environment variables and downloaded and ran malware **at install time**

关键点：

- 受影响范围是 **1.8.5 及之后的所有版本**（含"最新"的 1.11.4）——所谓"无修复版本"，
  实质是项目被接管后**再无可信发布**。
- 危害是**安装期**读取环境变量并下载运行恶意代码。对我们尤其危险：
  Render 构建机上安装依赖时，环境变量里存放着各类凭据。
- 它是**可选回退**（`free_translation_service.py` 在 try/except 中导入，缺失即优雅降级），
  移除后仅失去 Google 翻译回退，主力（智谱）不受影响。

**结论**：已移除，并在 `requirements*.txt` 与模块 docstring 中写明原因，**在出现可信发布之前不要重新加入**。

### ⚠️ pyjwt 2.8.0（10 条记录 / 6 个公告 ID）：无升级路径，且已验证**不可达**

- **为何修不了**：由 `zhipuai==2.1.5.20250825` 锁定 `pyjwt>=2.8.0,<2.9.0`，
  而 zhipuai 已是 PyPI 最新版；修复版本需 2.12+/2.13，与上游约束冲突。
- **可达性分析（关键）**：本仓库代码**完全没有 import jwt**。
  zhipuai 内部仅在 `zhipuai/core/_jwt_token.py:26` 调用 `jwt.encode(...)`
  （生成调用智谱 API 的鉴权令牌），**从不执行 decode / 验签、不使用
  `PyJWKClient`、不处理 `algorithms` 白名单**。
- 而 OSV 上这些公告（含 4 条 HIGH）**全部位于解码/验签侧**：

  | 公告 | 等级 | 触发前提 | 本项目是否满足 |
  |---|---|---|---|
  | CVE-2026-32597（crit 头扩展） | HIGH | 解码并校验 token | ❌ 仅 encode |
  | CVE-2017-11424 / CVE-2022-29217（密钥混淆） | HIGH | 验签时公钥格式处理 | ❌ 仅 encode |
  | CVE-2026-48526（JWK 当 HMAC 密钥伪造 HS256） | HIGH | 解码时混用密钥族 | ❌ 仅 encode |
  | CVE-2026-48522（PyJWKClient SSRF/file） | MODERATE | 使用 JWKS 客户端拉取密钥 | ❌ 未使用 |
  | CVE-2026-48523（算法白名单绕过） | MODERATE | 用 PyJWK/PyJWKClient 解码 | ❌ 未使用 |
  | CVE-2026-48524/48525、CVE-2025-45768 | MODERATE/LOW | 解码侧 DoS | ❌ 仅 encode |

  📎 出处：<https://osv.dev/vulnerability/PYSEC-2026-120> 等（OSV / GHSA 记录）

**结论**：当前评级为**不可达**（accepted risk）。一旦出现下列任一变化需重新评估：
zhipuai 放宽 pyjwt 上限（应立即升级）、或引入任何 **JWT 校验/解码** 场景（届时必须先升级）。

**跟踪动作**：

- 关注 zhipuai 新版本是否放宽 `pyjwt` 上限，放宽后立即升级，并**把相应 ID 从 CI 的例外表中移除**。
- **新增例外必须同时在本文件写明理由与重新评估触发条件**，否则不得加入 CI 例外表。
- 未来若引入 JWT **校验/解码**场景，上述 4 条 HIGH 将由"不可达"变为可达，必须先升级 pyjwt 再落地。
