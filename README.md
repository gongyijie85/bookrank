# BookRank

[![Test & Coverage](https://github.com/gongyijie85/bookrank/actions/workflows/test.yml/badge.svg)](https://github.com/gongyijie85/bookrank/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/gongyijie85/bookrank/branch/main/graph/badge.svg)](https://codecov.io/gh/gongyijie85/bookrank)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Flask 3.1](https://img.shields.io/badge/flask-3.1-black.svg)](https://flask.palletsprojects.com/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

纽约时报畅销书排行榜应用，追踪国际大型出版社最新出版物，展示各类图书奖项。

## 项目简介

BookRank 是一个聚合全球优质图书信息的平台，旨在为读者提供一站式的图书发现体验。通过整合纽约时报畅销书榜单和国际文学奖项，结合智能翻译和实时更新，为用户打造一个全面、便捷的图书信息中心。

## 功能特性

- 📚 **畅销书榜单**：展示纽约时报各类别畅销书，支持多维度排序和筛选
- 🏆 **获奖书单**：收集和展示8大国际图书奖项，包含详细的获奖信息
- 🆕 **新书速递**：追踪国际大型出版社最新出版物，支持按出版社筛选
- 📊 **多维度筛选**：支持按出版社、分类、时间等多维度筛选
- 🌐 **双端适配**：桌面端 + 移动端独立版本，同一 URL 根据 User-Agent 自动切换移动版模板。移动端核心 8 页面（首页、书籍详情、奖项榜单、获奖详情、关于、错误页、周报列表、周报详情）信息完整度已对齐桌面端，含 Tab 切换、元信息网格、购买链接、收藏/分享、30 秒轮询、搜索过滤、SEO 元数据（canonical + Open Graph + JSON-LD）
- 🔍 **智能搜索**：快速查找书籍，支持书名、作者等多字段搜索
- 📱 **优化详情页**：统一的左右布局详情页，左侧显示封面和购买链接，右侧显示图书信息
- 🎨 **统一卡片设计**：全局统一的图书卡片比例（2/3），视觉效果一致
- 🌍 **智能翻译**：提供书名、简介的中文翻译，降低语言门槛
- 🚀 **实时更新**：自动同步最新榜单数据，确保信息时效性；周报自愈机制（三重保险）避免漏跑
- 🔓 **开放API**：提供公开API，支持第三方系统集成

## 技术栈

- **后端**：Flask 3.1.3 (Python 3.13+)
- **数据库**：Flask-SQLAlchemy 2.0 (PostgreSQL / SQLite)
- **前端**：Jinja2 + 原生JS (ES2020+)
- **部署**：Render + Gunicorn 23.0
- **API集成**：NYT Books API、Google Books API、Open Library API、Wikidata SPARQL
- **翻译服务**：智谱AI GLM API（主）、deep-translator（备选回退）
- **代码质量**：Ruff（linting+formatting）、mypy（类型检查）、Pydantic（数据验证）、pytest-cov
- **任务调度**：APScheduler（内存队列）

## 快速开始

### 环境要求

- Python 3.13 或更高版本
- pip 包管理器

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/gongyijie85/bookrank.git
   cd bookrank
   ```

2. **创建虚拟环境**
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   复制 `.env.example` 文件为 `.env`，并填写相关配置：
   ```
   SECRET_KEY=your-secret-key
   ADMIN_SECRET=your-admin-secret          # 必需（v0.9.61+，所有 admin 端点统一使用）
   NYT_API_KEY=your-nyt-api-key
   GOOGLE_API_KEY=your-google-api-key
   ZHIPU_API_KEY=your-zhipu-api-key
   DATABASE_URL=your-database-url
   ```
   > **v0.9.61 破坏性变更**：`ADMIN_TOKEN` 环境变量已废弃，请改用 `ADMIN_SECRET`（与项目其他 27 个 admin 端点统一），详见 [CHANGELOG.md](./CHANGELOG.md)。

5. **初始化数据库**
   ```bash
   python run.py
   ```

6. **启动开发服务器**
   ```bash
   python run.py
   ```

   应用将在 `http://localhost:5000` 运行。

## 项目结构

```
BookRank3/
├── app/                          # 应用核心目录
│   ├── __init__.py               # 应用工厂函数
│   ├── config.py                 # 配置管理
│   ├── setup.py                  # 服务初始化 + 后台任务
│   ├── data/                     # 静态数据（出版社列表等）
│   ├── initialization/           # 初始化模块
│   │   ├── awards.py             # 奖项初始化
│   │   └── sample_books.py       # 示例数据初始化
│   ├── models/                   # 数据模型层
│   │   ├── database.py           # 数据库连接
│   │   ├── schemas.py            # SQLAlchemy 模型定义
│   │   ├── book.py               # Book dataclass
│   │   └── new_book.py           # 新书模型
│   ├── routes/                   # 路由控制层
│   │   ├── main.py               # 页面路由
│   │   ├── admin.py              # 管理后台 API
│   │   ├── new_books.py          # 新书速递 API
│   │   ├── health.py             # 健康检查
│   │   ├── public_api.py         # 公开 API
│   │   ├── analytics_bp.py       # 数据分析
│   │   └── api/                  # 内部 API（拆分子模块）
│   │       ├── books.py          # 图书 API
│   │       ├── translation.py    # 翻译 API
│   │       ├── cache.py          # 缓存管理 API
│   │       ├── awards.py         # 奖项 API
│   │       └── recommendations.py # 推荐 API
│   ├── schemas/                  # Pydantic 验证层
│   │   └── validators.py         # 请求验证模型
│   ├── services/                 # 业务服务层
│   │   ├── api_client.py         # NYT/Google API 客户端
│   │   ├── book_service.py       # 图书服务
│   │   ├── new_book_service.py   # 新书速递服务（重导出）
│   │   ├── new_book/             # 新书速递子模块（拆分）
│   │   │   ├── publisher_manager.py  # 出版社管理
│   │   │   ├── sync_engine.py        # 数据同步引擎
│   │   │   ├── translation_pipeline.py # 翻译管道
│   │   │   └── query_service.py      # 查询服务
│   │   ├── book_detail_service.py # 书籍详情服务
│   │   ├── cache_service.py      # 缓存服务
│   │   ├── translation_cache_service.py # 翻译缓存
│   │   ├── zhipu_translation_service.py # 智谱AI翻译
│   │   ├── weekly_report_service.py # 周报服务
│   │   ├── publisher_crawler/    # 出版社爬虫模块
│   │   └── ...
│   ├── tasks/                    # 后台任务
│   │   └── weekly_report_task.py # 周报任务
│   └── utils/                    # 工具模块
│       ├── exceptions.py         # 自定义异常
│       ├── rate_limiter.py       # 限流器
│       ├── error_handler.py      # 错误分类处理
│       ├── error_tracker.py      # 内存错误追踪
│       ├── service_helpers.py    # 服务注入注册
│       ├── book_filters.py       # 图书过滤排序
│       ├── date_helpers.py       # 日期工具函数
│       └── security.py           # 安全工具
├── static/                       # 静态资源
│   ├── css/                      # CSS样式
│   ├── js/                       # JavaScript
│   ├── data/                     # 数据文件
│   └── fonts/                    # 字体文件
├── templates/                    # 模板文件
│   ├── base.html                 # 基础模板
│   ├── _macros.html              # Jinja2 宏组件
│   ├── index.html                # 首页（畅销书榜）
│   ├── awards.html               # 获奖书单
│   ├── new_books.html            # 新书速递
│   ├── publishers.html           # 出版社导航
│   └── *detail.html              # 各类详情页
├── tests/                        # 测试文件
├── scripts/                      # 运维脚本工具
├── migrations/                   # 数据库迁移
├── requirements.txt              # 完整依赖（含开发工具）
├── requirements-prod.txt         # 生产环境精简依赖
├── run.py                        # Render 部署启动入口
├── build.py                      # CSS 构建脚本
└── Procfile                      # Render 部署配置
```

## API 限制

- **NYT Books API**：500次/天
- **Google Books API**：1000次/天
- **智谱AI API**：根据具体套餐

## 部署

### Render 部署（推荐）

1. 在 Render 平台创建新的 Web Service
2. 连接 GitHub 仓库
3. 配置服务参数：
   - Name: bookrank
   - Region: Singapore (离中国最近)
   - Branch: main
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. 添加环境变量（参考 `.env.example`）
5. 点击 "Create Web Service"
6. 等待构建完成，获取访问URL

### Docker 部署（可选）

```bash
# 构建镜像
docker build -t bookrank .

# 运行容器
docker run -p 5000:5000 --env-file .env bookrank
```

## 开发指南

### 代码规范

- **Python**：遵循 PEP 8 规范，使用类型注解
- **JavaScript**：使用现代语法（ES2020+），支持 `??`、`?.` 操作符
- **CSS**：使用 CSS 变量，保持响应式设计
- **Git 提交**：使用 Conventional Commits 规范

### 测试

- 测试目录：`tests/`
- 配置文件：`pytest.ini`
- 运行测试：`pytest`

### 数据更新

- 自动更新：通过 GitHub Actions 定期更新数据
- 手动更新：运行 `python update_books.py` 手动更新数据

## 公开API

### API 端点结构

```
/api/public
├── /bestsellers              # 所有分类畅销书
├── /bestsellers/{category}   # 指定分类畅销书
├── /bestsellers/search       # 搜索畅销书
├── /awards                   # 所有奖项列表
├── /awards/{award_name}      # 指定奖项获奖图书
├── /awards/{award_name}/{year} # 指定年份获奖图书
├── /book/{isbn}              # 图书详情
├── /new-books                # 新书列表（支持分页）
├── /new-books/{publisher}    # 指定出版社新书
└── /recommendations          # 智能推荐
```

### 用户 API

```
/api
├── /favorites                # 获取收藏列表 (GET)
├── /favorites                # 添加收藏 (POST)
├── /favorites/{isbn}         # 取消收藏 (DELETE)
└── /favorites/check/{isbn}   # 检查收藏状态 (GET)
```

## 最近更新

- v0.9.77 - 移动端 UI v2.0 视觉优化：按设计师 v2.0.0 设计稿改版现有移动端页面；底部 Tab Bar 改为实心/描边 SVG；首页加顶部导航栏+分类 Tab 指示条；书籍详情改单列元信息+返回按钮；获奖详情统一布局+奖项徽章；周报列表加 Wxx 周数指示器；周报详情 Hero 统计 4 列+推荐语气泡；搜索页/个人中心空状态加图标；按钮/分页统一 44px 触控高度；保持原生 CSS/SVG，不引入 Tailwind/Lucide；20 个移动端测试全部通过
- v0.9.76 - bookrank-draft 设计稿：新增周报列表页（weekly-report-list.html）和周报详情页（weekly-report.html）设计稿，含 Hero 渐变区、4 列统计、上升/下降箭头、推荐书籍语气泡、底部 Tab Bar 规范
- v0.9.75 - 移动端精简：移除筛选（年份/日期/搜索框）、分享、收藏功能；详情页移除 Tab 切换/购买链接/英文原标题/标签行，保留 ISBN+出版社+内容简介；mobile.js 从 215 行精简至 75 行；mobile.css 移除约 400 行冗余样式
- v0.9.74 - 数据库迁移至 Supabase Postgres + 文案统一补丁：`config.py` 新增 `_ensure_supabase_sslmode` 自动补 SSL；`Procfile` 移除 `flask db upgrade` 改为应用内惰性迁移；`render.yaml` 移除内置 Postgres 服务，`DATABASE_URL` 改为手动配置 Supabase Session Pooler；新增 `docs/supabase-migration.md` 迁移手册 + `scripts/init_external_postgres.py` 空库初始化脚本；CSV/注释 "上榜周数" → "累计上榜周数"（v0.9.69 补丁）
- v0.9.73 - 移动端内容完善 v2：修复 3 个跳转断裂（`/award-book/<id>`、`/about`、错误页改用 `render_adaptive`）；新增 3 个移动端模板（error、about、award_book_detail）；周报详情补"排名上升最快"+"持续上榜最久"+PDF/Excel 导出；周报列表增加搜索框；base.html 加 canonical + SearchAction JSON-LD；awards 卡片加 ISBN 标签；新增 6 个测试用例
- v0.9.72 - 移动端核心 4 页内容对齐桌面端：新增简化版周报详情页（无 Chart.js，含 Hero 数字卡 + Top 5 变化 + 本周新书 + 编辑推荐 + Article JSON-LD）；book_detail 新增排名徽章+双语标题+Tab 切换+2 列元信息网格+购买链接横滑+Book JSON-LD；awards 新增搜索框+描述预览+收藏按钮+分类标签，内联样式迁移到 mobile.css；weekly_reports 新增介绍卡+日期筛选+亮点徽章+分享按钮+30 秒轮询；修复 index.html 元信息行 Jinja2 语法 bug（namespace 方式）；全量 2115 passed / 4 xfailed，ruff + mypy 通过
- v0.9.71 - 移动端搜索与周报入口补齐：新增 `/search` 路由（移动端独立搜索页，桌面端重定向首页）；`/reports/weekly` 与 `/reports/weekly/<date>` 改用 `render_adaptive()`；路由统一传入 `active_tab` 底部 Tab 高亮
- v0.9.70 - 移动端独立版本 MVP：新增 UA 自动切换模板机制（`device_detect.py` + `template_resolver.py`），移动端独立 base/index/book_detail/awards/profile/search 模板，独立 mobile.css + mobile.js，11 个新文件 + 3 个修改文件
- v0.9.68 - 新书速递模块修复：修复统计栏 `{count}` 占位符未替换问题（移除 `data-i18n` 属性，直接使用 Jinja2 翻译）；统一分类数据中英文（添加 `CATEGORY_EN_TO_ZH` 映射表，`sanitize_category` 函数应用映射）；新增 `/migrate-categories` 管理接口批量更新历史数据；修复 3 个测试文件适配分类映射逻辑；ruff check / mypy / pytest 全部通过
- v0.9.67 - 安全审计：CSRF 全覆盖 + 依赖漏洞修复 + MD5 安全加固：为 `favorites` / `awards` / `books` 模块的 8 个 POST/DELETE 端点添加 `@csrf_protect` 装饰器；mistune 3.2.0 → 3.2.1（修复 2 个 XSS 漏洞 CVE-2026-44897）；添加 PyJWT>=2.13.0（修复 6 个漏洞，包括 crit 验证绕过、JWKS SSRF 等）；MD5 哈希添加 `usedforsecurity=False` 参数（bandit B324 修复）；确认 admin_auth 中间件、安全头（CSP/HSTS/X-Frame-Options）、密钥轮换 SOP 均已完善；ruff check / mypy / pytest 全部通过（48/48 测试）
- v0.9.64 - 多 worker 安全锁 + CSV 文件名国际化 + var→const/let：`app/routes/new_books.py` 使用 `current_app.extensions` 存储同步锁和时间戳（替代全局变量），确保跨 worker 同步操作安全；CSV 导出使用 `filename*=UTF-8''` 格式（RFC 5987），同时提供 ASCII 备用名，修复中文文件名乱码问题；`templates/new_books.html` 将 `var card` / `var bookCard` 替换为 `const`，符合 ES6 规范；`static/js/base.js` 的 `initImageErrorHandler` 已实现基于 `data-fallback` 属性的统一图片错误监听；确认详情页 i18n 通用化（M7/M8）在 v0.9.62 已完成；`tests/test_new_books_routes.py` 适配多 worker 安全锁，18/18 测试通过
- v0.9.63 - 新书速递 i18n 审查 follow-up：基于 2026-06-12 审查报告（19 个问题 C1-C4 / M1-M9 / L1-L6），完成 Medium 优先级修复 — **M1 Pydantic 验证**（`NewBookListQuery` / `NewBookSearchQuery` / `NewBookExportQuery` / `NewBookSyncQuery` 4 个新模型 + 通用 `parse_query_args()` 工具，4 个端点错误码 400 → 422；`tests/test_pydantic_validators.py` 48/48 PASSED） + **M2 `applyPublisherLanguage` 通用化**（`book-i18n.js` 新增通用方法，`book-i18n.min.js` 压缩 11,244→7,719 字节 / 31.4%） + **M3 `_macros.html` 出版社 fallback 简化**（`name_en if _l == 'en' else name`，'未知' 改用 `{{ _('未知') }}`） + **M4 Playwright E2E 验证脚本**（`scripts/_verify_new_books_i18n.py` 240 行 4 阶段断言 zh/en 切换无 CJK 残留） + **M9 CSS 颜色变量化收尾**（`static/css/new-books.css` 17 个 `:root` 变量覆盖所有新书页色板，32 处硬编码改 `var(--xxx, fallback)`，4 处自引用 bug + 1 处嵌套 bug 修复；当前 `:root` 与默认色一致，未来可被 `[data-theme="dark"]` 覆盖） ；harness 教训：`replace_all` 必须用带缩进的精确字符串做唯一匹配，并行 Edit 偶尔有竞态优先串行
- v0.9.62 - 详情页 i18n 补全 + 列表页切语言卡片不更新修复（v0.9.58 review follow-up）：4 个根因 — 详情页 `new_book_detail.html` 完全没参与 v0.9.58 修复（标题/作者/出版社/ISBN/简介在英文模式仍中文） + `applyNewBooksLanguage` 末尾是 noop 死代码（已加载的卡片切语言不更新） + `renderBooks` 的 `if (currentLanguage === 'zh')` 守卫导致英文首屏切语言失效 + `publisher-filter` 第一个 option 缺 `data-pub-name-*`；修复：`new_book_detail.html` 新增 `applyNewBookDetailLanguage(lang)` JS（5 类元素：title/author/publisher/desc/isbn 标签）+ 5 处 data-* 属性 / "暂无简介" 改用 `{{ _() }}` 翻译；`new_books.html` 修 C2/C3/L4/L6/C4 五处；en.po ISBN msgstr 补全；translations.js / min.js 各 +3 键（150→153，min.js 12,241→12,482 字节同步）；`tests/test_new_books_i18n.py` +11 个用例（**29/29 PASSED**，完整套件 2097 passed，覆盖率 81.56%）
- v0.9.61 - 统一 admin 鉴权协议：`app/routes/api/awards.py` 2 个管理端点（`fix-award-book-titles`、`fix-award-book-titles-by-ids`）从 `X-Admin-Token + ADMIN_TOKEN` 协议改用项目其它 27 个 admin 端点的 `X-Admin-Secret + ADMIN_SECRET + @admin_required` 装饰器协议（统一失败计数 / IP 封禁 / SystemConfig 持久化）；删除 14 行旧协议手工鉴权代码，未配置 secret 行为由 403 改为 503（与 `admin.py` 一致）；**破坏性变更**：Render 控制台需删除 `ADMIN_TOKEN` 环境变量并确认 `ADMIN_SECRET` 已存在，自动化脚本 / curl 改用 `X-Admin-Secret` 头；新增 `tests/test_api_awards.py::TestAdminAwardFixEndpoints` 6 个测试（覆盖 403/400/405/429/200）

- v0.9.60 - 翻译 API fallback ISBN 脏数据修复 + CI format 修复 + min.js 同步：`/awards` 页面"打开正常 → 过一会儿变 ISBN"的根因 — `POST /api/translate/book/<isbn>` 端点的 AwardBook fallback 分支用 `award_book.title` 原始字段作翻译源，v0.9.57 修复前存进数据库的脏 `title`（ISBN 字符串）被原样送进翻译模型，模型返回后被前端 `translateSingleBook` 写回 `titleEl.textContent`；修复：fallback 改用 `award_book.display_title`（已内置 ISBN 退化）；CI 修复：`ruff format` 应用到 `app/models/new_book.py` 恢复 `ruff format --check` 通过；v0.9.58 漏同步的 `translations.min.js` 重新生成（`data-i18n-params-*` 占位符实际生效）；新增 `tests/test_new_books_i18n.py::test_min_matches_build_output` 字节级防护（**2098 passed**, 覆盖率 82.05%）；**部署后需手动跑 admin 端点清理残留脏 `title_zh`**（详见 [VERSION.md](./VERSION.md)）
- v0.9.59 - 切换语言时获奖页面书名不更新修复：`book-i18n.js` 的 `applyLanguage` 用 `card.querySelector(TITLE_SELECTORS)` 在获奖页面失效（h3 自身带 `data-isbn` 是 card，`h3.querySelector` 返回 null）；新增 `_updateTitleInCard(card, text)` 辅助函数，优先 `card.matches(TITLE_SELECTORS)` 直接更新 card 自身（h3-as-card 场景），否则退化到 `card.querySelector`（兼容详情页/首页嵌套结构）；同步 `book-i18n.min.js`
- v0.9.58 - 新书推介页 i18n 完整修复：英文模式下"中英混杂"现象（出版社名阿歇特/Hachette、过滤项最近7天/Last 7 days、统计当前结果/Results、placeholder、按钮文案）三根因叠加 — en.po 缺失 ~13 msgid（Flask-Babel 回退中文）+ 模板硬编码 `{{ pub.name }}` 中文 + JS `applyPageTranslation` 不支持占位符 / option 文本不刷新；修复：po +13 键补全、translations.js / min.js 各 +39 键（111→150）、`NewBook.to_dict()` 新增 `publisher_name_en` 字段、模板/卡片/侧边栏/option 加 `data-pub-name-*` 属性、新增 `applyNewBooksLanguage(lang)` JS 函数；新增 `tests/test_new_books_i18n.py` 18 个测试（18/18 PASSED）
- v0.9.57 - 获奖书单列表页书名 ISBN 修复：`AwardBook.display_title` 属性避开 ISBN-as-title，路由 `_load_awards_data` 改用安全字段
- v0.9.56 - 修复首页 card 翻译键字符串泄露：`translations.min.js` 缺失 v0.9.55 新增的 16 个 card_* 键，`t()` 兜底返回 key 字面量导致卡片显示 `card_rank_aria` / `card_weeks_suffix` / `card_isbn_prefix`；min.js 补回 16 键后 zh/en 各 111 键对齐（手工维护 min.js 必须随源码同步，**已记入 harness 教训**）
- v0.9.55 - i18n 性能与一致性：8 分类预拉取彻底移除（按需加载 + 内存热层），首页 0 API / 二次切换 0 API；首次切换分类显示 8 个 skeleton 骨架卡；抽出 `static/js/categories.js` 共享 CATEGORIES 模块；详情页分类字段参与 CATEGORY_LABELS 映射（带短路保护）；新增 3 个 Playwright E2E 测试脚本 + `docs/I18N_TEST.md`
- v0.9.54 - 语言切换时图书动态内容即时重渲染：`rerenderCurrentBooks(lang)` 重新调用 `updateBooksOnPage()`，所有文案走 `t()`；`formatLocalTime` 时间本地化（zh ISO，en "Jun 3, 2026 8:08 AM"）；模板 SSR 嵌入 `initial-books-data` 作为回退数据源
- v0.9.53 - 夜晚模式图书分类标签对比度修复：删除 `index.css` 中 `.card-category-tag` 的 `color: var(--white)` 覆盖（夜晚模式变成 `#1e293b`），统一由 `components.css` 用 `var(--badge-bg)` / `var(--badge-text)` 主题变量管理
- v0.9.52 - 网格视图封面完整显示（v0.9.51 修复真正落地）：3:2 容器内嵌 2:3 `.cover-frame` 画框，`object-fit: contain` 完整显示，删除 `index.css` 中冲突的 v0.9.51 之前覆盖规则
- v0.9.51 - 网格视图图书卡片封面留白：`.card-image` 新增 `padding: 14px` + flex 居中，`object-fit: cover` → `contain` 整本封面完整显示，移除 hover 放大（scale 1.05 / 桌面端 1.08），下半段文字不再被贴近
- v0.9.50 - 修复 v0.9.49 推送后 CI 失败：ruff format 合并 2 文件多行调用 + 3 个 TestWeeklyReports 测试补充 `get_or_trigger_current_week_report` mock（2073 passed, 覆盖率 81.54%）
- v0.9.49 - 排行榜 list 视图 NYT 风格化：移除行内「收藏/分享/购买」按钮，对齐 NYT 视觉密度（功能改由详情页承载）
- v0.9.32 - 质量收官：测试覆盖率 61%→84.12%，新增 14 个测试文件（2034 passed），TODO 清理
- v0.9.31 - 管理增强：爬虫管理 API、系统监控、数据备份 API
- v0.9.30 - 功能补全：收藏持久化、新书/推荐公共API、搜索扩展（AwardBook+NewBook）
- v0.9.29 - 前端瘦身：index.html CSS/JS 提取，模板从 2703 行减至 580 行
- v0.9.28 - 地基修复：Python 3.13 统一、CI 门禁修复
- v0.9.24 - 错误日志分类记录迁移（22文件全量覆盖）
- v0.9.22 - 全面代码质量优化：Ruff/mypy 清零，测试覆盖率 47%→60%
- v0.9.11 - 分类切换崩溃修复 & Cookie Domain 修复
- v0.9.10 - 语言切换完整修复
- v0.9.9 - 分类切换报错修复与语言同步优化
- v0.9.8 - 语言切换按钮修复：切换中文版后导航栏按钮状态同步，消除竞态条件
- v0.9.7 - 路由层 db.session 治理 & 前端 XSS 加固：消除路由层直接 DB 操作，Service 层统一管理翻译持久化，前端 XSS 防护完善
- v0.9.6 - 配置项集中管理 & 图表颜色规范化：6 个配置项迁移到 config.py，图表颜色统一由 chartColors 对象管理
- v0.9.5 - API 路由统一错误处理装饰器：31 个函数引入 `@handle_api_errors`，错误返回格式统一
- v0.9.4 - 前端 XSS 漏洞修复与安全加固：购买链接转义、SVG 注入防护、数据表格转义
- v0.9.3 - SECRET_KEY 管理与 CORS 配置修复：开发固定密钥、生产环境变量强制校验
- v0.9.2 - 缓存高频写入优化：读路径移除数据库写入
- v0.9.1 - 数据库迁移系统修复：8 个缺失表迁移
- v0.9.0 - 全面代码审计：发现 120+ 问题，输出修复优先级矩阵
- v0.8.2 - Flask-Babel 4.0 兼容性修复：`get_locale()` 模板未定义问题
- v0.8.1 - 修复分类标签语言翻转bug、服务端渲染语言适配（index/macros/awards）
- v0.8.0 - 生产依赖精简、错误监控、CSRF全量覆盖、代码整洁、性能优化
- v0.7.0 - Render部署优化：连接池瘦身、单worker模式、APScheduler内存队列
- v0.6.0 - 代码架构升级：API路由拆分、周报模块标准化、代码质量工具链
- v0.5.0 - 新书速递优化：单例模式、N+1查询修复、AJAX筛选、批量提交
- v0.4.0 - 周报系统优化：封面HTML统一、摘要统计修复
- ✅ 修复新书分类数据污染，添加分类校验过滤营销文案
- ✅ 修复周报书名重复书名号问题

## 未来规划

### 短期规划（Q1 2026）
- 管理后台
- 用户收藏系统
- 批量翻译优化
- 错误监控告警

### 中期规划（Q2-Q3 2026）
- 图书推荐算法
- 用户评论系统
- 数据分析面板
- API v2版本

### 长期规划（2027）
- 移动端App
- AI图书助手
- 社区功能
- 多语言支持

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题或建议，请通过 GitHub Issues 联系我们。

## 相关链接

- **生产环境**：https://bookrank-ckml.onrender.com
- **GitHub仓库**：https://github.com/gongyijie85/bookrank
- **API文档**：API_DOCUMENTATION.md
- **项目说明文档**：docs/项目说明文档.md
