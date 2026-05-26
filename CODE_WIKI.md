# BookRank Code Wiki

> 版本: v0.6.0+ | 最后更新: 2026-05-22

---

## 一、项目概览

**BookRank** 是一个基于 Flask 的纽约时报（NYT）畅销书排行榜 Web 应用，提供：

- NYT 畅销书榜单浏览与搜索
- 国际图书奖项（普利策、布克奖等）展示
- 五大出版社新书速递（爬虫自动同步）
- 智谱 AI 驱动的中英翻译
- 每周畅销书报告自动生成与邮件推送
- AI 智能图书推荐
- PDF/Excel 导出

技术栈：Python 3.13 / Flask 3.1 / SQLAlchemy 2.0 / PostgreSQL / APScheduler / 智谱AI GLM-4.7-Flash

部署平台：Render 免费版（512MB 内存 / 97 连接 PostgreSQL）

---

## 二、项目架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                      前端 (Jinja2 模板)                    │
│  index.html / awards.html / new_books.html / weekly_*.html │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / AJAX
┌────────────────────────▼─────────────────────────────────┐
│                    Flask 路由层 (Blueprints)               │
│  main_bp │ api_bp │ admin_bp │ public_api_bp │ new_books_bp │
│  health_bp │ analytics_bp                                    │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                     服务层 (Services)                      │
│  BookService │ NewBookService │ AwardBookService           │
│  WeeklyReportService │ UserService │ RecommendationService │
│  ZhipuTranslationService │ CacheService │ ExportService    │
│  SmartSearchService │ BookLanguagePack                     │
└──────────┬──────────────┬──────────────┬──────────────────┘
           │              │              │
