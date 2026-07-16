# BookRank 部署回滚 Runbook

**版本**：v1.0  
**生效日期**：2026-07-02  
**适用范围**：Render 生产环境（`bookrank` Web Service）  
**责任人**：项目维护者 / On-call 人员

---

## 一、回滚触发条件

出现以下任一情况时，应立即启动回滚：

1. 部署后 `/health/ready` 持续返回非 200 或 503，服务无法恢复。
2. Render Dashboard 显示服务反复 Crash / Restart，或内存超限（OOM）。
3. 核心功能（榜单展示、搜索、新书速递、周报生成）出现大面积不可用或数据异常。
4. 5xx 错误率显著上升（如 > 5%），或关键后台任务连续 2 次失败。
5. 数据库迁移后出现 schema/数据不一致，且无法在 10 分钟内修复。
6. 外部 API（NYT / Google Books）调用因本次变更导致配额异常消耗。

---

## 二、回滚前准备

### 2.1 确认当前版本

```powershell
# 查看当前部署的 Git commit
# 方式 1：Render Dashboard → Services → bookrank → Events
# 方式 2：访问 /api/health 或 /health/ready 查看响应头（如后续接入 commit hash）
```

### 2.2 确认有回滚目标

- **首选目标**：上一个已知稳定的 Git commit。
- **获取方式**：
  ```powershell
  git log --oneline -10
  # 选择故障 commit 前一个稳定的 commit
  ```

### 2.3 通知相关方

- 在运维群 / 邮件列表发送：`[BookRank 回滚通知] 因 XXX 问题，正在将生产环境回滚至 commit XXX，预计影响 X 分钟。`

---

## 三、回滚步骤

### 步骤 1：停止自动部署（关键）

当前 `render.yaml` 设置了 `autoDeploy: true`，回滚前必须先关闭，否则 Git 回滚会再次触发自动部署。

1. 登录 [Render Dashboard](https://dashboard.render.com)。
2. 进入 `bookrank` Web Service → **Settings**。
3. 找到 **Auto-Deploy**，切换为 **No**（或选择 "Deploy only when manually deployed"）。
4. 保存。

### 步骤 2：代码回滚

#### 场景 A：仅回滚最近一次提交

```powershell
cd d:\BookRank3
git log --oneline -3
# 确认最近一次提交是故障提交
git revert --no-edit HEAD
# 或如果需保留历史并生成新的 revert commit
git revert HEAD
```

#### 场景 B：回滚到指定 commit

```powershell
cd d:\BookRank3
git log --oneline -10
# 选择目标 commit，例如 abc1234
git checkout abc1234
# 创建回滚分支（推荐）
git checkout -b rollback/2026-07-02-abc1234
# 强制将 main 指向该 commit（仅当确定无其他人推送时使用）
git checkout main
git reset --hard abc1234
git push origin main --force-with-lease
```

> ⚠️ 强制推送会重写 main 分支历史，务必先与团队确认。

### 步骤 3：处理数据库迁移（如有）

BookRank 使用 Flask-Migrate / Alembic（见 `run.py` 第 76-114 行）。

1. **查看当前 Alembic 版本**：
   ```powershell
   flask db current
   ```

2. **如果回滚涉及数据库 schema 变更**：
   - 确认目标 commit 对应的 Alembic revision：
     ```powershell
     git show abc1234:migrations/alembic.ini
     # 或查看 migrations/versions 目录
     ```
   - 执行 downgrade（谨慎操作，生产环境建议先备份）：
     ```powershell
     # 示例：回滚到指定 revision
     flask db downgrade <target_revision>
     ```

3. **数据安全**：
   - 如变更涉及数据删除/更新且无法通过 downgrade 恢复，优先从备份恢复。
   - Render 免费层外部 PostgreSQL（Supabase）备份策略需在 `docs/supabase-migration.md` 中确认。

### 步骤 4：在 Render 上手动部署回滚版本

1. Render Dashboard → `bookrank` → **Manual Deploy** → **Deploy latest commit**。
2. 如果步骤 2 使用的是分支，选择 **Deploy a specific branch/commit**。
3. 等待构建完成（通常 1-3 分钟）。
4. 观察 **Events** 和 **Logs** 是否有错误。

### 步骤 5：验证回滚结果

```powershell
# 1. 基础健康检查
curl https://<your-render-domain>/health/ready
# 期望返回 HTTP 200，{"success":true,"status":"ready"}

# 2. 业务功能抽查
curl https://<your-render-domain>/api/books?category=hardcover-fiction
# 期望返回榜单数据，无 5xx

# 3. 检查 Render 日志中无 ERROR / FATAL
# Dashboard → Logs，搜索 "ERROR"、"Traceback"

# 4. 检查后台任务状态（如已接入监控）
# 查看 SystemConfig 中 last_report_failure、last_sync_failure 等字段
```

### 步骤 6：恢复或调整配置

- 如果回滚是因为 `WEB_CONCURRENCY=2` 导致 OOM，在 Render Dashboard 将 `WEB_CONCURRENCY` 改为 `1`。
- 如果回滚是因为 Dockerfile 构建问题，检查构建日志并修复。

### 步骤 7：恢复生产部署（可选）

- 确认问题修复并通过 CI 后，**不要**直接在 Render Dashboard 重新开启 `autoDeploy`。
- 生产部署应通过 CI 成功后的 Render Deploy Hook 触发（参见 `render.yaml` 与 `.github/workflows/ci.yml` 的 `deploy` job）。
- 如需临时手动部署，使用 Render Dashboard → **Manual Deploy** → **Deploy latest commit**。

---

## 四、回滚后检查清单

- [ ] Render Dashboard 中服务状态为 **Live**，无持续重启。
- [ ] `/health/ready` 返回 HTTP 200 且响应时间 < 2s。
- [ ] 至少 3 个核心页面/API 返回正常数据。
- [ ] Render Logs 中 5xx 数量归零或回到基线。
- [ ] 后台任务（如存在）在回滚后一个周期内成功执行。
- [ ] 已向团队发送回滚完成通知，说明根因和后续修复计划。

---

## 五、常见问题

### Q1：回滚后数据库连接仍然失败？

1. 检查 `DATABASE_URL` 环境变量是否正确。
2. 查看 Render / Supabase 的连接数是否耗尽。
3. 检查 `run.py` 中的惰性初始化是否因异常进入死锁，必要时重启服务。

### Q2：回滚后静态资源（CSS/JS）404？

1. 确认回滚版本中 `build.py` 已正确执行。
2. Render Dashboard → **Manual Deploy** → **Clear build cache & deploy**。

### Q3：不确定是代码问题还是数据库问题？

1. 先回滚代码并观察。
2. 若问题消失，则为代码问题。
3. 若问题仍存在，检查数据库连接、迁移版本和外部 API 状态。

---

## 六、相关文件

- `render.yaml`：Render 部署配置
- `.github/workflows/ci.yml`：CI 流水线
- `run.py`：启动入口与数据库初始化逻辑
- `gunicorn.conf.py`：Gunicorn 运行配置
- `docs/audits/audit-deployment-2026-07-02.md`：部署审计报告
- `docs/audits/audit-monitoring-2026-07-02.md`：监控审计报告

---

## 七、修订记录

| 版本 | 日期 | 修订内容 | 修订人 |
|---|---|---|---|
| v1.0 | 2026-07-02 | 初始版本，基于 Render 免费层与当前 CI/CD 配置编写 | Trae Agent |
