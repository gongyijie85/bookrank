# BookRank Render Postgres -> Supabase Migration

这份清单用于把 BookRank 的数据库从 Render 免费 Postgres 迁到 Supabase Postgres。

## 先判断数据还能不能保住

如果 Render 显示 `Free database expired`，原库一般不能直接查询或导出。优先检查数据库是否还在 Render 的到期宽限期内：

- 还在宽限期内：先把 Render 数据库临时升级到付费实例，恢复访问后立刻导出，再迁到 Supabase。
- 已过宽限期：原库数据大概率已经无法恢复，只能在 Supabase 建空库并重新初始化基础数据。

不要在导出前删除 Render 数据库，也不要先把 Blueprint 同步到移除数据库资源的版本。

## 创建 Supabase 数据库

1. 在 Supabase 创建项目。
2. 进入 `Project Settings -> Database -> Connection string`。
3. 给 Render Web Service 优先使用 `Session Pooler` 连接串。它对 Render 这类 IPv4 环境更稳，也比 Transaction Pooler 更适合 SQLAlchemy 长连接。
4. 如果连接串里没有 `sslmode=require`，本项目会自动补上；手动写也可以。
5. 如果数据库密码含有 `@`, `/`, `#`, `?`, `&`, `%` 等字符，先 URL encode 后再放进连接串。

示例：

```text
postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

## 路径 A：保留 Render 原数据

前提：Render 原库可以重新访问。

在本机 PowerShell 里设置两个临时环境变量，不要写入代码仓库：

```powershell
$env:RENDER_DATABASE_URL = "postgresql://render_user:render_password@render_host:5432/render_db"
$env:SUPABASE_DATABASE_URL = "postgresql://postgres.PROJECT_REF:supabase_password@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
```

导出 Render：

```powershell
pg_dump --format=custom --no-owner --no-acl --file .\bookrank_render.dump $env:RENDER_DATABASE_URL
```

导入 Supabase：

```powershell
pg_restore --clean --if-exists --no-owner --no-acl --dbname $env:SUPABASE_DATABASE_URL .\bookrank_render.dump
```

只读核验连接与 Alembic 版本（不会迁移或验证业务行数）：

```powershell
$env:DATABASE_URL = $env:SUPABASE_DATABASE_URL
$env:DISABLE_BACKGROUND_THREADS = "true"
python scripts/init_external_postgres.py
```

确认无误后清理本机临时环境变量：

```powershell
Remove-Item Env:\RENDER_DATABASE_URL
Remove-Item Env:\SUPABASE_DATABASE_URL
Remove-Item Env:\DATABASE_URL
Remove-Item Env:\DISABLE_BACKGROUND_THREADS
```

## 路径 B：原数据已无法恢复，重建 Supabase 空库

以下属于显式数据库写入流程，须在备份、隔离演练及单独批准后执行。
先准备专用的空 schema（例如 `bookrank_empty`），不要对已有或无版本旧库直接标记当前版本。

```powershell
$env:DATABASE_URL = "postgresql://postgres.PROJECT_REF:supabase_password@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
$env:DISABLE_BACKGROUND_THREADS = "true"
python scripts/init_external_postgres.py --bootstrap-empty-schema --schema bookrank_empty --seed-base-data
```

脚本拒绝 public、系统 schema 或任何已有对象；按已审查的当前基线，在同一事务中创建模型及迁移补充对象并写入版本。
播种是单独的数据事务，空或部分失败会报错，已提交记录可能保留；应先检查结果，不能盲目重投。
应用连接必须显式配置同一 `search_path`，脚本不会更改生产连接配置或权限。
已有合法版本的库另用 `--upgrade`；默认无参数仅只读核验，不自动加载 `.env`、建表、迁移或播种。

## 切换 Render Web Service

1. 在 Render Web Service 的 Environment 里设置：

```text
DATABASE_URL=你的 Supabase Session Pooler URL
```

2. 保留已有的 `SECRET_KEY`, `ADMIN_SECRET`, `CRON_SECRET`, API key 等环境变量。
3. 推送包含本次配置变更的代码。`render.yaml` 现在不会再创建 Render 数据库，只会要求手动配置 `DATABASE_URL`。
4. 重新部署 Web Service。

验证：

```powershell
Invoke-WebRequest -Uri "https://你的域名/api/health"

$headers = @{ "X-Admin-Secret" = "你的 ADMIN_SECRET" }
Invoke-RestMethod -Uri "https://你的域名/api/admin/system/status" -Headers $headers
```

`/api/admin/system/status` 里数据库类型应为 `postgresql`。

## 可选：使用应用 JSON 备份

如果旧应用还能启动，也可以先导出一份应用层备份：

```powershell
$headers = @{ "X-Admin-Secret" = "你的 ADMIN_SECRET" }
Invoke-WebRequest -Uri "https://旧域名/api/admin/backup/export" -Headers $headers -OutFile .\bookrank_backup.json
```

导入接口是 `POST /api/admin/backup/import`。它适合作为补充备份；完整数据库迁移仍优先使用 `pg_dump` / `pg_restore`。