┌──────────▼──────┐ ┌────▼────────┐ ┌───▼───────────────┐
│   外部 API 客户端  │ │   数据模型层   │ │  爬虫子系统        │
│ NYTApiClient    │ │ Book(dataclass)│ │ BaseCrawler       │
│ GoogleBooksClient│ │ BookMetadata  │ │ GoogleBooksCrawler│
│ OpenLibraryClient│ │ AwardBook     │ │ PenguinRHCrawler  │
│ WikidataClient  │ │ NewBook       │ │ HachetteCrawler   │
│                 │ │ WeeklyReport  │ │ HarperCollinsCrawler│
│                 │ │ TranslationCache│ │ MacmillanCrawler │
│                 │ │ APICache      │ │ SimonSchusterCrawler│
│                 │ │ SystemConfig  │ │ OpenLibraryCrawler│
└─────────────────┘ └───────────────┘ └───────────────────┘
```

### 2.2 分层职责

| 层级 | 目录 | 职责 |
|------|------|------|
| 入口 | `run.py` | Render 部署入口，惰性数据库初始化 |
| 应用工厂 | `app/__init__.py` | `create_app()` 创建 Flask 实例，注册蓝图/扩展/中间件 |
| 配置 | `app/config.py` | 三环境配置（Development/Production/Testing） |
| 路由 | `app/routes/` | 7 个 Blueprint，处理 HTTP 请求 |
| API 路由 | `app/routes/api/` | RESTful API 子模块（books/translation/cache/awards/recommendations） |
| 服务 | `app/services/` | 业务逻辑层，路由层通过 Service 操作数据 |
| 爬虫 | `app/services/publisher_crawler/` | 出版社网站爬虫子系统 |
| 模型 | `app/models/` | 数据类（Book dataclass）+ SQLAlchemy ORM 模型 |
| 验证 | `app/schemas/validators.py` | Pydantic 输入验证模型 |
| 工具 | `app/utils/` | 异常体系、API 响应、限流、安全、服务定位 |
| 任务 | `app/tasks/` | 后台定时任务（周报生成） |
| 初始化 | `app/initialization/` | 奖项/样本书籍种子数据 |
| 静态数据 | `app/data/` | 出版社元数据配置 |

---

## 三、目录结构详解

```
BookRank3/
├── app/                          # 应用主目录
│   ├── __init__.py               # 应用工厂 create_app()
│   ├── config.py                 # 配置类（Development/Production/Testing）
│   ├── setup.py                  # 服务初始化 + APScheduler 后台任务管理
│   ├── models/                   # 数据模型
│   │   ├── book.py               # Book dataclass（业务数据对象）
│   │   ├── database.py           # SQLAlchemy db 实例 + init_db()
│   │   ├── schemas.py            # ORM 模型（BookMetadata, AwardBook, WeeklyReport 等）
│   │   └── new_book.py           # NewBook + Publisher ORM 模型
│   ├── routes/                   # 路由层
│   │   ├── main.py               # 主页面路由（首页/奖项/新书/周报/详情）
│   │   ├── admin.py              # 管理后台路由
│   │   ├── health.py             # 健康检查路由
│   │   ├── analytics_bp.py       # 数据统计路由
│   │   ├── new_books.py          # 新书速递 API 路由
│   │   ├── public_api.py         # 公开 API（/api/public/）
│   │   └── api/                  # 内部 API 子模块
│   │       ├── books.py          # 图书 API
│   │       ├── translation.py    # 翻译 API
│   │       ├── cache.py          # 缓存管理 API
│   │       ├── awards.py         # 奖项 API
│   │       └── recommendations.py# 推荐 API
│   ├── services/                 # 服务层
│   │   ├── book_service.py       # 图书核心服务
│   │   ├── new_book_service.py   # 新书速递服务
│   │   ├── award_book_service.py # 获奖图书服务
│   │   ├── weekly_report_service.py# 周报服务
│   │   ├── user_service.py       # 用户行为服务
│   │   ├── recommendation_service.py# AI 推荐服务
│   │   ├── zhipu_translation_service.py# 智谱翻译服务
│   │   ├── free_translation_service.py # 免费翻译回退
│   │   ├── cache_service.py      # 缓存服务（内存+文件）
│   │   ├── api_cache_service.py  # API 缓存服务（数据库层）
│   │   ├── translation_cache_service.py# 翻译缓存服务
│   │   ├── export_service.py     # PDF/Excel 导出服务
│   │   ├── smart_search_service.py# 智能搜索服务
│   │   ├── book_language_pack.py # 语言包管理
│   │   ├── book_verification_service.py# 书籍验证服务
│   │   ├── award_cover_sync_service.py# 封面同步服务
│   │   ├── api_client.py         # API 客户端兼容入口
│   │   ├── api_utils.py          # API 工具函数
│   │   ├── nyt_client.py         # NYT API 客户端
│   │   ├── google_books_client.py# Google Books API 客户端
│   │   ├── open_library_client.py# Open Library API 客户端
│   │   ├── wikidata_client.py    # Wikidata API 客户端
│   │   └── publisher_crawler/    # 出版社爬虫子系统
│   │       ├── base_crawler.py   # 爬虫基类（HTTP重试/robots.txt/分页）
│   │       ├── google_books.py   # Google Books 爬虫
│   │       ├── google_books_publisher.py # Google Books 出版社爬虫
│   │       ├── open_library.py   # Open Library 爬虫
│   │       ├── penguin_random_house.py # 企鹅兰登爬虫
│   │       ├── hachette.py       # Hachette 爬虫
│   │       ├── harpercollins.py  # HarperCollins 爬虫
│   │       ├── macmillan.py      # Macmillan 爬虫
│   │       ├── simon_schuster.py # Simon & Schuster 爬虫
│   │       ├── rss_crawler.py    # RSS 爬虫
│   │       └── mixed_crawl4ai_crawler.py # Crawl4AI 混合爬虫
│   ├── schemas/
│   │   └── validators.py         # Pydantic 验证模型
│   ├── utils/                    # 工具模块
│   │   ├── api_helpers.py        # API 响应/CSRF/限流装饰器
│   │   ├── exceptions.py         # 自定义异常体系
│   │   ├── rate_limiter.py       # 速率限制器
│   │   ├── security.py           # 安全工具（URL验证等）
│   │   ├── admin_auth.py         # 管理员认证
│   │   ├── error_tracker.py      # 错误追踪器
│   │   └── service_helpers.py    # 服务定位器
│   ├── tasks/
│   │   └── weekly_report_task.py # 周报生成任务
│   ├── initialization/           # 种子数据
│   │   ├── awards.py             # 奖项初始化
│   │   ├── sample_books.py       # 样本书籍
│   │   └── sample_award_books.py # 样本获奖书籍
│   └── data/
│       └── publishers.py         # 出版社元数据配置
├── static/                       # 静态资源
│   ├── css/                      # 样式（base/components/animations/new-books）
│   ├── js/                       # JavaScript（app/api/components/store/i18n）
│   ├── data/                     # JSON 数据文件（语言包/出版社数据）
│   └── fonts/                    # 字体文件
├── templates/                    # Jinja2 模板
│   ├── base.html                 # 基础布局
│   ├── index.html                # 首页
│   ├── awards.html               # 奖项页
│   ├── new_books.html            # 新书页
│   ├── weekly_reports.html       # 周报列表
│   ├── weekly_report_detail.html # 周报详情
│   ├── emails/                   # 邮件模板
│   └── ...                       # 其他页面模板
├── tests/                        # 测试目录
├── migrations/                   # Alembic 数据库迁移
├── scripts/                      # 运维脚本
├── translations/                 # Flask-Babel 国际化（en/zh）
├── run.py                        # Render 部署入口
├── update_books.py               # 手动数据更新脚本
├── build.py                      # CSS 压缩构建脚本
├── Dockerfile                    # Docker 构建文件
├── gunicorn.conf.py              # Gunicorn 配置
├── pyproject.toml                # Ruff + mypy 配置
├── pytest.ini                    # pytest 配置
├── Makefile                      # 快捷命令
├── requirements.txt              # 依赖（含开发工具）
├── requirements-prod.txt         # 生产依赖（精简）
└── render.yaml                   # Render 部署配置
```

---

## 四、核心模块详解

### 4.1 应用工厂 (`app/__init__.py`)

**核心函数**：`create_app(config_name) -> Flask`

启动流程：

1. 创建 Flask 实例，加载对应环境配置
2. 初始化扩展（CORS、数据库、邮件、Babel 国际化）
3. 注册 7 个 Blueprint
4. 注册全局错误处理器（400/404/405/429/500）
5. 配置日志
6. 应用安全响应头（CSP nonce / X-Frame-Options / HSTS / gzip）
7. 生产环境启用速率限制
8. 注册 Jinja2 自定义过滤器
9. `atexit` 注册调度器关闭回调

**语言选择优先级**：URL 参数 `?lang=` > Cookie `lang` > Accept-Language > 默认 `en`

### 4.2 配置体系 (`app/config.py`)

| 配置类 | 环境 | 关键差异 |
|--------|------|----------|
| `DevelopmentConfig` | 本地开发 | DEBUG=True, SQLite, 无连接池限制 |
| `ProductionConfig` | Render 生产 | SECRET_KEY 强制, pool_size=2, max_overflow=1, CORS 白名单 |
| `TestingConfig` | 测试 | 内存 SQLite, CSRF 禁用 |

**关键配置项**：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `NYT_API_KEY` | 环境变量 | NYT Books API 密钥 |
| `GOOGLE_API_KEY` | 环境变量 | Google Books API 密钥 |
| `ZHIPU_API_KEY` | 环境变量 | 智谱 AI 翻译密钥 |
| `DATABASE_URL` | SQLite | 数据库连接（自动处理 `postgres://` 前缀） |
| `CACHE_DEFAULT_TIMEOUT` | 7200 | 缓存 TTL（秒） |
| `API_RATE_LIMIT` | 100 | API 速率限制（次/分钟） |
| `CATEGORIES` | 8 个分类 | NYT 榜单分类映射 |
| `NYT_RANKING_SYNC_DAYS` | 7 | 排行榜同步间隔（天） |

