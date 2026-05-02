# BookRank 版本说明

## 当前版本：v0.5.1

### 项目概述
BookRank 是一个基于 Flask 的纽约时报畅销书排行榜网站，提供图书排名、奖项追踪、出版社导航、新书速递和自动生成周报等功能。

### 技术栈
- **后端**：Flask 3.1.3 + SQLAlchemy + PostgreSQL
- **前端**：Jinja2 模板 + 原生 JS（AJAX 无刷新交互）
- **API**：NYT Books API、Google Books API、Zhipu GLM API
- **部署**：Render 免费版
- **Python**：3.13

### v0.5.1 更新内容（2026-05-02）
- 修复 `/about` 页面 404 错误（新增路由和模板）
- 修复语言切换功能（新增 translations.js 翻译系统）
- 修复移动端侧边栏遮挡问题（宽度限制 + 遮罩层）

### v0.5.0 更新内容（2026-05-02）
- 新书速递页面全面优化：AJAX 无刷新筛选/分页/搜索
- NewBookService 单例模式 + N+1 查询修复
- 同步接口冷却时间限制（60秒）
- 批量同步优化（每10本提交一次）
- 骨架屏加载动画
- 搜索防抖（500ms）
- 暗色模式全面补全
- XSS 防护

### 环境变量配置
```
必需：SECRET_KEY, NYT_API_KEY, GOOGLE_API_KEY, ZHIPU_API_KEY, DATABASE_URL
可选：FLASK_ENV, CACHE_TTL, API_RATE_LIMIT
```

### API 配额限制
- NYT Books API：500 次/天
- Google Books API：1000 次/天