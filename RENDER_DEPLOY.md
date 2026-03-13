# Render 免费方案部署指南

## 📋 项目部署配置检查 ✅

### 已有的配置文件

1. **`Procfile`** - Render 启动配置
2. **`requirements.txt`** - Python 依赖列表
3. **`gunicorn.conf.py`** - Gunicorn 服务器配置
4. **`run.py`** - 应用启动入口
5. **`.env.example`** - 环境变量示例

---

## 🚀 部署步骤

### 第一步：准备 GitHub 仓库

确保你的代码已经推送到 GitHub：

```bash
# 检查 git 状态
git status

# 添加所有更改
git add .

# 提交更改
git commit -m "chore: prepare for Render deployment"

# 推送到 GitHub
git push origin main
```

---

### 第二步：在 Render 上创建新服务

1. 访问 [Render.com](https://render.com) 并登录
2. 点击 **"New +"** → **"Web Service"**
3. 连接你的 GitHub 账户（如果还没有）
4. 选择你的 `bookrank` 仓库
5. 配置服务：

| 配置项 | 值 |
|--------|-----|
| **Name** | `bookrank`（或你喜欢的名字） |
| **Region** | `Singapore`（新加坡，离中国近） |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn -c gunicorn.conf.py run:application` |

---

### 第三步：配置环境变量 ⚠️

在 Render 控制面板的 **"Environment"** 部分，添加以下环境变量：

#### 必填环境变量

| 变量名 | 说明 | 获取方式 |
|--------|------|---------|
| `SECRET_KEY` | Flask 安全密钥 | 自动生成或使用强随机字符串 |
| `NYT_API_KEY` | 纽约时报 API 密钥 | [developer.nytimes.com](https://developer.nytimes.com) |
| `GOOGLE_API_KEY` | Google Books API 密钥 | [console.cloud.google.com](https://console.cloud.google.com) |
| `ZHIPU_API_KEY` | 智谱 AI API 密钥（用于翻译） | [open.bigmodel.cn](https://open.bigmodel.cn) |

#### 可选环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `FLASK_ENV` | 运行环境 | `production` |
| `CACHE_TTL` | 缓存时间（秒） | `3600` |
| `API_RATE_LIMIT` | API 限流 | `20` |

#### 数据库配置

Render 会自动提供 `DATABASE_URL` 环境变量，无需手动配置！

---

### 第四步：添加 PostgreSQL 数据库（免费）

1. 在 Render 控制面板，点击 **"New +"** → **"PostgreSQL"**
2. 配置数据库：
   - **Name**: `bookrank-db`
   - **Region**: 选择和 Web Service 相同的区域（Singapore）
   - **Plan**: 选择 **Free** 套餐
3. 点击 **"Create Database"**
4. 数据库创建后，回到 Web Service 配置
5. 在 **"Environment"** → **"Environment Variables"** 中，点击 **"Add from Database"**
6. 选择刚创建的 `bookrank-db`
7. Render 会自动添加 `DATABASE_URL` 环境变量 ✅

---

### 第五步：部署！

1. 点击 **"Create Web Service"**
2. 等待 Render 自动构建和部署（首次可能需要 2-5 分钟）
3. 部署成功后，你会看到一个 `onrender.com` 域名，例如：
   - `https://bookrank.onrender.com`

---

## 🔧 Render 免费方案限制

### 免费套餐规格

| 资源 | 限制 |
|------|------|
| **Web Service** | 1 个，每月 750 小时 |
| **PostgreSQL** | 1 GB 存储，有限连接数 |
| **休眠** | 15 分钟无活动后休眠 |
| **带宽** | 100 GB/月 |

### 注意事项

1. **休眠问题**：免费版 15 分钟无访问会自动休眠，首次访问可能需要 10-30 秒唤醒
2. **数据库**：免费 PostgreSQL 只有 1GB 存储，足够 BookRank 使用
3. **构建时间**：每次推送都会触发重新构建

---

## 📊 部署后验证

### 检查日志

在 Render 控制面板 → **"Logs"** 标签页，查看应用日志，确认：

```
✅ 数据表已就绪
📦 初始化奖项数据...
🏢 初始化出版社数据...
🎉 数据库初始化完成
```

### 测试功能

访问你的部署网站，测试以下功能：

1. ✅ 首页加载
2. ✅ 畅销书榜单
3. ✅ 获奖书单
4. ✅ 新书速递
5. ✅ 出版社页面
6. ✅ 搜索功能
7. ✅ 翻译功能

---

## 🔄 持续部署

### 自动部署

Render 默认开启自动部署：
- 每次推送到 `main` 分支，会自动触发重新构建和部署
- 可以在 **"Settings"** → **"Build & Deploy"** 中关闭

### 手动部署

如果需要手动重新部署：
1. 进入 Render 控制面板
2. 点击 **"Manual Deploy"** → **"Deploy latest commit"**

---

## 🛠️ 常见问题

### 问题 1：部署失败，显示 "ModuleNotFoundError"

**解决方案**：
- 检查 `requirements.txt` 是否包含所有依赖
- 确保没有使用本地开发的包

### 问题 2：数据库连接失败

**解决方案**：
- 确认 PostgreSQL 数据库已创建
- 确认在 Web Service 中添加了数据库环境变量
- 检查数据库和 Web Service 在同一区域

### 问题 3：网站加载很慢

**解决方案**：
- 免费版会休眠，首次访问需要等待唤醒
- 可以使用外部监控服务（如 UptimeRobot）定期访问防止休眠

### 问题 4：API 密钥泄露

**解决方案**：
- 永远不要将 `.env` 文件提交到 git
- 在 Render 中设置环境变量，不要放在代码中

---

## 📝 升级到付费方案（可选）

如果需要更好的性能，可以考虑升级：

| 方案 | 价格 | 优势 |
|------|------|------|
| **Starter** | $7/月 | 不休眠，更多资源 |
| **Pro** | $35/月 | 更好的性能，更多数据库 |

---

## 🎉 完成！

部署成功后，你就有了一个可以公开访问的 BookRank 网站！

**你的网站地址**: `https://[你的服务名].onrender.com`

记得将这个地址分享给朋友们！ 🚀
