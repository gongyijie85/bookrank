# BookRank 代码简化、审查、修复计划

## 版本：v1.8.0

---

## 一、安全问题（最高优先级）

### 1.1 `.env` 文件泄露风险
- **现状**：`d:\.env` 包含真实 API 密钥（NYT、Google、百度翻译、腾讯翻译、XAI、OpenAI、ARK、Hardcover）
- **风险**：如果 `.env` 被提交到 GitHub，所有密钥将公开暴露
- **措施**：
  - 确认 `.gitignore` 已包含 `.env`（已确认）
  - 检查 Git 历史中是否曾提交过 `.env`（如有需清理）
  - 更新 `.env.example` 补充缺失的配置项说明

### 1.2 敏感信息硬编码检查
- 检查代码中是否有硬编码的 API Key 或密钥

---

## 二、代码简化（核心任务）

### 2.1 提取 `main.py` 中出版社数据
- **文件**：`app/routes/main.py`（当前 1023 行）
- **问题**：`publishers()` 路由内嵌 70+ 行出版社数据字典
- **方案**：提取到 `app/data/publishers.py`，路由中直接导入

### 2.2 拆分 `api.py` 管理端点
- **文件**：`app/routes/api.py`（当前 1482 行）
- **问题**：管理端点（`/api/admin/*`）与业务 API 混在一起
- **方案**：提取管理端点到 `app/routes/admin.py`，注册新蓝图

### 2.3 拆分 `api_client.py` 多客户端类
- **文件**：`app/services/api_client.py`（当前 1067 行）
- **问题**：5 个独立客户端类挤在一个文件
- **方案**：
  - `NYTApiClient` → `app/services/nyt_client.py`
  - `GoogleBooksClient` → 保留在 `api_client.py`（最核心）
  - `OpenLibraryClient` → `app/services/open_library_client.py`
  - `WikidataClient` → `app/services/wikidata_client.py`
  - `ImageCacheService` → 保留在 `api_client.py`
  - 公共工具函数（`create_session_with_retry`、`retry`、`_get_api_cache_service`、`_safe_cache_set`）→ `app/services/api_utils.py`
  - `api_client.py` 改为兼容导入入口（从新模块 re-export）

### 2.4 消除重复的 GoogleBooksClient 创建
- **问题**：`main.py`、`api.py`、`setup.py` 中多处创建 GoogleBooksClient 实例
- **方案**：统一从 `current_app.extensions` 获取，移除各处临时创建逻辑

### 2.5 清理冗余导入和重复代码
- `main.py`：移除重复的 `import threading`（行 3 和行 467）
- `main.py`：移除函数内 `import logging`（行 830）
- `api.py`：`_clean_report_text` 与 `weekly_report_service.py` 重复，统一使用后者

---

## 三、代码审查与修复

### 3.1 `main.py` 修复
1. **重复导入**：`threading` 在行 3 和行 467 重复导入
2. **函数内导入**：行 830 的 `import logging` 应使用模块顶部 logger
3. **`_merge_or_translate_book` 过于复杂**：嵌套 try-except 过深，简化逻辑
4. **`_translate_field_async` 线程管理**：创建的线程无引用，无法追踪或取消
5. **空行过多**：行 187-189 有 3 个连续空行

### 3.2 `api.py` 修复
1. **`clean_translation_text` 导入验证**：行 342 使用了 `clean_translation_text`，需确认导入链正确
2. **`_clean_report_text` 重复逻辑**：应统一使用 `weekly_report_service._format_book_title`
3. **`get_book_details` 中 GoogleBooksClient 创建**：应从 `current_app.extensions` 获取

### 3.3 `schemas.py` 修复
1. **`BookMetadata.to_dict` 中循环导入风险**：`from ..utils import quick_clean_translation` 在方法内导入

### 3.4 `.env.example` 更新
- 补充缺失的配置项：`BAIDU_FY_APP_ID`、`BAIDU_FY_APP_KEY`、`TENCENT_FY_SECRET_ID`、`TENCENT_FY_SECRET_KEY`、`XAI_API_KEY`、`ARK_API_KEY`、`HARDCOVER_API_TOKEN`
- 更新 `API_RATE_LIMIT` 默认值为 100（与 config.py 一致）

### 3.5 README.md 更新
- 更新技术栈版本号（Flask 3.1.3、Python 3.13）
- 更新版本号到 v1.8.0

---

## 四、执行顺序

| 步骤 | 任务 | 涉及文件 |
|------|------|----------|
| 1 | 安全检查：确认 `.env` 未被提交 | `.gitignore`、Git 历史 |
| 2 | 提取出版社数据 | `main.py` → `app/data/publishers.py` |
| 3 | 拆分管理端点 | `api.py` → `app/routes/admin.py` |
| 4 | 拆分 API 客户端 | `api_client.py` → 4 个新文件 + 兼容入口 |
| 5 | 消除重复 GoogleBooksClient 创建 | `main.py`、`api.py` |
| 6 | 修复代码问题 | `main.py`、`api.py`、`schemas.py` |
| 7 | 更新配置文件 | `.env.example`、`README.md` |
| 8 | 更新 CHANGELOG.md | `CHANGELOG.md` |
| 9 | 运行测试验证 | `pytest` |
| 10 | 提交并推送到 GitHub | Git 操作 |

---

## 五、不做的范围

- 不修改模板文件（HTML/CSS/JS）
- 不修改数据库模型结构
- 不修改爬虫逻辑
- 不修改翻译服务核心逻辑
- 不删除根目录脚本文件（需单独确认）