### 4.3 服务初始化与后台任务 (`app/setup.py`)

**`init_services(app)`** 初始化链：

```
MemoryCache + FileCache → CacheService → NYTApiClient → GoogleBooksClient
→ ImageCacheService → TranslationService → BookService → 启动后台任务
```

**APScheduler 后台任务**：

| 任务 ID | 名称 | 调度策略 | 说明 |
|---------|------|----------|------|
| `weekly_report_init` | 周报启动检查 | 一次性（5/30分钟后） | 启动时检查是否需要生成周报 |
| `auto_sync` | 新书速递自动同步 | 每14天 | 同步出版社新书数据 |
| `nyt_ranking_sync` | NYT 排行榜语言包同步 | 每7天 | 刷新榜单 + 翻译 + 写入语言包 |
| `cover_sync_init` | 获奖书籍封面同步 | 一次性（60/120秒后） | 补全缺失封面 |
| `translation_cache_cleanup` | 翻译缓存自动清理 | 每30分钟 | 清理过期翻译缓存 |

**数据刷新回调**：`BookService.on_data_refreshed()` 注册回调，排行榜刷新后自动触发周报生成。

---

## 五、数据模型

### 5.1 业务数据类

#### `Book` (dataclass, `app/models/book.py`)

纯数据对象，不绑定数据库，用于 API 响应和页面渲染。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | ISBN 或 MD5 哈希 |
| `title` / `title_zh` | str / str\|None | 原文书名 / 中文书名 |
| `author` | str | 作者 |
| `publisher` | str | 出版社 |
| `rank` | int | 排名 |
| `weeks_on_list` | int | 上榜周数 |
| `isbn13` / `isbn10` | str | ISBN 编号 |
| `buy_links` | list[dict] | 购买链接 |
| `description_zh` / `details_zh` | str\|None | 中文翻译 |

