# BookRank 详情页修复 + 苹果风格 UI 改造计划

## 一、Bug 修复

### 1.1 书名/简介 Markdown 格式未渲染
**问题**：截图显示 `**书名：**《养兔记》**作者：**...` 这种 Markdown 格式文本直接显示
**原因**：后端返回的翻译文本包含 Markdown 标记（`**书名：**`），但前端没有 Markdown 渲染
**修复**：
- 方案 A：后端去除 Markdown 标记（推荐，简单可靠）
- 方案 B：前端引入 Markdown 渲染库
**选择**：方案 A — 在 `translate_book_info()` 中去除 `**` 标记

### 1.2 详情页没有中文翻译
**问题**：简介区域只有英文原文，没有中文翻译
**原因**：`_update_book_from_google_books()` 只更新英文 details/description，没有调用翻译服务
**修复**：在 `_fetch_google_books_details()` 获取详情后，调用翻译服务翻译 description 和 details

### 1.3 图标缺失检查
**问题**：详情页使用了 `#icon-building`, `#icon-calendar` 等图标引用
**检查**：确认 `static/icons.svg` 中是否包含这些图标定义
**修复**：如缺失，补充图标或改用 Font Awesome

### 1.4 详情页暗色模式不支持
**问题**：`book_detail.html` 中所有颜色都是硬编码
**修复**：将所有硬编码颜色替换为 CSS 变量，添加暗色模式覆盖规则

### 1.5 数据库迁移索引重复创建
**问题**：`idx_award_books_award_year_category` 索引已存在但迁移尝试重复创建
**修复**：迁移脚本中使用 `CREATE INDEX IF NOT EXISTS`

---

## 二、苹果风格 UI 改造

### 设计原则
- **大圆角**：卡片 20-24px，按钮 12-16px
- **毛玻璃效果**：导航栏、浮动元素使用 `backdrop-filter: blur(20px)`
- **柔和阴影**：`box-shadow: 0 4px 24px rgba(0,0,0,0.08)`
- **字体**：使用系统字体栈 `-apple-system, BlinkMacSystemFont, "SF Pro Text"`
- **强调色**：苹果蓝 `#007AFF`
- **留白**：增加元素间距，呼吸感
- **动画**：流畅的过渡动画，cubic-bezier(0.4, 0, 0.2, 1)

### 改造范围
1. **book_detail.html**：全面重写为苹果风格
2. **base.css**：添加苹果风格变量和工具类
3. **暗色模式**：同步适配苹果风格的暗色模式

---

## 三、实施步骤

### Phase 1: Bug 修复
1. [ ] 修复 Markdown 格式问题（后端去除 `**` 标记）
2. [ ] 修复详情页中文翻译（调用翻译服务）
3. [ ] 检查并修复图标缺失
4. [ ] 修复详情页暗色模式
5. [ ] 修复数据库迁移索引问题

### Phase 2: 苹果风格改造
6. [ ] 重写 book_detail.html 为苹果风格
7. [ ] 更新 base.css 添加苹果风格变量
8. [ ] 适配暗色模式

### Phase 3: 验证与提交
9. [ ] 本地验证所有修改
10. [ ] 提交并推送到 GitHub
