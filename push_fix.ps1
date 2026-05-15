# BookRank Git 推送脚本
# 请在 PowerShell 中运行此脚本

$ErrorActionPreference = 'Stop'

Write-Host "=== BookRank Git 推送脚本 ===" -ForegroundColor Cyan

# 1. 添加修改的文件
Write-Host "`n[1/5] 添加修改的文件..." -ForegroundColor Yellow
git add app/routes/main.py templates/base.html static/js/base.js CHANGELOG.md VERSION.md README.md

# 2. 提交
Write-Host "`n[2/5] 提交更改..." -ForegroundColor Yellow
git commit -m "fix(i18n): 修复语言切换按钮状态不同步问题

- 消除竞态条件：base.html 和 base.js 同时更新按钮
- 统一语言初始化逻辑：内联脚本同步 localStorage，base.js 更新 UI
- 触发 languagechange 事件通知其他页面

版本：v0.9.8"

# 3. 拉取最新代码
Write-Host "`n[3/5] 拉取最新代码..." -ForegroundColor Yellow
git pull origin main --rebase --no-edit

# 4. 推送
Write-Host "`n[4/5] 推送到 GitHub..." -ForegroundColor Yellow
git push origin main

# 5. 验证
Write-Host "`n[5/5] 验证推送结果..." -ForegroundColor Yellow
git log --oneline -3

Write-Host "`n完成!" -ForegroundColor Green
