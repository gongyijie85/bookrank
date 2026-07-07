# BookRank 数据库备份与恢复 Runbook

**版本**: v1.0  
**生效日期**: 2026-07-02  
**适用范围**: Render 生产环境 + Supabase PostgreSQL  
**责任人**: 项目维护者 / On-call 人员

---

## 一、备份策略

### 1.1 备份频率

| 数据类型 | 频率 | 保留周期 | 工具 |
|----------|------|----------|------|
| 全库逻辑备份 | 每日 | 30 天 | `pg_dump` |
| 关键表备份（`book_metadata`、`award_books`、`weekly_reports`） | 每周 | 90 天 | `pg_dump --table` |
| 迁移前快照 | 手动 | 至少保留到验证通过 | `pg_dump` |

### 1.2 备份前检查清单

- [ ] 确认 `DATABASE_URL` 已配置且可连接。
- [ ] 确认本地有 `pg_dump`（PostgreSQL 客户端工具）。
- [ ] 选择备份存储位置（本地加密磁盘 / S3 / 其他云存储）。
- [ ] 避免在业务高峰期执行全库备份（可选 `pg_dump --lock-wait-timeout`）。

---

## 二、备份命令

### 2.1 全库逻辑备份

```bash
# 设置环境变量
export DATABASE_URL="postgresql://user:password@host:port/dbname"
export BACKUP_FILE="bookrank_backup_$(date +%Y%m%d_%H%M%S).sql"

# 执行全库备份（自定义格式，可压缩且支持选择性恢复）
pg_dump "$DATABASE_URL" \
  --format=custom \
  --file="$BACKUP_FILE" \
  --verbose \
  --no-owner \
  --no-privileges \
  --exclude-table='alembic_version'

# 验证文件大小
ls -lh "$BACKUP_FILE"
```

### 2.2 关键表逻辑备份

```bash
export BACKUP_FILE="bookrank_critical_$(date +%Y%m%d_%H%M%S).sql"

pg_dump "$DATABASE_URL" \
  --format=custom \
  --file="$BACKUP_FILE" \
  --verbose \
  --no-owner \
  --no-privileges \
  --table='book_metadata' \
  --table='award_books' \
  --table='awards' \
  --table='weekly_reports' \
  --table='new_books' \
  --table='publishers'
```

### 2.3 平文本备份（用于人工审阅）

```bash
export BACKUP_FILE="bookrank_plain_$(date +%Y%m%d_%H%M%S).sql"

pg_dump "$DATABASE_URL" \
  --format=plain \
  --file="$BACKUP_FILE" \
  --no-owner \
  --no-privileges \
  --data-only \
  --table='book_metadata'
```

---

## 三、恢复命令

### 3.1 全库恢复到新数据库

⚠️ **警告**：此操作会覆盖目标数据库。请先在隔离环境验证。

```bash
# 1. 创建新空数据库（在 Supabase Dashboard 或 psql 中执行）
# CREATE DATABASE bookrank_restore;

# 2. 设置目标数据库 URL
export TARGET_URL="postgresql://user:password@host:port/bookrank_restore"
export BACKUP_FILE="bookrank_backup_YYYYMMDD_HHMMSS.sql"

# 3. 恢复数据
pg_restore "$BACKUP_FILE" \
  --dbname="$TARGET_URL" \
  --verbose \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists

# 4. 验证表与行数
psql "$TARGET_URL" -c "\dt"
psql "$TARGET_URL" -c "SELECT COUNT(*) FROM book_metadata;"
psql "$TARGET_URL" -c "SELECT COUNT(*) FROM award_books;"
```

### 3.2 恢复到原数据库（灾难恢复）

仅在原数据库损坏且无法启动时使用：

```bash
# 1. 在 Render Dashboard 中暂停 Web Service，停止写入
# 2. 在 Supabase Dashboard 中删除或重命名损坏的数据库
# 3. 创建同名空数据库
# 4. 执行恢复
pg_restore "$BACKUP_FILE" \
  --dbname="$DATABASE_URL" \
  --verbose \
  --no-owner \
  --no-privileges

# 5. 重新运行迁移确保 schema 一致
flask db upgrade

# 6. 在 Render Dashboard 中重新启动 Web Service
```

### 3.3 单表恢复

```bash
export TARGET_URL="$DATABASE_URL"
export BACKUP_FILE="bookrank_critical_YYYYMMDD_HHMMSS.sql"

pg_restore "$BACKUP_FILE" \
  --dbname="$TARGET_URL" \
  --verbose \
  --no-owner \
  --no-privileges \
  --table='book_metadata' \
  --data-only
```

---

## 四、Render 外部数据库切换步骤

适用于从 Render 内置 PostgreSQL 迁移到 Supabase，或切换 Supabase 项目。

### 4.1 切换前准备

1. 在 Supabase 创建新项目，获取 **Session Pooler** 连接串。
2. 确认 `DATABASE_URL` 已包含 `sslmode=require`（`app/config.py` 会自动补齐）。
3. 执行全库备份：见 2.1。

### 4.2 切换到新数据库

```bash
# 1. 恢复数据到新 Supabase 数据库
pg_restore "$BACKUP_FILE" \
  --dbname="$NEW_DATABASE_URL" \
  --verbose --no-owner --no-privileges

# 2. 验证迁移版本
export DATABASE_URL="$NEW_DATABASE_URL"
flask db current
flask db heads

# 3. 运行任何缺失的迁移
flask db upgrade
```

### 4.3 更新 Render 环境变量

1. 登录 Render Dashboard → 选择 `bookrank` Web Service。
2. 找到 `DATABASE_URL`，更新为新的 Supabase Session Pooler URL。
3. 点击 **Save**。
4. 等待 Render 重新部署（因 `autoDeploy: false`，需手动触发 Deploy Hook 或 Render Dashboard 中点击 Manual Deploy）。

### 4.4 切换后验证

- [ ] `https://<your-app>.onrender.com/health/ready` 返回 `200`。
- [ ] 首页、榜单页、周报页可正常访问。
- [ ] 执行 `flask db current` 与 `flask db heads` 一致。
- [ ] 检查核心表行数与切换前一致。

---

## 五、数据验证检查清单

恢复或切换后，执行以下检查：

```bash
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM book_metadata;"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM award_books;"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM awards;"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM weekly_reports;"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM new_books;"
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM publishers;"

# 验证迁移版本
flask db current
```

---

## 六、应急回滚步骤

若切换新数据库后出现问题：

1. **立即停止服务**：在 Render Dashboard 中暂停 Web Service。
2. **切回旧数据库**：将 `DATABASE_URL` 改回旧值，保存并重新部署。
3. **通知用户**：通过状态页或邮件告知服务恢复中。
4. **事后复盘**：记录问题根因，必要时从备份恢复。

---

## 七、相关文件

- `app/config.py`：数据库连接池与 `DATABASE_URL` 处理
- `migrations/`：Alembic 迁移脚本
- `docs/runbooks/deployment-rollback.md`：部署回滚 Runbook
- `docs/runbooks/alerts.md`：监控告警 Runbook

---

## 八、修订记录

| 版本 | 日期 | 修订内容 | 修订人 |
|---|---|---|---|
| v1.0 | 2026-07-02 | 初始版本，定义备份/恢复/切换 SOP | Trae Agent |
