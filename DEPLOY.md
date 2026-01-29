# 免费部署指南

本文档介绍如何将 BookRank 应用免费部署到云端。

## 推荐的免费部署平台

### 1. Render（推荐）
- **优点**: 免费 PostgreSQL 数据库、自动部署、自定义域名
- **限制**: 免费实例在 15 分钟无活动后会休眠，下次访问需要 30 秒启动
- **网址**: https://render.com

### 2. Railway
- **优点**: 使用简单、自动部署、免费 PostgreSQL
- **限制**: 每月 500 小时运行时间（约 20 天）
- **网址**: https://railway.app

### 3. PythonAnywhere
- **优点**: 永久运行、免费 MySQL 数据库
- **限制**: 每天限制 CPU 时间
- **网址**: https://www.pythonanywhere.com

---

## Render 部署步骤（详细）

### 步骤 1: 准备代码

确保以下文件已创建：
- `requirements.txt` - Python 依赖
- `Procfile` - 启动命令
- `gunicorn.conf.py` - Gunicorn 配置
- `render.yaml` - Render 部署配置

### 步骤 2: 注册 Render 账号

1. 访问 https://render.com
2. 点击 "Get Started for Free"
3. 使用 GitHub 账号登录（推荐）

### 步骤 3: 创建 PostgreSQL 数据库

1. 在 Render Dashboard 中，点击 "New +"
2. 选择 "PostgreSQL"
3. 配置：
   - Name: `book-rank-db`
   - Database: `bookrank`
   - User: `bookrank`
   - Plan: **Free**
4. 点击 "Create Database"
5. 等待数据库创建完成，复制 **Internal Database URL**

### 步骤 4: 部署 Web 服务

#### 方法 A: 使用 Blueprint（推荐）

1. 在 Render Dashboard 中，点击 "Blueprints"
2. 点击 "New Blueprint Instance"
3. 选择你的 GitHub 仓库
4. Render 会自动读取 `render.yaml` 文件
5. 点击 "Apply"

#### 方法 B: 手动创建

1. 在 Render Dashboard 中，点击 "New +"
2. 选择 "Web Service"
3. 选择你的 GitHub 仓库
4. 配置：
   - Name: `book-rank-app`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn -c gunicorn.conf.py run:application`
   - Plan: **Free**
5. 点击 "Advanced" 添加环境变量：
   - `FLASK_ENV`: `production`
   - `SECRET_KEY`: （点击 Generate 生成随机值）
   - `NYT_API_KEY`: `你的纽约时报API密钥`
   - `GOOGLE_API_KEY`: `你的Google Books API密钥`（可选）
   - `DATABASE_URL`: （粘贴步骤 3 复制的 Internal Database URL）
6. 点击 "Create Web Service"

### 步骤 5: 初始化数据库

1. 在 Render Dashboard 中，打开你的 Web Service
2. 点击 "Shell" 标签
3. 运行以下命令：
   ```bash
   python init_db.py
   ```
4. 等待显示 "数据库表创建成功！"

### 步骤 6: 访问应用

1. 等待部署完成（显示 "Live" 状态）
2. 点击页面上方的 URL 链接
3. 应用现在应该可以正常访问了！

---

## Railway 部署步骤

### 步骤 1: 注册 Railway 账号

1. 访问 https://railway.app
2. 使用 GitHub 账号登录

### 步骤 2: 创建项目

1. 点击 "New Project"
2. 选择 "Deploy from GitHub repo"
3. 选择你的仓库

### 步骤 3: 添加 PostgreSQL 数据库

1. 点击 "New"
2. 选择 "Database" → "Add PostgreSQL"
3. Railway 会自动创建数据库并设置 `DATABASE_URL` 环境变量

### 步骤 4: 配置环境变量

1. 点击你的 Web Service
2. 选择 "Variables" 标签
3. 添加以下变量：
   - `FLASK_ENV`: `production`
   - `NYT_API_KEY`: `你的API密钥`
   - `PORT`: `8000`

### 步骤 5: 部署

1. Railway 会自动部署
2. 等待部署完成
3. 点击 "Settings" → "Domain" 查看访问地址

---

## 获取 API 密钥

### 纽约时报 API 密钥

1. 访问 https://developer.nytimes.com
2. 注册账号
3. 创建新应用
4. 启用 "Books API"
5. 复制 API Key

### Google Books API 密钥（可选）

1. 访问 https://console.cloud.google.com
2. 创建新项目
3. 启用 "Books API"
4. 创建 API 密钥
5. 复制密钥

---

## 部署后注意事项

### 1. 免费套餐限制

| 平台 | 休眠 | 数据库 | 存储 |
|------|------|--------|------|
| Render | 15分钟无活动后休眠 | 免费 PostgreSQL | 1GB |
| Railway | 每月500小时 | 免费 PostgreSQL | 5GB |
| PythonAnywhere | 无 | 免费 MySQL | 512MB |

### 2. 优化建议

- **首次加载慢**: 免费实例休眠后首次访问需要 30 秒启动，这是正常的
- **API 限流**: NYT API 有每日限制，建议添加缓存
- **图片缓存**: 应用会自动缓存图片到本地磁盘

### 3. 监控日志

在 Render/Railway 控制台中可以查看应用日志，用于排查问题。

### 4. 更新部署

每次推送代码到 GitHub 主分支，平台会自动重新部署。

---

## 故障排除

### 问题: 应用启动失败

**解决**: 检查环境变量是否正确设置，特别是 `DATABASE_URL` 和 `NYT_API_KEY`

### 问题: 数据库连接错误

**解决**: 
1. 确认 PostgreSQL 服务已启动
2. 检查 `DATABASE_URL` 格式是否正确
3. 运行 `python init_db.py` 初始化数据库

### 问题: API 返回 500 错误

**解决**: 
1. 检查 `NYT_API_KEY` 是否有效
2. 查看应用日志获取详细错误信息

---

## 自定义域名（可选）

### Render

1. 在 Web Service 设置中，点击 "Custom Domains"
2. 添加你的域名
3. 按照说明配置 DNS

### Railway

1. 在 Service 设置中，点击 "Settings" → "Domain"
2. 点击 "Custom Domain"
3. 输入你的域名并配置 DNS

---

## 需要帮助？

- Render 文档: https://render.com/docs
- Railway 文档: https://docs.railway.app
- Flask 部署: https://flask.palletsprojects.com/en/2.3.x/deploying/