关键方法：
- `from_api_response()` — 从 NYT API 响应构造 Book 对象
- `to_dict()` — 序列化为字典（自动清理翻译数据）

### 5.2 ORM 模型 (`app/models/schemas.py`)

| 模型 | 表名 | 说明 |
|------|------|------|
| `BookMetadata` | book_metadata | 书籍元数据缓存（含中文翻译字段） |
| `Award` | awards | 国际图书奖项 |
| `AwardBook` | award_books | 获奖图书（含验证状态、封面路径） |
| `TranslationCache` | translation_cache | 翻译缓存（源文本哈希 + 翻译结果） |
| `APICache` | api_cache | 外部 API 响应缓存 |
| `SystemConfig` | system_config | 系统配置键值对 |
| `WeeklyReport` | weekly_reports | 每周报告（JSON 内容） |
| `ReportView` | report_views | 周报阅读记录 |
| `UserPreference` | user_preferences | 用户偏好（视图模式、关注分类） |
| `UserCategory` | user_categories | 用户关注分类 |
| `UserViewedBook` | user_viewed_books | 用户浏览记录 |
| `SearchHistory` | search_history | 搜索历史 |
| `UserBehavior` | user_behaviors | 用户行为数据 |
| `CSRFToken` | csrf_tokens | CSRF 令牌（数据库存储） |

### 5.3 新书模型 (`app/models/new_book.py`)

| 模型 | 表名 | 说明 |
|------|------|------|
| `Publisher` | publishers | 出版社（含爬虫类名、同步状态） |
| `NewBook` | new_books | 新书（含中英双语、封面、ISBN、验证状态） |

---

## 六、路由层

### 6.1 Blueprint 注册表

| Blueprint | URL 前缀 | 文件 | 说明 |
|-----------|----------|------|------|
| `main_bp` | `/` | `routes/main.py` | 主页面（首页/奖项/新书/周报/详情/关于） |
| `api_bp` | `/api` | `routes/api/` | 内部 RESTful API |
| `public_api_bp` | `/api/public` | `routes/public_api.py` | 公开 API（无需认证） |
| `admin_bp` | `/admin` | `routes/admin.py` | 管理后台 |
| `new_books_bp` | `/new-books/api` | `routes/new_books.py` | 新书速递 API |
| `health_bp` | `/health` | `routes/health.py` | 健康检查 |
| `analytics_bp` | `/analytics` | `routes/analytics_bp.py` | 数据统计 |

### 6.2 主要页面路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（畅销书榜单，支持分类/搜索/排序/筛选） |
| `/awards` | GET | 图书奖项页面 |
| `/new-books` | GET | 新书速递页面 |
| `/book/<int:book_index>` | GET | 畅销书详情 |
| `/award-book/<int:book_id>` | GET | 获奖图书详情 |
| `/new-book/<int:book_id>` | GET | 新书详情（异步翻译） |
| `/reports/weekly` | GET | 周报列表 |
| `/reports/weekly/<date>` | GET | 周报详情 |
| `/reports/weekly/<date>/export` | GET | 导出周报（PDF/Excel） |
| `/about` | GET | 关于页面 |
| `/publishers` | GET | 出版社导航 |
| `/set-language` | GET | 切换语言（写 Cookie） |

### 6.3 API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/books/<category>` | GET | 获取分类图书 |
| `/api/books/search` | GET | 搜索图书 |
| `/api/books/<isbn>/metadata` | GET | 获取书籍元数据 |
| `/api/translate` | POST | 翻译文本 |
| `/api/translate/book-fields` | POST | 翻译书籍字段 |
| `/api/awards` | GET | 获取奖项列表 |
| `/api/awards/<id>/books` | GET | 获取获奖图书 |
| `/api/recommendations` | GET | 获取推荐图书 |
| `/api/cache/stats` | GET | 缓存统计 |
| `/api/csrf-token` | GET | 获取 CSRF 令牌 |
| `/api/health` | GET | API 健康检查 |
| `/api/public/bestsellers` | GET | 公开畅销书 API |
| `/api/public/bestsellers/<category>` | GET | 公开分类畅销书 API |

---

## 七、服务层

### 7.1 核心服务

#### `BookService` (`app/services/book_service.py`)

