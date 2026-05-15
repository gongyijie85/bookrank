# 国际图书奖项榜单 - 第二阶段PRD文档（精简版）

## 1. 项目背景

### 1.1 业务背景
- **用户角色**：外文书商，主营外文书销售
- **目标**：展示国际权威图书奖项获奖作品，辅助选品和销售决策

### 1.2 数据范围
| 奖项 | 国家 | 更新周期 | 2026年颁布时间 |
|------|------|----------|----------------|
| 普利策奖 | 美国 | 年度 | 5月 |
| 美国国家图书奖 | 美国 | 年度 | 11月 |
| 布克奖 | 英国 | 年度 | 11月 |
| 雨果奖 | 美国 | 年度 | 8月 |
| 诺贝尔文学奖 | 瑞典 | 年度 | 10月 |

### 1.3 技术约束
- **部署平台**：Render免费版（512MB RAM限制）
- **技术栈**：Flask + SQLite（轻量级方案）

---

## 2. 第一阶段现状

### 2.1 已实现功能
- [x] 基础页面 `awards.html` - 奖项卡片展示
- [x] 翻译服务 `translation_service.py` - 基于 deep-translator
- [x] 数据库基础 `database.py` - Flask-SQLAlchemy
- [x] 基础API `app.py` - NYT畅销书接口

### 2.2 现有技术资产
- 依赖已安装：`deep-translator==1.11.4`
- 数据库模型：`schemas.py` - 包含 BookMetadata 等模型
- 缓存机制：文件缓存 + 内存缓存

---

## 3. 第二阶段需求

### 3.1 核心功能

| 功能模块 | 需求描述 | 优先级 |
|----------|----------|--------|
| 单页应用 | 复用现有 `awards.html`，增加交互功能 | P0 |
| 模态框详情 | 点击图书卡片弹出详情模态框 | P0 |
| 筛选功能 | 按奖项、年份、类别筛选 | P0 |
| 搜索功能 | 按书名、作者搜索 | P1 |
| 响应式设计 | 适配移动端和桌面端 | P0 |

### 3.2 数据策略

#### 3.2.1 数据导入计划
```
2023-2025年数据：一次性静态导入
├── 普利策奖：约 18本/年 × 3年 = 54本
├── 美国国家图书奖：约 20本/年 × 3年 = 60本
├── 布克奖：约 6本/年 × 3年 = 18本
├── 雨果奖：约 15本/年 × 3年 = 45本
└── 诺贝尔文学奖：约 1本/年 × 3年 = 3本
总计：约 180本（2023-2025固定数据）
```

#### 3.2.2 2026年更新计划
| 月份 | 奖项 | 操作 |
|------|------|------|
| 5月 | 普利策奖 | 手动导入 |
| 8月 | 雨果奖 | 手动导入 |
| 10月 | 诺贝尔文学奖 | 手动导入 |
| 11月 | 美国国家图书奖、布克奖 | 手动导入 |

#### 3.2.3 封面处理
- 下载到本地 `static/covers/` 目录
- 压缩至 50KB 以内
- 使用 WebP 格式优化

#### 3.2.4 翻译策略
- 预翻译所有书名和简介
- 缓存翻译结果到数据库
- 复用现有 `translation_service.py`

---

## 4. 数据库设计

### 4.1 新增数据表

```sql
-- 奖项表
CREATE TABLE awards (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- 奖项名称
    name_en VARCHAR(100),                  -- 英文名称
    country VARCHAR(50),                   -- 国家
    description TEXT,                      -- 奖项介绍
    category_count INTEGER,                -- 奖项类别数
    icon_class VARCHAR(50)                 -- 图标样式类
);

-- 获奖图书表
CREATE TABLE award_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    award_id INTEGER NOT NULL,             -- 奖项ID
    year INTEGER NOT NULL,                 -- 获奖年份
    category VARCHAR(100),                 -- 奖项类别（如小说、非虚构）
    rank INTEGER,                          -- 排名（如有）
    
    -- 图书基本信息
    title VARCHAR(500) NOT NULL,           -- 书名（英文）
    title_zh VARCHAR(500),                 -- 书名（中文翻译）
    author VARCHAR(300) NOT NULL,          -- 作者
    description TEXT,                      -- 简介（英文）
    description_zh TEXT,                   -- 简介（中文翻译）
    
    -- 封面和链接
    cover_local_path VARCHAR(255),         -- 本地封面路径
    cover_original_url VARCHAR(500),       -- 原始封面URL
    
    -- 元数据
    isbn13 VARCHAR(13),                    -- ISBN-13
    isbn10 VARCHAR(10),                    -- ISBN-10
    publisher VARCHAR(200),                -- 出版社
    publication_year INTEGER,              -- 出版年份
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (award_id) REFERENCES awards(id),
    UNIQUE(award_id, year, category, isbn13)
);

-- 创建索引
CREATE INDEX idx_award_books_award_year ON award_books(award_id, year);
CREATE INDEX idx_award_books_category ON award_books(category);
CREATE INDEX idx_award_books_search ON award_books(title, author);
```

