# BookRank

纽约时报畅销书排行榜应用，追踪国际大型出版社最新出版物。

## 功能特性

- 📚 **畅销书榜单**：展示纽约时报各类别畅销书
- 🏆 **获奖书单**：收集和展示各类图书奖项
- 🆕 **新书速递**：追踪国际大型出版社最新出版物
- 📊 **多维度筛选**：支持按出版社、分类、时间等筛选
- 🌐 **响应式设计**：适配桌面端和移动端
- 🔍 **智能搜索**：快速查找书籍
- 📱 **独立详情页**：优化的书籍详情展示

## 技术栈

- **后端**：Flask 2.3.3 (Python 3.10+)
- **数据库**：Flask-SQLAlchemy (SQLite/PostgreSQL)
- **前端**：Jinja2 + 原生JS (ES2020+)
- **部署**：Render + Gunicorn 21.2.0

## 快速开始

### 环境要求

- Python 3.10 或更高版本
- pip 包管理器

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/gongyijie85/bookrank.git
   cd bookrank
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   复制 `.env.example` 文件为 `.env`，并填写相关配置：
   ```
   SECRET_KEY=your-secret-key
   NYT_API_KEY=your-nyt-api-key
   GOOGLE_API_KEY=your-google-api-key
   ZHIPU_API_KEY=your-zhipu-api-key
   DATABASE_URL=your-database-url
   ```

4. **初始化数据库**
   ```bash
   python run.py
   ```

5. **启动开发服务器**
   ```bash
   python run.py
   ```

   应用将在 `http://localhost:8000` 运行。

## 项目结构

```
bookrank/
├── app/
│   ├── initialization/      # 初始化数据
│   ├── models/             # 数据模型
│   ├── routes/             # 路由
│   ├── services/           # 业务逻辑
│   ├── utils/              # 工具函数
│   ├── __init__.py         # 应用初始化
│   └── config.py           # 配置
├── static/                 # 静态文件
│   ├── css/                # CSS样式
│   ├── js/                 # JavaScript
│   └── data/               # 数据文件
├── templates/              # 模板文件
├── tests/                  # 测试文件
├── scripts/                # 脚本文件
├── migrations/             # 数据库迁移
├── .env.example            # 环境变量示例
├── requirements.txt        # 依赖列表
├── run.py                  # 启动文件
└── Procfile                # Render 部署配置
```

## API 限制

- **NYT Books API**：500次/天
- **Google Books API**：1000次/天

## 部署

项目已配置为在 Render 平台部署，使用 Gunicorn 作为 WSGI 服务器。

## 开发指南

### 代码规范

- **Python**：遵循 PEP 8 规范
- **JavaScript**：使用现代语法（ES2020+）
- **Git 提交**：使用 Conventional Commits 规范

### 测试

- 测试目录：`tests/`
- 配置文件：`pytest.ini`
- 运行测试：`pytest`

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