图书业务核心服务，整合 NYT API、Google Books API、缓存和翻译。

| 方法 | 说明 |
|------|------|
| `get_books_by_category(category_id)` | 获取指定分类图书（缓存优先） |
| `sync_all_categories(force_refresh, translate)` | 同步所有分类数据 |
| `get_book_by_isbn(isbn)` | 通过 ISBN 查找图书 |
| `on_data_refreshed(callback)` | 注册数据刷新回调 |
| `get_cache_time(category_id)` | 获取缓存更新时间 |

依赖：`NYTApiClient`、`GoogleBooksClient`、`CacheService`、`ImageCacheService`、`BookLanguagePack`

#### `NewBookService` (`app/services/new_book_service.py`)

新书速递服务，管理爬虫、数据同步和翻译。

| 方法 | 说明 |
|------|------|
| `init_publishers()` | 初始化出版社数据 |
| `sync_all_publishers()` | 同步所有出版社新书 |
| `get_new_books(publisher_id, category, days, page, per_page)` | 分页获取新书 |
| `search_books(keyword, page, per_page)` | 搜索新书 |
| `get_publishers(active_only)` | 获取出版社列表 |
| `get_statistics()` | 获取统计数据 |
| `translate_book_background(book_id, translator)` | 后台翻译新书 |

#### `AwardBookService` (`app/services/award_book_service.py`)

获奖图书服务。

| 方法 | 说明 |
|------|------|
| `get_all_awards()` | 获取所有奖项 |
| `get_award_books(award_id, year, page, limit)` | 获取获奖图书 |
| `get_book_counts_by_award()` | 各奖项图书计数 |
| `get_distinct_years()` | 获取年份列表 |

#### `WeeklyReportService` (`app/services/weekly_report_service.py`)

周报服务，自动生成和邮件推送。

| 方法 | 说明 |
|------|------|
| `get_reports()` | 获取周报列表 |
| `get_report_by_date(date)` | 按日期获取周报 |
| `generate_report()` | 生成周报 |
| `record_report_view()` | 记录阅读行为 |
| `record_report_export()` | 记录导出行为 |

#### `UserService` (`app/services/user_service.py`)

用户行为服务，管理偏好、浏览记录、搜索历史。

| 方法 | 说明 |
|------|------|
| `save_user_categories(session_id, category_ids)` | 保存分类偏好 |
| `save_viewed_books(session_id, isbns)` | 保存浏览记录 |
| `save_search_history(session_id, keyword, count)` | 保存搜索历史 |
| `get_book_metadata(isbn)` | 获取书籍元数据 |
| `save_book_translation(isbn, ...)` | 保存翻译结果 |

### 7.2 翻译服务

#### `ZhipuTranslationService` (`app/services/zhipu_translation_service.py`)

智谱 AI GLM-4.7-Flash 翻译服务。

| 方法 | 说明 |
|------|------|
| `translate(text, source_lang, target_lang, field_type)` | 翻译文本 |
| `batch_translate(texts, ...)` | 批量翻译 |

#### `HybridTranslationService`

混合翻译服务，主用智谱 AI，回退到 `deep-translator`。

#### `FreeTranslationService` (`app/services/free_translation_service.py`)

免费翻译回退方案（MyMemory API）。

### 7.3 缓存服务

#### `CacheService` (`app/services/cache_service.py`)

双层缓存：`MemoryCache`（LRU，线程安全）+ `FileCache`（磁盘持久化）。

| 类 | 说明 |
|----|------|
| `CacheStrategy` | 缓存策略抽象基类 |
| `MemoryCache` | 内存缓存（OrderedDict + LRU） |
| `FileCache` | 文件缓存（JSON 序列化） |
| `CacheService` | 组合缓存服务（内存 → 文件 → 未命中） |

#### `APICacheService` (`app/services/api_cache_service.py`)

数据库层 API 缓存，存储 NYT/Google Books API 响应。

#### `TranslationCacheService` (`app/services/translation_cache_service.py`)

翻译缓存服务，基于 `TranslationCache` ORM 模型。

### 7.4 推荐服务

#### `RecommendationService` (`app/services/recommendation_service.py`)

| 策略 | 说明 |
|------|------|
| `personalized` | 基于用户浏览历史的个性化推荐 |
| `similarity` | 基于奖项相似度的推荐 |
| `popular` | 热门图书推荐 |
| `smart` | 智能混合推荐 |

### 7.5 其他服务

