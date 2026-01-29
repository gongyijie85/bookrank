# BookRank 项目规范

本文档定义了 BookRank 项目的开发规范和最佳实践。

## 1. 代码风格

### 1.1 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 类名 | PascalCase | `BookService`, `NYTApiClient` |
| 函数/方法 | snake_case | `get_books_by_category()`, `fetch_book_details()` |
| 变量 | snake_case | `cache_key`, `category_id` |
| 私有属性 | 单下划线前缀 | `self._api_key`, `self._cache` |
| 常量 | 全大写 SNAKE_CASE | `BASE_DIR`, `API_RATE_LIMIT` |
| 模块名 | 小写 snake_case | `book_service.py`, `api_client.py` |
| 抽象基类 | PascalCase | `CacheStrategy` |

### 1.2 格式规范

- 使用 **4 个空格** 缩进（不使用 Tab）
- 行长度不超过 **120 字符**
- 使用单引号或双引号均可，但在同一文件中保持一致
- 使用类型注解标注参数和返回类型

```python
def get_books_by_category(self, category_id: str, force_refresh: bool = False) -> List[Book]:
    """获取指定分类的图书列表"""
    pass
```

## 2. 项目结构

### 2.1 目录组织

```
BookRank/
├── app/                      # 主应用包
│   ├── __init__.py          # 应用工厂函数
│   ├── config.py            # 配置管理
│   ├── models/              # 数据模型层
│   ├── routes/              # 路由/控制器层
│   ├── services/            # 业务服务层
│   └── utils/               # 工具类
├── cache/                   # 缓存目录
├── static/                  # 静态文件
├── templates/               # 模板文件
├── run.py                   # 应用入口
└── tests/                   # 测试目录
```

### 2.2 文件组织原则

- 按功能分层（models/routes/services/utils）
- 每个模块必须包含 `__init__.py`，使用 `__all__` 显式导出公共接口
- 配置集中管理在 `config.py`
- 避免循环导入，优先使用相对导入

## 3. 导入规范

### 3.1 导入顺序

导入语句按以下顺序分组，每组之间用空行分隔：

1. **标准库导入**（`os`, `time`, `json`, `logging`）
2. **第三方库导入**（`flask`, `requests`, `werkzeug`）
3. **本地应用导入**（使用相对导入 `..` 或绝对导入）

### 3.2 示例

```python
import csv
import logging
import re
from io import StringIO
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from ..models.schemas import UserPreference, UserCategory
from ..models.database import db
from ..utils.exceptions import APIRateLimitException
from ..services import BookService
```

## 4. 文档规范

### 4.1 文档字符串风格

使用 **Google Style** 三引号文档字符串：

```python
def get_books_by_category(self, category_id: str, force_refresh: bool = False) -> List[Book]:
    """
    获取指定分类的图书列表
    
    Args:
        category_id: 分类ID
        force_refresh: 是否强制刷新缓存
        
    Returns:
        图书列表
        
    Raises:
        APIRateLimitException: 当API限流时
        APIException: 当API调用失败时
    """
```

### 4.2 注释规范

- 使用 `#` 添加解释性注释
- 中文注释用于解释业务逻辑
- 英文注释用于技术实现细节
- 使用 `TODO`, `FIXME`, `NOTE` 等标记重要注释

```python
# TODO: 添加缓存预热机制
# FIXME: Windows 下的文件锁需要特殊处理
# NOTE: 此函数会修改数据库状态
```

## 5. 错误处理

### 5.1 自定义异常

在 `app/utils/exceptions.py` 中定义异常层次：

```python
class BookRankException(Exception):
    """基础异常类"""
    pass

class APIRateLimitException(BookRankException):
    """API限流异常"""
    def __init__(self, message="API rate limit exceeded", retry_after=60):
        self.retry_after = retry_after
        super().__init__(message)

class APIException(BookRankException):
    """API调用异常"""
    def __init__(self, message="API call failed", status_code=500):
        self.status_code = status_code
        super().__init__(message)
```

### 5.2 错误处理模式

- 服务层抛出异常，路由层捕获并转换
- 使用降级策略：API失败时返回缓存数据
- 使用统一的响应格式

```python
try:
    api_data = self._nyt_client.fetch_books(category_id)
except APIRateLimitException:
    # 限流时返回缓存数据
    cached_data = self._cache.get(cache_key)
    if cached_data:
        return [Book(**book_data) for book_data in cached_data]
    raise
except APIException as e:
    logger.error(f"Failed to fetch books: {e}")
    return []
```

## 6. 配置管理

### 6.1 配置类结构

```python
class Config:
    """基础配置类"""
    SECRET_KEY: str = os.environ.get('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI: str = os.environ.get('DATABASE_URL', 'sqlite:///...')
    # ...

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG: bool = True

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG: bool = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
```

### 6.2 配置原则

- 使用类型注解
- 优先从环境变量读取，提供默认值
- 使用 `init_app()` 方法初始化应用相关配置
- 支持多环境（development/production/testing）

## 7. 日志规范

### 7.1 日志配置

```python
import logging

logger = logging.getLogger(__name__)
```

