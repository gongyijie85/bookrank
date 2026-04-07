# BookRank

纽约时报畅销书排行榜应用，追踪国际大型出版社最新出版物，展示各类图书奖项。

## 功能特性

- 📚 **畅销书榜单**：展示纽约时报各类别畅销书，支持多维度排序和筛选
- 🏆 **获奖书单**：收集和展示各类国际图书奖项，包含详细的获奖信息
- 🆕 **新书速递**：追踪国际大型出版社最新出版物，支持按出版社筛选
- 📊 **多维度筛选**：支持按出版社、分类、时间等多维度筛选
- 🌐 **响应式设计**：适配桌面端和移动端，提供良好的用户体验
- 🔍 **智能搜索**：快速查找书籍，支持书名、作者等多字段搜索
- 📱 **优化详情页**：统一的左右布局详情页，左侧显示封面和购买链接，右侧显示图书信息
- 🎨 **统一卡片设计**：全局统一的图书卡片比例（2/3），视觉效果一致

## 技术栈

- **后端**：Flask 2.3.3 (Python 3.10+)
- **数据库**：Flask-SQLAlchemy (SQLite/PostgreSQL)
- **前端**：Jinja2 + 原生JS (ES2020+)
- **部署**：Render + Gunicorn 21.2.0
- **API集成**：NYT Books API、Google Books API
- **翻译服务**：智谱AI API

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

   应用将在 `http://localhost:5000` 运行。

## 项目结构

```
bookrank/
├── app/
│   ├── initialization/      # 初始化数据（示例数据、奖项数据）
│   ├── models/             # 数据模型（图书、奖项、出版社等）
│   ├── routes/             # 路由（主页面、API等）
│   ├── services/           # 业务逻辑（API调用、爬虫、翻译等）
│   ├── utils/              # 工具函数（安全、限流等）
│   ├── __init__.py         # 应用初始化
│   └── config.py           # 配置
├── static/                 # 静态文件
│   ├── css/                # CSS样式（基础样式、组件样式）
│   ├── js/                 # JavaScript（应用逻辑、API调用）
│   ├── data/               # 数据文件（出版社数据、缓存数据）
│   └── icons.svg           # SVG图标
├── templates/              # 模板文件
│   ├── base.html           # 基础模板
│   ├── index.html          # 首页（畅销书榜）
│   ├── awards.html         # 获奖书单
│   ├── new_books.html      # 新书速递
│   └── *detail.html        # 各类详情页
├── tests/                  # 测试文件
├── scripts/                # 脚本文件（数据同步、翻译等）
├── migrations/             # 数据库迁移
├── .env.example            # 环境变量示例
├── requirements.txt        # 依赖列表
├── run.py                  # 启动文件
└── Procfile                # Render 部署配置
```

## API 限制

- **NYT Books API**：500次/天
- **Google Books API**：1000次/天
- **智谱AI API**：根据具体套餐

## 部署

项目已配置为在 Render 平台部署，使用 Gunicorn 作为 WSGI 服务器。

### 部署步骤

1. 在 Render 平台创建新的 Web Service
2. 连接 GitHub 仓库
3. 配置环境变量（参考 `.env.example`）
4. 部署完成后，应用将自动运行

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

## 最近更新

- ✅ 修复了获奖书单详情页布局，使用统一的左右布局
- ✅ 修复了新书速递详情页左侧导航栏缺失问题
- ✅ 全局统一图书卡片比例为 2/3，提升视觉一致性
- ✅ 优化了详情页的导航结构，使用 base.html 的侧边栏

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题或建议，请通过 GitHub Issues 联系我们。
