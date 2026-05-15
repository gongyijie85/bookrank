# BookRank - Render 免费版优化指南

本文档专门针对 Render 免费版进行优化，确保应用在 512MB 内存、1GB 数据库、15 分钟休眠限制下稳定运行。

---

## 🚀 立即要做的优化

### 1. 配置 UptimeRobot 防止休眠 ⚠️

**Render 免费版限制：** 15 分钟无访问会自动休眠

**解决方案：**

1. **注册 UptimeRobot（免费）**
   - 访问：https://uptimerobot.com
   - 注册免费账户

2. **添加监控**
   - 点击 **"Add New Monitor"**
   - 选择 **"HTTP(s)"** 类型
   - 配置：
     ```
     Friendly Name: BookRank Keepalive
     URL: https://你的服务名.onrender.com/health
     Monitoring Interval: 5 minutes
     ```
   - 点击 **"Create Monitor"**

3. **完成！** 每 5 分钟自动访问一次，防止休眠

---

### 2. 数据库迁移（本地操作）

**重要：** Render 上必须使用数据库迁移，不要依赖 `db.create_all()`

**本地操作步骤：**

```bash
# 1. 安装 Flask-Migrate（如果还没安装）
pip install Flask-Migrate

# 2. 运行迁移初始化脚本
python migrate_init.py

# 或者手动执行：
flask db init
flask db migrate -m "Initial migration - all tables"
flask db upgrade

# 3. 提交到 git
git add migrations/
git commit -m "feat: add database migrations"
git push
```

**Render 部署自动迁移：**

确保 `Procfile` 包含数据库迁移步骤：
```procfile
web: flask db upgrade && gunicorn -c gunicorn.conf.py run:application
```

---

### 3. Render 环境变量配置

在 Render 控制面板 → **Environment** → **Environment Variables** 中添加：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `SECRET_KEY` | 强随机字符串 | 用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成 |
| `FLASK_ENV` | `production` | 生产环境 |
| `NYT_API_KEY` | 你的 NYTimes API Key | [developer.nytimes.com](https://developer.nytimes.com) |
| `GOOGLE_API_KEY` | 你的 Google Books API Key | [console.cloud.google.com](https://console.cloud.google.com) |
| `ZHIPU_API_KEY` | 你的智谱 AI API Key | [open.bigmodel.cn](https://open.bigmodel.cn) |
| `CACHE_TTL` | `7200` | 缓存 2 小时 |
| `MEMORY_CACHE_TTL` | `600` | 内存缓存 10 分钟 |
| `WEB_CONCURRENCY` | `1` | 1 个 Worker（节省内存） |
| `GUNICORN_THREADS` | `2` | 每个 Worker 2 个线程 |

**数据库配置：**
- 在 Render 中添加 PostgreSQL 数据库（Free 套餐）
- 点击 **"Add from Database"** 自动添加 `DATABASE_URL`

---

## ⚙️ 已完成的优化（本项目已包含）

### ✅ 1. Gunicorn 配置优化
- 文件：`gunicorn.conf.py`
- 优化内容：
  - Worker 数从 2 → 1（节省内存）
  - 线程数从 4 → 2
  - 超时时间从 120 → 180 秒
  - 添加了内存清理钩子

### ✅ 2. 数据库连接池优化
- 文件：`app/config.py`
- 优化内容：
  - 连接池大小从 5 → 2
  - 最大溢出从 10 → 2
  - 连接回收从 1800 → 600 秒
  - 超时从 30 → 10 秒

### ✅ 3. 缓存策略优化
- 文件：`app/config.py` + `app/__init__.py`
- 优化内容：
  - 文件缓存 TTL 从 3600 → 7200 秒（2 小时）
  - 内存缓存 TTL 从 300 → 600 秒（10 分钟）
  - 内存缓存容量从 1000 → 2000 条

### ✅ 4. 健康检查端点
- 文件：`app/routes/health.py`
- 端点：
  - `/health` - 快速检查（用于 UptimeRobot）
  - `/health/detailed` - 详细检查
  - `/health/ready` - 就绪检查

---

## 📊 监控和诊断

### 查看 Render 日志
1. 进入 Render 控制面板
2. 选择你的服务
3. 点击 **"Logs"** 标签
4. 查看实时日志输出

### 健康检查端点
访问以下 URL 检查服务状态：

**简单健康检查（推荐用于监控）：**
```
https://你的服务名.onrender.com/health
```

**详细健康检查：**
```
https://你的服务名.onrender.com/health/detailed
```

响应示例：
```json
{
  "success": true,
  "status": "healthy",
  "service": "book-rank-api",
  "checks": {
    "database": true,
    "cache": true,
    "awards_count": 10,
    "books_count": 50,
    "publishers_count": 5,
    "memory_usage": "128.45 MB"
  }
}
```

---

## 💰 成本优化（完全免费！）

### 免费资源使用情况
| 资源 | 免费配额 | 预计使用 | 状态 |
|------|---------|---------|------|
| Web Service | 750 小时/月 | 720 小时/月 | ✅ 充足 |
| PostgreSQL | 1 GB 存储 | < 100 MB | ✅ 充足 |
| 带宽 | 100 GB/月 | < 5 GB | ✅ 充足 |

### 额外免费工具
- **UptimeRobot**：免费监控（50 个监控，5 分钟间隔）
- **Sentry**：免费错误追踪（5000 事件/月）
- **Better Stack**：免费日志管理

---

## 🚀 部署检查清单

部署到 Render 前，请确认：

- [ ] `.env.example` 文件完善（已完成）
- [ ] `gunicorn.conf.py` 已优化（已完成）
- [ ] 数据库连接池配置已优化（已完成）
- [ ] 缓存策略已优化（已完成）
- [ ] 健康检查端点已添加（已完成）
- [ ] 数据库迁移脚本已生成（需要本地操作）
- [ ] UptimeRobot 监控已配置（需要手动操作）
- [ ] Render 环境变量已配置（需要手动操作）
- [ ] PostgreSQL 数据库已创建（需要手动操作）

---

## ❓ 常见问题

### Q: 首次访问很慢？
A: Render 免费版会休眠，配置 UptimeRobot 即可解决。

### Q: 内存溢出（OOM）错误？
A: 确认 `WEB_CONCURRENCY=1`，不要增加 Worker 数。

### Q: 数据库连接失败？
A: 确认 PostgreSQL 已创建并添加到环境变量。

### Q: 如何更新数据库表结构？
A: 本地生成迁移脚本，提交后 Render 会自动运行 `flask db upgrade`。

---

## 📞 获取帮助

如遇问题：
1. 查看 Render 日志
2. 访问 `/health/detailed` 端点
3. 检查环境变量配置

---

**祝部署顺利！🎉**