### 7.2 日志级别使用

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| `info` | 正常操作记录 | `logger.info(f"Fetched {len(books)} books")` |
| `warning` | 警告和降级 | `logger.warning(f"Cache miss for {key}")` |
| `error` | 错误和异常 | `logger.error(f"API error: {e}", exc_info=True)` |
| `debug` | 调试信息 | `logger.debug(f"Processing book: {isbn}")` |

### 7.3 日志内容

- 使用中文日志消息
- 包含上下文信息（如 `key`, `category_id`）
- 错误日志必须包含 `exc_info=True`

## 8. 数据库操作

### 8.1 模型定义

```python
class Book(db.Model):
    """图书模型"""
    __tablename__ = 'books'
    
    id = db.Column(db.String(13), primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat()
        }
```

### 8.2 事务处理

```python
try:
    db.session.add(book)
    db.session.commit()
except Exception as e:
    logger.error(f"Database error: {e}")
    db.session.rollback()
    raise
```

## 9. API 设计

### 9.1 响应格式

```python
{
    "success": true,
    "data": { ... },
    "message": "Success"
}

{
    "success": false,
    "message": "Error message",
    "errors": { ... }  # 可选
}
```

### 9.2 路由定义

```python
@api_bp.route('/books/<category>')
def get_books(category: str):
    """获取图书列表"""
    try:
        # 业务逻辑
        return APIResponse.success(data={...})
    except APIRateLimitException as e:
        return APIResponse.error(f'Rate limit exceeded', 429)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return APIResponse.error('Internal server error', 500)
```

## 10. 缓存策略

### 10.1 多级缓存

```python
# 1. 尝试从内存缓存获取
value = self._memory.get(key)
if value is not None:
    return value

# 2. 尝试从文件缓存获取
value = self._file.get(key)
if value is not None:
    # 回填内存缓存
    self._memory.set(key, value)
    return value

return None
```

### 10.2 缓存键命名

```python
cache_key = f"books_{category_id}"
cache_key = f"search_{keyword_hash}"
cache_key = f"book_details_{isbn}"
```

## 11. 安全规范

### 11.1 输入验证

```python
import re

# 验证关键词（防止XSS）
if not re.match(r'^[\w\s\-\u4e00-\u9fff]+$', keyword):
    return APIResponse.error('Invalid keyword format', 400)

# 使用 secure_filename 防止路径遍历
from werkzeug.utils import secure_filename
filename = secure_filename(user_input)
```

### 11.2 敏感信息

- API 密钥存储在环境变量中
- 不在代码中硬编码敏感信息
- 使用 `.env` 文件管理本地环境变量

## 12. 测试规范

### 12.1 测试结构

```python
import unittest

class TestBookService(unittest.TestCase):
    """图书服务测试"""
    
    def setUp(self):
        """测试前准备"""
        self.service = BookService(...)
    
    def test_get_books_by_category(self):
        """测试获取图书列表"""
        books = self.service.get_books_by_category('hardcover-fiction')
        self.assertIsInstance(books, list)
    
    def tearDown(self):
        """测试后清理"""
        pass
```

## 13. Git 规范

### 13.1 提交信息格式

```
<type>: <subject>

<body>

<footer>
```

**类型（type）**:
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `style`: 格式（不影响代码运行的变动）
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建过程或辅助工具的变动

**示例**:
```
feat: 添加图书搜索功能

- 实现关键词搜索
- 添加搜索结果缓存
- 更新 API 文档

Closes #123
```

### 13.2 分支管理

- `main`: 主分支，稳定版本
- `develop`: 开发分支
- `feature/*`: 功能分支
- `hotfix/*`: 紧急修复分支

## 14. 部署规范

### 14.1 环境变量

必需的环境变量：
- `FLASK_ENV`: 运行环境（development/production）
- `SECRET_KEY`: 应用密钥
- `DATABASE_URL`: 数据库连接字符串
- `NYT_API_KEY`: 纽约时报 API 密钥

### 14.2 生产环境检查清单

- [ ] 设置 `FLASK_ENV=production`
- [ ] 配置强密码的 `SECRET_KEY`
- [ ] 使用 PostgreSQL 而非 SQLite
- [ ] 配置日志记录
- [ ] 禁用调试模式
- [ ] 配置 HTTPS
- [ ] 设置适当的 `WEB_CONCURRENCY`

## 15. 代码审查检查清单

### 15.1 提交前自检

- [ ] 代码符合命名规范
- [ ] 添加了必要的文档字符串和注释
- [ ] 处理了可能的异常情况
- [ ] 没有硬编码的敏感信息
- [ ] 添加了必要的日志记录
- [ ] 代码通过本地测试

### 15.2 审查关注点

- 代码可读性和可维护性
- 错误处理是否完善
- 性能影响（如 N+1 查询问题）
- 安全风险（如 SQL 注入、XSS）
- 是否符合项目架构设计

---

## 参考

- [PEP 8 - Python 代码风格指南](https://pep8.org/)
- [Google Python 风格指南](https://google.github.io/styleguide/pyguide.html)
- [Flask 文档](https://flask.palletsprojects.com/)
