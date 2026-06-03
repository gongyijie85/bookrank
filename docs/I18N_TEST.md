# i18n 手动验证文档（v0.9.55）

> 本文档说明如何手动验证 BookRank3 的多语言切换、按需加载、骨架屏功能。
> 适合开发者在提交 PR 前后做回归测试。

---

## 一、自动化脚本（推荐）

项目内置 3 个 Playwright 端到端测试脚本，**必须全部通过**才能发布。

### 1.1 首页语言切换测试

```bash
cd d:/BookRank3
python scripts/_verify_i18n.py
```

**测试内容：**
- 初始中文 → 切到英文 → 卡片标题/作者/分类/排名/周数立即变英文
- 切到英文 → 切回中文 → 卡片立即变回中文
- 切换分类下拉框 option 文本应同步切换
- 时间格式：英文模式应显示 `Updated: Jun 3, 2026 8:08 AM`
- **切换过程不应触发任何新 API 请求**（关键性能指标）

**期望输出：**
```
=== 断言 ===
  [PASS] 标题变化
  [PASS] 分类标签变化
  [PASS] 排名徽章英文
  [PASS] 排名徽章中文
  [PASS] 周数英文
  [PASS] 周数中文
  [PASS] 下拉框 option 变化
  [PASS] 下拉框英文
  [PASS] 时间英文格式
  [PASS] 切回中文还原

=== 切到英文时 API 请求数: 0 ===
=== 切回中文时 API 请求数: 0 ===
```

### 1.2 按需加载 + 内存缓存测试

```bash
python scripts/_verify_cache.py
```

**测试内容：**
- 初始访问后 API 请求总数 = 0（已移除 8 分类预拉取）
- 首次切换到一个新分类 → 应触发 1 次 API 请求 + 显示 skeleton 占位
- 再次切换到同一分类 → 应直接命中内存缓存，0 API 请求
- 跨分类来回切换 → 仅首次每个分类消耗 1 次 API
- 切换语言时仍然 0 API 请求

**期望输出：**
```
=== 初始访问后 API 请求总数: 0 (期望: 0) ===
[PASS] 初始访问 0 API 请求（已移除预拉取）
[PASS] 切换分类时 skeleton 占位已显示
[PASS] 首次切换到新分类只消耗 1 次 API
[PASS] 再次访问 trade-fiction-paperback 命中缓存（0 API）
[PASS] 切换语言 0 API（按需加载保持原有行为）
```

### 1.3 详情页分类一致性测试

```bash
python scripts/_verify_detail_i18n.py
```

**测试内容：**
- 进入详情页，中文分类应显示"精装小说"
- 切到英文，分类应显示"Hardcover Fiction"（与首页一致）
- 切回中文，分类还原
- 切换过程 0 API 请求

**期望输出：**
```
=== 断言 ===
  [PASS] 中文分类含'精装': '精装小说'
  [PASS] 英文分类含'Hardcover/Fiction': 'Hardcover Fiction'
  [PASS] 切回中文还原: '精装小说'
  [PASS] 详情页切换语言 0 API
```

---

## 二、手动浏览器测试

如果不能用 Playwright（缺少 Chromium），可以人工跑以下步骤：

### 2.1 首页语言切换

1. 启动 Flask 开发服务器：`python run.py`
2. 浏览器打开 `http://127.0.0.1:8000/`
3. 打开 DevTools → Network 面板，过滤 `/api/`
4. 点击右上角语言按钮（🌐）→ 选 **English**
5. **预期：**
   - 卡片标题变成英文（"THE BALLAD OF FALLING DRAGONS"）
   - 卡片左上角分类变成 "Hardcover Fiction"
   - 排名徽章变成 "Rank 1"
   - 分类下拉框 option 变成英文
   - 时间显示 `Updated: Jun 3, 2026 8:08 AM`
   - **Network 面板不应有 `/api/` 请求**
6. 切回 **中文**，所有内容应立即变回中文

### 2.2 按需加载 + 骨架屏

1. 清空浏览器 localStorage（DevTools → Application → Clear storage）
2. 刷新页面，等 1-2 秒
3. **预期：**
   - Network 面板 **不应有 8 个** `/api/category-books` 请求
   - 页面正常显示当前分类（精装小说）的卡片
4. 点击分类下拉框 → 选 "平装小说"
5. **预期：**
   - 立即显示 8 个灰色骨架卡（带 shimmer 动画）
   - 300-800ms 后真实卡片替换骨架
   - Network 面板只有 1 个 `/api/category-books?category=trade-fiction-paperback` 请求
6. 再次选 "平装小说"（来回切到别的再切回来）
7. **预期：**
   - **没有骨架屏**（缓存命中）
   - 瞬时显示，无 API 请求
   - Network 面板 0 个新请求

### 2.3 详情页分类一致性

1. 在首页点任意一本书的封面 → 进入详情页
2. 默认中文态：分类字段应显示"精装小说"
3. 切到英文：分类字段应变成 "Hardcover Fiction"（与首页一致）
4. 切回中文：分类字段还原"精装小说"
5. **Network 面板 0 个 `/api/` 请求**

---

## 三、常见问题排查

### Q1: 切换语言后卡片没变

检查 `static/js/categories.js` 是否在 `translations.js` 之前加载：
```html
<script src="/static/js/categories.js"></script>
<script src="/static/js/translations.js"></script>
```
顺序错了会导致 `window.CATEGORIES` 未定义。

### Q2: skeleton 骨架屏不显示

- 检查 `static/css/animations.css` 里的 `.skeleton` 类是否生效
- 检查 `index.js` 里的 `showSkeleton()` 是否被调用
- 浏览器 Console 是否有 JS 报错

### Q3: 切换分类时还是 8 个 API 请求

检查 `index.js` 的 `DOMContentLoaded` 监听器，应该是空函数：
```js
document.addEventListener('DOMContentLoaded', function() { /* on-demand loading, no prefetch */ });
```
如果还有循环 fetch，说明没有正确升级到 v0.9.55。

### Q4: 详情页分类显示空白

检查 `book-i18n.js` 的 `_extractBookData` 函数：必须用 `categoryId && window.CATEGORIES.getLabel(...)`（带短路保护），否则 `category_id` 缺失时会清空元素。

---

## 四、性能基准

| 场景 | 期望 API 调用次数 | 期望响应时间 |
|---|---|---|
| 首次访问首页 | 0 | < 200ms（SSR） |
| 切换语言（zh ↔ en） | 0 | < 100ms（纯本地重渲染） |
| 首次切换到未访问过的分类 | 1 | 300-800ms（NYT API） |
| 再次切换到已访问分类 | 0 | < 50ms（内存缓存） |
| 进入详情页 | 0（首页内）或 1（直接 URL 进入） | - |

---

## 五、修改记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.9.55 | 2026-06-03 | 首次编写：3 个 Playwright 自动化脚本 + 手动测试步骤 |
