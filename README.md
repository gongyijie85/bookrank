# BookRank

纽约时报畅销书排行榜应用，追踪国际大型出版社最新出版物，展示各类图书奖项。

## 项目简介

BookRank 是一个聚合全球优质图书信息的平台，旨在为读者提供一站式的图书发现体验。通过整合纽约时报畅销书榜单和国际文学奖项，结合智能翻译和实时更新，为用户打造一个全面、便捷的图书信息中心。

## 功能特性

- 📚 **畅销书榜单**：展示纽约时报各类别畅销书，支持多维度排序和筛选
- 🏆 **获奖书单**：收集和展示8大国际图书奖项，包含详细的获奖信息
- 🆕 **新书速递**：追踪国际大型出版社最新出版物，支持按出版社筛选
- 📊 **多维度筛选**：支持按出版社、分类、时间等多维度筛选
- 🌐 **响应式设计**：适配桌面端和移动端，提供良好的用户体验
- 🔍 **智能搜索**：快速查找书籍，支持书名、作者等多字段搜索
- 📱 **优化详情页**：统一的左右布局详情页，左侧显示封面和购买链接，右侧显示图书信息
- 🎨 **统一卡片设计**：全局统一的图书卡片比例（2/3），视觉效果一致
- 🌍 **智能翻译**：提供书名、简介的中文翻译，降低语言门槛
- 🚀 **实时更新**：自动同步最新榜单数据，确保信息时效性
- 🔓 **开放API**：提供公开API，支持第三方系统集成

## 技术栈

- **后端**：Flask 2.3.3 (Python 3.10+)
- **数据库**：Flask-SQLAlchemy (SQLite/PostgreSQL)
- **前端**：Jinja2 + 原生JS (ES2020+)
- **部署**：Render + Gunicorn 21.2.0
- **API集成**：NYT Books API、Google Books API、Open Library API
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
   NYT_API_KEY=your-nyt-api-key
   GOOGLE_API_KEY=your-google-api-key
   ZHIPU_API_KEY=your-zhipu-api-key
   DATABASE_URL=your-database-url
   ```

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
│   ├── initialization/           # 初始化模块
│   │   ├── awards.py             # 奖项初始化
│   │   └── sample_books.py       # 示例数据初始化
│   ├── models/                   # 数据模型层
│   │   ├── database.py           # 数据库连接
│   │   └── schemas.py            # 数据模型定义
│   ├── routes/                   # 路由控制层
│   │   ├── main.py               # 页面路由
│   │   ├── api.py                # 内部API
│   │   └── public_api.py         # 公开API
│   ├── services/                 # 业务服务层
│   │   ├── api_client.py         # API客户端
│   │   ├── book_service.py       # 图书服务
│   │   ├── award_book_service.py # 获奖图书服务
│   │   ├── cache_service.py      # 缓存服务
│   │   └── translation_service.py # 翻译服务
│   └── utils/                    # 工具模块
│       ├── exceptions.py         # 自定义异常
│       ├── rate_limiter.py       # 限流器
│       └── security.py           # 安全工具
├── static/                       # 静态资源
│   ├── css/                      # CSS样式
│   ├── js/                       # JavaScript
│   ├── data/                     # 数据文件
│   └── webfonts/                 # 字体文件
├── templates/                    # 模板文件
│   ├── base.html                 # 基础模板
│   ├── index.html                # 首页（畅销书榜）
│   ├── awards.html               # 获奖书单
│   ├── new_books.html            # 新书速递
│   └── *detail.html              # 各类详情页
├── tests/                        # 测试文件
├── scripts/                      # 脚本工具
├── migrations/                   # 数据库迁移
├── docs/                         # 文档目录
├── .env.example                  # 环境变量示例
├── requirements.txt              # 依赖列表
├── run.py                        # 启动文件
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
└── /book/{isbn}              # 图书详情
```

## 最近更新

- ✅ 修复了获奖书单详情页布局，使用统一的左右布局
- ✅ 修复了新书速递详情页左侧导航栏缺失问题
- ✅ 全局统一图书卡片比例为 2/3，提升视觉一致性
- ✅ 优化了详情页的导航结构，使用 base.html 的侧边栏
- ✅ 增强了安全防护，添加了响应头安全配置
- ✅ 优化了 Render 免费版部署配置，提高性能

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