---

## 5. API设计

### 5.1 奖项相关接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/awards` | GET | 获取所有奖项列表 |
| `/api/awards/<id>/books` | GET | 获取指定奖项的图书列表 |

### 5.2 图书相关接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/books` | GET | 获取图书列表（支持筛选） |
| `/api/books/<id>` | GET | 获取图书详情 |
| `/api/books/search` | GET | 搜索图书 |

### 5.3 查询参数

```
GET /api/books?award_id=1&year=2024&category=fiction&page=1&limit=20
参数说明：
- award_id: 奖项ID筛选
- year: 年份筛选
- category: 类别筛选
- keyword: 搜索关键词
- page: 页码
- limit: 每页数量
```

---

## 6. 前端设计

### 6.1 页面结构

```
awards.html 页面结构
├── Header（标题 + 返回链接）
├── Filter Bar（筛选栏）
│   ├── 奖项选择（下拉/标签）
│   ├── 年份选择（下拉）
│   ├── 类别选择（下拉）
│   └── 搜索框
├── Book Grid（图书网格）
│   └── Book Card × N
│       ├── 封面图
│       ├── 排名徽章（前三名皇冠图标）
│       ├── 书名（中英文）
│       └── 作者
└── Book Detail Modal（详情模态框）
    ├── 关闭按钮
    ├── 封面大图
    ├── 完整信息
    └── 简介（中英文切换）
```

### 6.2 交互说明

| 交互 | 行为 |
|------|------|
| 点击图书卡片 | 打开详情模态框 |
| 筛选条件变化 | 实时刷新列表 |
| 搜索输入 | 防抖300ms后搜索 |
| 语言切换 | 全局切换中英文显示 |

---

## 7. 实施计划（4天）

### Day 1：数据库 + 数据导入
- [ ] 创建奖项表和获奖图书表
- [ ] 编写数据导入脚本
- [ ] 准备2023-2025年基础数据
- [ ] 测试数据导入流程

### Day 2：API开发
- [ ] 实现奖项列表接口
- [ ] 实现图书列表接口（含筛选）
- [ ] 实现图书详情接口
- [ ] 实现搜索接口
- [ ] API测试

### Day 3：前端对接 + 翻译
- [ ] 改造 `awards.html` 添加筛选栏
- [ ] 实现图书网格展示
- [ ] 实现详情模态框
- [ ] 批量翻译书名和简介
- [ ] 联调测试

### Day 4：部署
- [ ] 本地完整测试
- [ ] 封面图片整理
- [ ] Render部署
- [ ] 线上验证

---

## 8. 第三阶段规划（未来扩展）

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 用户收藏 | 用户可收藏感兴趣的图书 | P1 |
| 评分功能 | 用户对图书进行评分 | P2 |
| 购买链接 | 关联外文书购买渠道 | P1 |
| 数据自动更新 | 爬虫自动获取最新获奖信息 | P2 |
| 统计分析 | 热门奖项、热门作者统计 | P3 |

---

## 9. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| Render 512MB内存限制 | 高 | 优化图片大小，使用分页加载 |
| 翻译API限流 | 中 | 预翻译并缓存，避免实时翻译 |
| 数据准确性 | 高 | 手动验证2023-2025数据 |
| 封面图片版权 | 低 | 使用公开封面或默认封面 |

---

## 10. 验收标准

- [ ] 5个奖项数据完整展示
- [ ] 筛选功能正常工作（奖项、年份、类别）
- [ ] 搜索功能支持书名和作者
- [ ] 模态框展示图书详情
- [ ] 中英文切换正常
- [ ] 移动端适配良好
- [ ] Render部署成功且可访问

---

**文档版本**：v1.0  
**编写日期**：2026-01-30  
**适用阶段**：第二阶段开发
