# BookRank 新成员上手指南

本指南帮助新成员在本地快速搭建 BookRank 开发环境，并了解项目结构与工作流。

---

## 一、前置要求

- **Python**：3.13 或更高版本
- **pip**：最新版（建议 `python -m pip install --upgrade pip`）
- **Git**：2.50 或更高版本
- **外部 API 密钥**（开发必需）：
  - [NYT Books API](https://developer.nytimes.com)
  - [Google Books API](https://console.cloud.google.com)
  - [智谱 AI](https://open.bigmodel.cn)

---

## 二、本地运行步骤

### 1. 克隆仓库

```bash
git clone https://github.com/gongyijie85/bookrank.git
cd bookrank
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

复制示例文件并填写实际值：

```bash
cp .env.example .env
```

至少填写以下变量：

```env
SECRET_KEY=your-secret-key
ADMIN_SECRET=your-admin-secret
NYT_API_KEY=your-nyt-api-key
GOOGLE_API_KEY=your-google-api-key
ZHIPU_API_KEY=your-zhipu-api-key
DATABASE_URL=sqlite:///bestsellers.db
FLASK_ENV=development
```

### 5. 构建静态资源

```bash
python build.py
```

### 6. 初始化并启动应用

```bash
python run.py
```

应用默认运行在 `http://localhost:5000`。

---

## 三、项目结构速览

```
BookRank3/
├── app/                    # 应用核心
│   ├── __init__.py         # 应用工厂
│   ├── config.py           # 配置管理
│   ├── setup.py            # 服务初始化 + 后台任务
│   ├── models/             # SQLAlchemy 模型 + Book dataclass
│   ├── routes/             # 路由层（禁止直接操作 db.session）
│   ├── services/           # 业务服务层
│   ├── schemas/            # Pydantic 验证模型
│   ├── utils/              # 工具函数
│   └── tasks/              # 后台任务
├── tests/                  # pytest 测试
├── migrations/             # Alembic 数据库迁移
├── static/                 # CSS/JS/图片/数据
├── templates/              # Jinja2 模板
├── docs/                   # 文档与审计报告
├── requirements.txt        # 开发依赖
├── requirements-prod.txt   # 生产依赖
├── run.py                  # 启动入口
└── Makefile                # 快捷命令
```

---

## 四、常用命令

```bash
# 代码检查
make lint

# 代码格式化
make format

# 类型检查
make typecheck

# 运行测试（含覆盖率）
make test

# 一键执行 lint + typecheck + test
make check

# 单独运行测试
pytest tests/ -v
```

---

## 五、开发规范

### 5.1 Python

- 强制类型注解，使用 `str | None` 替代 `Optional[str]`。
- 导入顺序：标准库 → 第三方库 → 内部模块。
- 捕获具体异常，使用异常链（`raise ... from e`）。
- 路由层禁止直接操作 `db.session`，必须通过 Service 层。
- 新 API 端点需在 `app/schemas/validators.py` 定义 Pydantic 验证模型。

### 5.2 JavaScript

- 使用 ES2020+ 语法（`??`、`?.`、`const`/`let`）。
- 文件顶部添加 `'use strict'`。
- 对用户输入做 XSS 防护，避免直接 `innerHTML` 插入不可信内容。

### 5.3 Git 提交

- 使用 Conventional Commits：`<type>(<scope>): <subject>`
- 常见类型：`feat`、`fix`、`docs`、`style`、`refactor`、`perf`、`test`、`chore`
- 示例：`feat(api): add book search endpoint`

---

## 六、提交前必做

每次提交前请确保：

1. `make lint` 通过（Ruff 无报错）。
2. `make format` 已执行（Ruff format 无变更）。
3. `make typecheck` 通过（mypy 无报错）。
4. `pytest tests/` 全量通过，覆盖率 ≥70%。

CI 已配置相同门禁，未通过将无法合并到 `main`。

---

## 七、调试与排查

- **数据库迁移**：使用 `flask db migrate` / `flask db upgrade`，生产环境由应用启动时惰性迁移。
- **后台任务**：周报生成等任务在 `app/setup.py` 中注册，失败告警依赖 `ALERT_WEBHOOK_URL`。
- **错误追踪**：生产环境配置 `SENTRY_DSN` 后，异常会自动上报 Sentry。
- **性能**：榜单页/搜索等路径已做 N+1 优化，新增查询请使用 `joinedload` / `selectinload`。

---

## 八、相关文档

- [README.md](../README.md)：项目概览与快速开始
- [API_DOCUMENTATION.md](../API_DOCUMENTATION.md)：公开 API 文档
- [CHANGELOG.md](../CHANGELOG.md)：版本变更记录
- [VERSION.md](../VERSION.md)：当前版本亮点
- [docs/audits/](./audits/)：各维度审计报告
- [docs/runbooks/](./runbooks/)：运维操作手册

---

## 九、获取帮助

- 技术问题：在仓库提交 Issue
- 紧急生产故障：先按 [`deployment-rollback.md`](./runbooks/deployment-rollback.md) 回滚，再定位根因
