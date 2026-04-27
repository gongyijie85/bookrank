# Render 免费版数据库操作完全指南

本文档介绍如何操作 Render 免费版 PostgreSQL 数据库，提供三种方式。

---

## 📊 三种操作方式对比

| 方式 | 难度 | 推荐度 | 适用场景 |
|------|------|--------|---------|
| **Flask-Migrate** | ⭐ | ⭐⭐⭐⭐⭐ | 日常开发、表结构变更 |
| **数据库管理工具** | ⭐⭐ | ⭐⭐⭐ | 查看数据、手动修改 |
| **Render Web Shell** | ⭐⭐⭐ | ⭐⭐ | 紧急修复、调试 |

---

## 🚀 方式 1：Flask-Migrate（最推荐）

### 步骤 1：本地生成迁移

在你的电脑上，打开 PowerShell：

```powershell
# 进入项目目录
cd d:\BookRank3

# 运行一键配置脚本
python setup_render_db.py
```

或者手动执行：

```powershell
# 设置环境变量
$env:FLASK_APP = "app"
$env:FLASK_ENV = "development"

# 初始化迁移（第一次）
flask db init

# 生成迁移脚本
flask db migrate -m "Initial migration - all tables"

# 本地测试迁移
flask db upgrade
```

### 步骤 2：提交到 GitHub

```powershell
# 添加迁移文件
git add migrations/ Procfile

# 提交
git commit -m "feat: add database migrations for Render"

# 推送
git push origin main
```

### 步骤 3：Render 自动部署

推送后，Render 会自动：
1. 拉取代码
2. 运行 `flask db upgrade`（来自 Procfile）
3. 启动应用

**完成！** 🎉

---

## 🔧 方式 2：数据库管理工具（查看/修改数据）

### 推荐工具

| 工具 | 说明 | 下载 |
|------|------|------|
| **DBeaver** | 免费、跨平台、功能强大 | [dbeaver.io](https://dbeaver.io/) |
| **pgAdmin** | PostgreSQL 官方工具 | [pgadmin.org](https://www.pgadmin.org/) |
| **TablePlus** | 付费，但界面美观 | [tableplus.com](https://tableplus.com/) |

### 步骤 1：获取 Render 数据库连接信息

1. 登录 [Render.com](https://render.com)
2. 进入你的 PostgreSQL 数据库
3. 点击 **"Connections"** 标签
4. 复制 **"External Connection String"**

格式类似：
```
postgresql://用户名:密码@主机:端口/数据库名
```

### 步骤 2：使用 DBeaver 连接

1. 打开 DBeaver
2. 点击 **"New Database Connection"**
3. 选择 **PostgreSQL**
4. 粘贴 Render 的连接字符串，点击 **"Finish"**
5. 连接成功！可以查看/修改数据

### 安全提示
- 不要把连接字符串提交到 git
- 用完后可以在 Render 上重置密码

---

## 💻 方式 3：Render Web Shell（紧急修复）

### 步骤 1：打开 Web Shell

1. 登录 [Render.com](https://render.com)
2. 进入你的 Web Service
3. 点击 **"Shell"** 标签

### 步骤 2：连接数据库

在 Shell 中运行：

```bash
# 连接数据库（使用 Render 提供的 DATABASE_URL）
psql $DATABASE_URL
```

### 常用 SQL 命令

```sql
-- 查看所有表
\dt

-- 查看奖项数据
SELECT * FROM awards;

-- 查看获奖图书
SELECT * FROM award_books LIMIT 10;

-- 退出
\q
```

---

## 📝 常见数据库操作

### 修改表结构（使用 Flask-Migrate）

```powershell
# 1. 修改模型代码（app/models/schemas.py）

# 2. 生成新的迁移
flask db migrate -m "add new column to books"

# 3. 提交并推送
git add migrations/
git commit -m "feat: add new column"
git push

# 4. Render 自动部署并运行迁移
```

### 查看数据（使用 DBeaver）

1. 连接到 Render 数据库
2. 在左侧导航中展开表
3. 右键表 → **"View Data"**
4. 可以直接编辑数据（小心！）

### 手动修复数据（使用 Web Shell）

```bash
# 进入 Shell
psql $DATABASE_URL

# 例如：更新某条记录
UPDATE award_books 
SET is_displayable = true 
WHERE id = 123;

# 提交更改
COMMIT;
```

---

## ⚠️ 注意事项

### Render 免费版限制

| 限制 | 说明 |
|------|------|
| **存储** | 1 GB（足够 BookRank 使用） |
| **连接数** | 有限（我们已优化连接池） |
| **备份** | 免费版没有自动备份 |

### 安全最佳实践

1. **永远不要**把数据库连接字符串提交到 git
2. 使用 Flask-Migrate 做表结构变更，不要直接改表
3. 定期导出数据备份
4. 修改数据前先备份

---

## 🎯 推荐工作流

```
1. 本地开发（修改代码）
   ↓
2. 生成迁移（flask db migrate）
   ↓
3. 本地测试（flask db upgrade）
   ↓
4. 提交到 git
   ↓
5. Render 自动部署
   ↓
6. 自动运行 flask db upgrade
   ↓
7. 完成！
```

---

## ❓ 常见问题

### Q: Flask-Migrate 报错怎么办？
A: 检查：
1. 模型文件是否正确
2. 本地数据库是否正常
3. `FLASK_APP` 环境变量是否设置

### Q: 想查看数据库里的数据？
A: 用 DBeaver 连接，或者在 Render Web Shell 里用 `psql`

### Q: 数据误删了怎么办？
A: Render 免费版没有自动备份，建议：
1. 定期用 DBeaver 导出数据
2. 修改前先备份

### Q: 可以直接在数据库里改数据吗？
A: 可以，但推荐：
- **表结构变更**：用 Flask-Migrate
- **数据修改**：用 DBeaver 或 Web Shell

---

**需要帮助？随时问我！** 🚀