| 服务 | 文件 | 说明 |
|------|------|------|
| `ExportService` | `export_service.py` | PDF/Excel 导出（fpdf2 + openpyxl） |
| `SmartSearchService` | `smart_search_service.py` | 跨数据源智能搜索 |
| `BookLanguagePack` | `book_language_pack.py` | JSON 语言包读写 |
| `BookVerificationService` | `book_verification_service.py` | 书籍数据验证 |
| `AwardCoverSyncService` | `award_cover_sync_service.py` | 获奖图书封面同步 |
| `ImageCacheService` | `api_utils.py` | 封面图片缓存（本地磁盘） |

---

## 八、爬虫子系统

### 8.1 架构

```
BaseCrawler (ABC)
├── GoogleBooksCrawler        # Google Books API 爬虫
├── GoogleBooksPublisherCrawler # Google Books 出版社爬虫
├── OpenLibraryCrawler        # Open Library API 爬虫
├── PenguinRandomHouseCrawler # 企鹅兰登网站爬虫
├── HachetteCrawler           # Hachette 网站爬虫
├── HarperCollinsCrawler      # HarperCollins 网站爬虫
├── MacmillanCrawler          # Macmillan 网站爬虫
├── SimonSchusterCrawler      # Simon & Schuster 网站爬虫
├── RSSCrawler                # RSS Feed 爬虫
└── MixedCrawl4AICrawler      # Crawl4AI 混合爬虫
```

### 8.2 `BaseCrawler` 核心功能

| 功能 | 说明 |
|------|------|
| HTTP 重试 | `requests.Session` + `HTTPAdapter` + `Retry` |
| robots.txt 遵守 | `RobotFileParser` 检查 |
| 分页处理 | 抽象方法 `crawl()` 返回 `Generator[BookInfo]` |
| 错误处理 | 统一日志 + 优雅降级 |

### 8.3 `BookInfo` 数据类

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | str | 书名 |
| `author` | str | 作者 |
| `isbn13` | str\|None | ISBN-13 |
| `cover_url` | str\|None | 封面 URL |
| `publication_date` | date\|None | 出版日期 |
| `category` | str\|None | 分类 |
| `description` | str\|None | 简介 |
| `price` | str\|None | 价格 |
| `page_count` | int\|None | 页数 |
| `buy_links` | list[dict] | 购买链接 |
| `source_url` | str\|None | 来源 URL |

---

## 九、异常体系

```
BookRankException (基类)
├── ExternalAPIError        # 外部 API 调用失败
├── DataNotFoundError       # 数据不存在
├── ServiceUnavailableError # 服务不可用
├── DatabaseError           # 数据库操作失败
├── TranslationError        # 翻译失败
├── APIRateLimitException   # 速率限制
├── CacheMissException      # 缓存未命中
├── APIException            # API 通用异常
├── ValidationException     # 输入验证失败
└── SecurityException       # 安全异常
```

**工具装饰器**：

| 装饰器 | 说明 |
|--------|------|
| `@safe_call(fallback=[])` | 安全调用，异常返回 fallback |
| `@safe_service_call(service_name, operation)` | 安全调用服务方法 |
| `@handle_api_errors` | 路由层统一异常处理 |
| `@api_rate_limit(max_requests, window)` | API 速率限制 |
| `@csrf_protect` | CSRF 保护 |

---

## 十、Pydantic 验证模型 (`app/schemas/validators.py`)

| 模型 | 用途 |
|------|------|
| `BookSearchRequest` | 图书搜索参数验证 |
| `TranslateRequest` | 翻译请求验证 |
| `TranslateBookFieldsRequest` | 书籍字段翻译验证 |
| `PaginationParams` | 分页参数验证 |
| `AwardBooksQuery` | 获奖图书查询验证 |
| `UserPreferencesUpdate` | 用户偏好更新验证 |
| `RecommendationQuery` | 推荐查询验证 |
| `SmartSearchQuery` | 智能搜索验证 |
| `CacheClearRequest` | 缓存清理验证 |
| `TranslationCacheClearRequest` | 翻译缓存清理验证 |

---

## 十一、依赖关系

### 11.1 Python 依赖

