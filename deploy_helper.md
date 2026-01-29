# 部署助手

## ⚠️ 重要：保护你的 API 密钥

你的 `.env` 文件包含敏感的 API 密钥，**绝不能**推送到 GitHub！

## 当前状态

✅ 已创建 `.gitignore` 文件（排除 .env）
✅ 已创建 `.env.example` 模板文件
✅ 已从 Git 暂存区移除 .env

## 下一步操作

### 1. 创建新的干净仓库（推荐）

由于 `.env` 曾在 Git 历史中，最安全的方法是创建新仓库：

```bash
# 备份 .env 文件
copy .env .env.backup

# 删除 .git 目录
del /s /q .git
rmdir /s /q .git

# 重新初始化
git init
git config user.email "gongyijie85@example.com"
git config user.name "gongyijie85"

# 添加文件（.env 会被 .gitignore 自动排除）
git add .
git commit -m "Initial commit"

# 恢复 .env
copy .env.backup .env
```

### 2. 推送到 GitHub

```bash
# 在 GitHub 创建仓库后
git remote add origin https://github.com/gongyijie85/bookrank.git
git branch -M main
git push -u origin main
```

### 3. 在 Render 部署

1. 访问 https://dashboard.render.com
2. 使用 GitHub 登录
3. 点击 "New Web Service"
4. 选择 bookrank 仓库
5. 配置环境变量：
   - `NYT_API_KEY`: A80oHjtdSKQDLLuShe2jsB6GLbRrujL2
   - `SECRET_KEY`: （生成随机字符串）
   - `FLASK_ENV`: production

## 安全提醒

- ✅ `.env` 文件在 `.gitignore` 中
- ✅ `.env.example` 是安全的模板
- ❌ 永远不要推送真实的 `.env` 文件
- ❌ 如果意外推送，立即更换 API 密钥