| 类别 | 包 | 版本 | 用途 |
|------|-----|------|------|
| 核心 | Flask | 3.1.3 | Web 框架 |
| 核心 | Flask-SQLAlchemy | 3.1.1 | ORM |
| 核心 | Flask-Migrate | 4.0.7 | 数据库迁移 |
| 核心 | Flask-CORS | 4.0.1 | 跨域支持 |
| 核心 | Flask-Babel | 4.0.0 | 国际化 |
| 核心 | Flask-WTF | 1.2.2 | 表单/CSRF |
| 数据库 | SQLAlchemy | 2.0.38 | ORM 引擎 |
| 数据库 | psycopg2-binary | 2.9.10 | PostgreSQL 驱动 |
| 数据库 | alembic | 1.14.0 | 迁移引擎 |
| HTTP | requests | 2.32.3 | HTTP 客户端 |
| 解析 | beautifulsoup4 | 4.13.0 | HTML 解析 |
| AI | zhipuai | 2.1.5 | 智谱 AI SDK |
| AI | deep-translator | 1.11.4 | 翻译回退 |
| 调度 | APScheduler | 3.11.0 | 后台任务调度 |
| 重试 | tenacity | 9.0.0 | 重试机制 |
| 导出 | fpdf2 | 2.7.9 | PDF 生成 |
| 导出 | openpyxl | 3.1.2 | Excel 生成 |
| 图像 | Pillow | 11.1.0 | 图片处理 |
| 渲染 | mistune | 3.2.0 | Markdown 渲染 |
| 部署 | gunicorn | 23.0.0 | WSGI 服务器 |
| 配置 | python-dotenv | 1.0.1 | 环境变量 |
| 开发 | ruff | >=0.11.0 | Lint + Format |
| 开发 | mypy | >=1.15.0 | 类型检查 |
| 开发 | pydantic | >=2.10.0 | 数据验证 |
| 开发 | pytest-cov | >=6.1.0 | 测试覆盖率 |
| 开发 | pre-commit | >=4.2.0 | Git 钩子 |

### 11.2 外部 API 依赖

| API | 限额 | 缓存 TTL | 用途 |
|-----|------|----------|------|
| NYT Books API | 500次/天 | 7天 | 畅销书榜单数据 |
| Google Books API | 1000次/天 | 24小时 | 书籍详情/封面/ISBN |
| Open Library API | 无限制 | 3天 | 书籍元数据补充 |
| Wikidata API | 无限制 | - | 奖项元数据 |
| 智谱 AI GLM-4.7-Flash | 免费额度 | 数据库缓存 | 中英翻译 |

### 11.3 模块间依赖关系

```
routes.main → services.book_service → services.nyt_client
                                      → services.google_books_client
                                      → services.cache_service
                                      → services.book_language_pack
           → services.new_book_service → services.publisher_crawler.*
           → services.award_book_service
           → services.weekly_report_service → services.export_service
           → services.user_service
           → services.recommendation_service

routes.api.books → services.book_service
                 → services.user_service
routes.api.translation → services.zhipu_translation_service
routes.api.cache → services.cache_service
routes.api.awards → services.award_book_service
routes.api.recommendations → services.recommendation_service
```

---

## 十二、项目运行方式

### 12.1 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 NYT_API_KEY, GOOGLE_API_KEY, ZHIPU_API_KEY 等

# 3. 初始化数据库
python scripts/init_database.py

# 4. 构建 CSS
python build.py

# 5. 启动开发服务器
flask run
# 或
python -c "from app import app; app.run(debug=True)"
```

### 12.2 Docker 部署

```bash
docker build -t bookrank .
docker run -p 8000:8000 --env-file .env bookrank
```

### 12.3 Render 部署

- 入口：`run.py` → `gunicorn -c gunicorn.conf.py run:application`
- 数据库：外部 PostgreSQL（`DATABASE_URL` 环境变量）
- 惰性初始化：首次非健康检查请求时初始化数据库
- 自动迁移：启动时检查 Alembic 版本并执行迁移

### 12.4 代码质量检查

```bash
make lint       # Ruff 检查
make format     # Ruff 格式化
make typecheck  # mypy 类型检查
make test       # pytest + 覆盖率
make check      # 全部检查
```

### 12.5 数据库迁移

```bash
flask db migrate -m "描述"   # 生成迁移脚本
flask db upgrade             # 执行迁移
flask db downgrade           # 回滚
```

---

## 十三、安全机制

| 机制 | 实现位置 | 说明 |
|------|----------|------|
| CSP nonce | `app/__init__.py` | 每请求生成唯一 nonce，内联脚本/样式需带 nonce |
| CSRF Token | `CSRFToken` 模型 + `csrf_protect` 装饰器 | 数据库存储，1小时过期 |
| 安全响应头 | `_apply_security_headers()` | X-Frame-Options / X-XSS-Protection / HSTS / Permissions-Policy |
| 速率限制 | `IPRateLimiter` + `api_rate_limit` 装饰器 | IP 级别，可配置窗口 |
| 输入验证 | Pydantic 验证模型 | API 路由层参数校验 |
| SQL 注入防护 | SQLAlchemy ORM | 参数化查询 |
| XSS 防护 | `sanitize_html` Jinja2 过滤器 | 移除危险标签和事件属性 |
| 路径遍历防护 | `cached_image()` 路由 | 正则验证文件名格式 |
| 安全重定向 | `is_safe_redirect_url()` | 防止开放重定向 |
| gzip 压缩 | `_apply_security_headers()` | 自动压缩文本/JSON/SVG 响应 |

---

## 十四、国际化 (i18n)

- 框架：Flask-Babel 4.0
- 支持语言：英语（en）、中文（zh）
- 翻译文件：`translations/{en,zh}/LC_MESSAGES/messages.{po,mo}`
- 前端 i18n：`static/js/book-i18n.js` + `static/js/translations.js`
- 语言包：`static/data/book_language_pack.zh.json`（书名/简介中文翻译）
- 切换方式：`/set-language?lang=zh&next=/` → 写入 Cookie

---

## 十五、CI/CD

### GitHub Actions (`ci.yml`)

| Job | 说明 | 触发条件 |
|-----|------|----------|
| `lint` | Ruff lint + format check | push/PR to main |
| `typecheck` | mypy 类型检查 | push/PR to main |
| `test` | pytest + 覆盖率 >= 60% | push/PR to main |
| `test-root` | 根目录测试（非关键） | push/PR to main |

### 自动数据更新 (`update-books.yml`)

定时执行 `update_books.py` 同步 NYT 榜单数据。

---

## 十六、运维脚本

| 脚本 | 说明 |
|------|------|
| `scripts/init_database.py` | 初始化数据库 |
| `scripts/reset_db.py` | 重置数据库 |
| `scripts/generate_weekly_report.py` | 手动生成周报 |
| `scripts/sync_award_books.py` | 同步获奖图书 |
| `scripts/sync_all_publishers.py` | 同步所有出版社 |
| `scripts/batch_translate.py` | 批量翻译 |
| `scripts/check_api_health.py` | API 健康检查 |
| `scripts/check_cache.py` | 缓存状态检查 |
| `scripts/init_awards_data.py` | 初始化奖项数据 |
| `scripts/migrate_init.py` | 数据库迁移初始化 |
| `scripts/optimize_award_books.py` | 优化获奖图书数据 |

---

## 十七、测试

- 框架：pytest + pytest-cov
- 配置：`pytest.ini`
- 目录：`tests/`
- 覆盖率要求：>= 60%（目标 80%）

| 测试文件 | 覆盖模块 |
|----------|----------|
| `test_book_service.py` | BookService |
| `test_new_book_service.py` | NewBookService |
| `test_translation_service.py` | 翻译服务 |
| `test_api_routes.py` | API 路由 |
| `test_api_translation.py` | 翻译 API |
| `test_api_awards.py` | 奖项 API |
| `test_api_cache_service.py` | 缓存服务 |
| `test_cache_service.py` | CacheService |
| `test_publisher_crawler.py` | 爬虫 |
| `test_weekly_report.py` | 周报 |
| `test_user_service.py` | UserService |
| `test_models.py` | 数据模型 |
| `test_routes.py` | 页面路由 |
| `test_pydantic_validators.py` | Pydantic 验证 |
| `test_error_tracker.py` | 错误追踪 |
| `security_test.py` | 安全测试 |
| `performance_test.py` | 性能测试 |

---

## 十八、关键设计决策

| 决策 | 原因 |
|------|------|
| 应用工厂模式 | 支持多环境配置，避免循环导入 |
| Service 层隔离 | 路由层不直接操作 `db.session`，通过 Service 层统一管理 |
| 双层缓存（内存+文件） | Render 免费版无 Redis，内存缓存 + 文件持久化 |
| APScheduler 替代 Celery | 无需 Redis/RabbitMQ，适合免费版部署 |
| 数据库存储 CSRF Token | 多实例部署时内存 dict 不可共享 |
| 惰性数据库初始化 | 减少 Render 冷启动时间 |
| 智谱 AI + deep-translator 双回退 | 保证翻译可用性 |
| 语言包 JSON 文件 | 前端可直接加载，避免每次请求翻译 |
| CSP nonce | 防止 XSS 攻击，比 unsafe-inline 更安全 |
| Book dataclass 独立于 ORM | 业务数据对象与持久化模型解耦 |
