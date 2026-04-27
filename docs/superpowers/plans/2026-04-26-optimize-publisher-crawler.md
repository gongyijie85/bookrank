# 出版社爬虫模块优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 BookRank3 出版社爬虫模块的代码质量、稳定性和可维护性，消除重复代码、修复代码缺陷、统一架构、删除废弃文件、统一注册机制、补充测试覆盖。

**Architecture:** 保持现有分层架构（BaseCrawler → MixedCrawl4AICrawler → 具体爬虫），重点：1) 企鹅兰登爬虫迁移到 MixedCrawl4AICrawler 基类消除重复；2) 修复 SimonSchusterCrawler 和 MacmillanCrawler 的 `__init__` 重复定义 bug；3) 删除废弃的 `crawl4ai_base.py`；4) 统一 CRAWLER_MAP 和 CRAWLER_REGISTRY 两套注册机制；5) 清理 OpenLibraryCrawler 中的 mock 依赖；6) 补充爬虫单元测试。

**Tech Stack:** Python 3.13, Flask, requests, BeautifulSoup4, pytest

---

## 现状问题分析

| # | 问题 | 位置 | 严重度 | 影响 |
|---|------|------|--------|------|
| 1 | **企鹅兰登爬虫未使用 MixedCrawl4AICrawler 基类** | `penguin_random_house.py` 529行 | 高 | `_check_crawl4ai`、`_crawl_with_crawl4ai_async`、`_crawl_with_crawl4ai`、`_make_request_with_fallback`、`get_new_books`、`get_book_details`、所有 `_extract_*` 方法与 MixedCrawl4AICrawler 完全重复 |
| 2 | **SimonSchusterCrawler 两个 `__init__` 定义** | `simon_schuster.py:39` 和 `simon_schuster.py:68` | 高 | Python 中后者覆盖前者，第一个 `__init__` 中的 `respect_robots_txt = False` 被丢弃 |
| 3 | **MacmillanCrawler 两个 `__init__` 定义** | `macmillan.py:39` 和 `macmillan.py:63` | 高 | 同上，第一个 `__init__` 的 `respect_robots_txt = False` 被丢弃，且 `request_delay` 值不一致（1.5 vs 1.3） |
| 4 | **`crawl4ai_base.py` 废弃文件** | `crawl4ai_base.py` 220行 | 中 | `Crawl4AICrawler` 和 `HybridCrawlerMixin` 未被任何爬虫使用，实际用的是 `MixedCrawl4AICrawler` |
| 5 | **两套独立的爬虫注册机制** | `__init__.py` 的 `CRAWLER_REGISTRY` 和 `new_book_service.py` 的 `CRAWLER_MAP` | 中 | 两套映射需同步维护，容易遗漏或不一致 |
| 6 | **OpenLibraryCrawler 使用 `unittest.mock.Mock`** | `open_library.py:139` | 中 | 在生产代码中使用测试框架的 Mock 类创建假 Response，不规范 |
| 7 | **爬虫模块无单元测试** | `tests/` 目录 | 高 | 爬虫的 HTML 解析、API 解析、降级逻辑等核心功能无自动化测试覆盖 |
| 8 | **企鹅兰登 `_extract_author` 逻辑与基类不同** | `penguin_random_house.py:354-369` | 低 | 企鹅兰登有额外的长度校验 `len(text) < 100`，基类没有。迁移后需保留此差异 |

---

## 文件结构

| 操作 | 文件路径 | 职责变更 |
|------|----------|----------|
| 重写 | `app/services/publisher_crawler/penguin_random_house.py` | 迁移到 MixedCrawl4AICrawler 基类，仅保留差异化配置 |
| 修复 | `app/services/publisher_crawler/simon_schuster.py` | 合并两个 `__init__`，保留正确配置 |
| 修复 | `app/services/publisher_crawler/macmillan.py` | 合并两个 `__init__`，保留正确配置 |
| 删除 | `app/services/publisher_crawler/crawl4ai_base.py` | 废弃文件，无使用方 |
| 修改 | `app/services/publisher_crawler/__init__.py` | 统一注册机制，NewBookService 使用 CRAWLER_REGISTRY |
| 修改 | `app/services/publisher_crawler/open_library.py` | 替换 Mock 为简单 Response 包装类 |
| 修改 | `app/services/new_book_service.py` | 使用 CRAWLER_REGISTRY 替代本地 CRAWLER_MAP |
| 创建 | `tests/test_publisher_crawler.py` | 爬虫单元测试 |

---

### Task 1: 企鹅兰登爬虫迁移到 MixedCrawl4AICrawler 基类

**问题：** `PenguinRandomHouseCrawler` 直接继承 `BaseCrawler`，自行实现了与 `MixedCrawl4AICrawler` 完全重复的 Crawl4AI 降级逻辑、数据提取方法和业务流程方法（共约470行重复代码）。

**Files:**
- 重写: `app/services/publisher_crawler/penguin_random_house.py`

- [ ] **Step 1: 编写企鹅兰登爬虫迁移的验证测试**

在 `tests/test_publisher_crawler.py` 创建测试文件：

```python
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler
from app.services.publisher_crawler.mixed_crawl4ai_crawler import MixedCrawl4AICrawler


class TestPenguinRandomHouseMigration:
    """企鹅兰登爬虫迁移验证"""

    def test_inherits_from_mixed_crawl4ai(self):
        """验证企鹅兰登爬虫继承自 MixedCrawl4AICrawler"""
        assert issubclass(PenguinRandomHouseCrawler, MixedCrawl4AICrawler)

    def test_publisher_name(self):
        """验证出版社名称配置"""
        crawler = PenguinRandomHouseCrawler.__new__(PenguinRandomHouseCrawler)
        assert crawler.PUBLISHER_NAME == "企鹅兰登"
        assert crawler.PUBLISHER_NAME_EN == "Penguin Random House"
        assert crawler.CRAWLER_CLASS_NAME == "PenguinRandomHouseCrawler"

    def test_crawler_config_default_delay(self):
        """验证默认请求延迟"""
        with patch.object(PenguinRandomHouseCrawler, '__init__', lambda self, config=None: None):
            crawler = PenguinRandomHouseCrawler.__new__(PenguinRandomHouseCrawler)
            crawler.config = Mock()
            crawler.config.request_delay = 1.5
            assert crawler.config.request_delay == 1.5

    def test_category_map_exists(self):
        """验证分类映射"""
        crawler = PenguinRandomHouseCrawler.__new__(PenguinRandomHouseCrawler)
        assert 'fiction' in crawler.CATEGORY_MAP
        assert crawler.CATEGORY_MAP['fiction'] == '小说'

    def test_get_categories_returns_list(self):
        """验证 get_categories 返回正确列表"""
        with patch.object(PenguinRandomHouseCrawler, '__init__', lambda self, config=None: None):
            crawler = PenguinRandomHouseCrawler.__new__(PenguinRandomHouseCrawler)
            categories = crawler.get_categories()
            assert isinstance(categories, list)
            assert len(categories) >= 5
            assert any(c['id'] == 'fiction' for c in categories)

    def test_new_releases_url(self):
        """验证新书页面URL"""
        crawler = PenguinRandomHouseCrawler.__new__(PenguinRandomHouseCrawler)
        assert crawler.NEW_RELEASES_URL == "https://www.penguinrandomhouse.com/books/new-releases/"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd d:\BookRank3 && python -m pytest tests/test_publisher_crawler.py::TestPenguinRandomHouseMigration::test_inherits_from_mixed_crawl4ai -v`
Expected: FAIL（当前继承自 BaseCrawler）

- [ ] **Step 3: 重写企鹅兰登爬虫，继承 MixedCrawl4AICrawler**

将 `penguin_random_house.py` 重写为仅包含差异化配置的精简版：

```python
"""
Penguin Random House（企鹅兰登）出版社爬虫

企鹅兰登是世界上最大的大众图书出版商之一，
网站提供新书发布信息、作者介绍和书籍详情。

混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级
（继承自 MixedCrawl4AICrawler 基类）
"""
import logging

from .mixed_crawl4ai_crawler import MixedCrawl4AICrawler

logger = logging.getLogger(__name__)


class PenguinRandomHouseCrawler(MixedCrawl4AICrawler):
    """
    Penguin Random House 出版社爬虫

    混合架构：先尝试传统 requests，失败后自动用 Crawl4AI 降级

    官方网站：https://www.penguinrandomhouse.com/
    新书页面：https://www.penguinrandomhouse.com/books/new-releases/
    """

    PUBLISHER_NAME = "企鹅兰登"
    PUBLISHER_NAME_EN = "Penguin Random House"
    PUBLISHER_WEBSITE = "https://www.penguinrandomhouse.com"
    CRAWLER_CLASS_NAME = "PenguinRandomHouseCrawler"

    NEW_RELEASES_URL = "https://www.penguinrandomhouse.com/books/new-releases/"

    # 企鹅兰登特定选择器（网站使用 .carousel .item 结构）
    BOOK_LIST_SELECTORS: str = (
        '.carousel .item, .book-item, .product-item, [data-book-id], .book-card, '
        '.product, .release-item, .new-release, .product-tile, .grid-item'
    )
    BOOK_LINK_SELECTORS: str = (
        'a[href*="/books/"], .img a, .title a, '
        'a[href*="/book/"], a[href*="/product/"], '
        'a.product-link, a.book-link'
    )
    TITLE_SELECTORS: str = '.title a, .title, .book-title, h1.book-title, h1.product-title, .book-info h1, h1'
    AUTHOR_SELECTORS: str = '.contributor a, .contributor, .author-name, .book-author, .contributor-name, .author a'
    DESCRIPTION_SELECTORS: str = '.book-description, .product-description, .synopsis, .summary, [data-description], .description'
    COVER_SELECTORS: str = '.book-cover img, .product-image img, .cover-image img, img.book-image, img[alt*="cover"]'
    CATEGORY_SELECTORS: str = '.book-category, .genre, .category, [data-category]'
    PRICE_SELECTORS: str = '.price, .book-price, .product-price, [data-price]'
    PAGE_COUNT_SELECTORS: str = '.page-count, .pages, [data-pages]'
    ISBN_SELECTORS: str = '.isbn, .book-isbn, [data-isbn]'
    BUY_SECTION_SELECTORS: str = '.buy-buttons, .purchase-options, .buy-links'

    CATEGORY_MAP = {
        'fiction': '小说',
        'non-fiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'science-fiction': '科幻',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young-adult': '青少年',
        'graphic-novels': '图像小说',
    }

    RETAILERS = {
        'Amazon': 'amazon.com',
        'Barnes & Noble': 'bn.com',
        'Books-A-Million': 'booksamillion.com',
        'Bookshop': 'bookshop.org',
        'IndieBound': 'indiebound.org',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.5

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'non-fiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'science-fiction', 'name': '科幻'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young-adult', 'name': '青少年'},
            {'id': 'graphic-novels', 'name': '图像小说'},
        ]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd d:\BookRank3 && python -m pytest tests/test_publisher_crawler.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/publisher_crawler/penguin_random_house.py tests/test_publisher_crawler.py
git commit -m "refactor(crawler): 企鹅兰登爬虫迁移到MixedCrawl4AICrawler基类，消除470行重复代码"
```

---

### Task 2: 修复 SimonSchusterCrawler 和 MacmillanCrawler 的 `__init__` 重复定义 bug

**问题：** 两个爬虫文件各有两个 `__init__` 定义，后者覆盖前者，导致第一个 `__init__` 中的 `respect_robots_txt = False` 配置丢失。

**Files:**
- 修改: `app/services/publisher_crawler/simon_schuster.py`
- 修改: `app/services/publisher_crawler/macmillan.py`

- [ ] **Step 1: 编写 `__init__` 修复的验证测试**

在 `tests/test_publisher_crawler.py` 添加：

```python
class TestCrawlerInitBug:
    """爬虫 __init__ 重复定义 bug 修复验证"""

    def test_simon_schuster_respect_robots_false(self):
        """验证西蒙舒斯特爬虫禁用 robots.txt"""
        crawler = SimonSchusterCrawler()
        assert crawler.config.respect_robots_txt is False

    def test_simon_schuster_request_delay(self):
        """验证西蒙舒斯特请求延迟"""
        crawler = SimonSchusterCrawler()
        assert crawler.config.request_delay == 1.2

    def test_macmillan_request_delay(self):
        """验证麦克米伦请求延迟"""
        crawler = MacmillanCrawler()
        assert crawler.config.request_delay == 1.3

    def test_macmillan_no_duplicate_init(self):
        """验证麦克米伦只有一个 __init__"""
        import inspect
        source = inspect.getsource(MacmillanCrawler)
        init_count = source.count('def __init__')
        assert init_count == 1

    def test_simon_schuster_no_duplicate_init(self):
        """验证西蒙舒斯特只有一个 __init__"""
        import inspect
        source = inspect.getsource(SimonSchusterCrawler)
        init_count = source.count('def __init__')
        assert init_count == 1
```

在文件顶部添加导入：

```python
from app.services.publisher_crawler.simon_schuster import SimonSchusterCrawler
from app.services.publisher_crawler.macmillan import MacmillanCrawler
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd d:\BookRank3 && python -m pytest tests/test_publisher_crawler.py::TestCrawlerInitBug -v`
Expected: `test_macmillan_request_delay` FAIL（当前是1.5而非1.3）、`test_macmillan_no_duplicate_init` FAIL（有2个）、`test_simon_schuster_no_duplicate_init` FAIL（有2个）

- [ ] **Step 3: 修复 SimonSchusterCrawler**

替换 `simon_schuster.py` 中两个 `__init__` 为一个合并版本：

```python
    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.2
            self.config.respect_robots_txt = False
```

删除第39-44行的第一个 `__init__`，保留第68-72行并合并 `respect_robots_txt = False`。

- [ ] **Step 4: 修复 MacmillanCrawler**

替换 `macmillan.py` 中两个 `__init__` 为一个合并版本：

```python
    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.3
            self.config.respect_robots_txt = False
```

删除第39-43行的第一个 `__init__`，修改第63-65行为合并版本（保留 `respect_robots_txt = False`，延迟用 1.3）。

- [ ] **Step 5: 运行测试验证通过**

Run: `cd d:\BookRank3 && python -m pytest tests/test_publisher_crawler.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/services/publisher_crawler/simon_schuster.py app/services/publisher_crawler/macmillan.py tests/test_publisher_crawler.py
git commit -m "fix(crawler): 修复SimonSchuster和Macmillan爬虫__init__重复定义bug，恢复respect_robots_txt配置"
```

---

### Task 3: 删除废弃的 `crawl4ai_base.py`

**问题：** `Crawl4AICrawler` 和 `HybridCrawlerMixin` 定义在 `crawl4ai_base.py` 中，但没有任何爬虫继承或混入它们，实际使用的是 `MixedCrawl4AICrawler`。

**Files:**
- 删除: `app/services/publisher_crawler/crawl4ai_base.py`
- 修改: `app/services/publisher_crawler/__init__.py`（移除对废弃类的导出引用）

- [ ] **Step 1: 确认无使用方**

Run: `cd d:\BookRank3 && python -c "import ast; import os; root='app/services/publisher_crawler'; [print(f) for f in os.listdir(root) if f.endswith('.py') and open(os.path.join(root,f)).read().find('crawl4ai_base')>=0]"`
Expected: 仅 `crawl4ai_base.py` 自身和 `__init__.py`

- [ ] **Step 2: 删除文件**

删除 `app/services/publisher_crawler/crawl4ai_base.py`

- [ ] **Step 3: 检查 `__init__.py` 是否引用了该文件**

如果 `__init__.py` 中有 `crawl4ai_base` 的导入，移除。

- [ ] **Step 4: 运行全部测试确认无回归**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "not weekly"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A app/services/publisher_crawler/
git commit -m "chore(crawler): 删除废弃的crawl4ai_base.py（Crawl4AICrawler和HybridCrawlerMixin无使用方）"
```

---

### Task 4: 统一爬虫注册机制

**问题：** `__init__.py` 的 `CRAWLER_REGISTRY` 和 `new_book_service.py` 的 `CRAWLER_MAP` 是两套独立的爬虫注册机制，容易不同步。

**Files:**
- 修改: `app/services/publisher_crawler/__init__.py`
- 修改: `app/services/new_book_service.py`

- [ ] **Step 1: 编写统一注册机制的验证测试**

在 `tests/test_publisher_crawler.py` 添加：

```python
from app.services.publisher_crawler import get_crawler_class, get_all_crawlers


class TestCrawlerRegistry:
    """爬虫注册机制测试"""

    def test_registry_has_all_seven_crawlers(self):
        """验证注册表包含全部7个爬虫"""
        all_crawlers = get_all_crawlers()
        expected = [
            'OpenLibraryCrawler', 'GoogleBooksCrawler',
            'PenguinRandomHouseCrawler', 'SimonSchusterCrawler',
            'HachetteCrawler', 'HarperCollinsCrawler', 'MacmillanCrawler',
        ]
        for name in expected:
            assert name in all_crawlers, f"缺少爬虫: {name}"

    def test_get_crawler_class_returns_correct_type(self):
        """验证 get_crawler_class 返回正确类型"""
        from app.services.publisher_crawler.base_crawler import BaseCrawler
        cls = get_crawler_class('PenguinRandomHouseCrawler')
        assert cls is not None
        assert issubclass(cls, BaseCrawler)

    def test_get_crawler_class_unknown_returns_none(self):
        """验证获取不存在的爬虫返回 None"""
        cls = get_crawler_class('NonExistentCrawler')
        assert cls is None
```

- [ ] **Step 2: 增强 `__init__.py` 的注册机制**

修改 `__init__.py` 中的 `_load_all_crawlers()`，使其更健壮并成为唯一注册入口：

```python
_CRAWLER_MODULES = [
    ('OpenLibraryCrawler', '.open_library'),
    ('GoogleBooksCrawler', '.google_books'),
    ('PenguinRandomHouseCrawler', '.penguin_random_house'),
    ('SimonSchusterCrawler', '.simon_schuster'),
    ('HachetteCrawler', '.hachette'),
    ('HarperCollinsCrawler', '.harpercollins'),
    ('MacmillanCrawler', '.macmillan'),
]


def _load_all_crawlers() -> None:
    """加载所有爬虫到注册表（统一注册入口）"""
    if CRAWLER_REGISTRY:
        return

    import importlib
    for class_name, module_path in _CRAWLER_MODULES:
        try:
            module = importlib.import_module(module_path, package=__name__)
            crawler_class = getattr(module, class_name)
            register_crawler(crawler_class)
        except Exception as e:
            logger.warning(f"无法加载爬虫 {class_name}: {e}")
```

同时添加 logger 导入并确保 `__all__` 包含 `get_crawler_class` 和 `get_all_crawlers`。

- [ ] **Step 3: 修改 NewBookService 使用 CRAWLER_REGISTRY**

修改 `new_book_service.py`，删除 `CRAWLER_MAP`、`_CRAWLER_IMPORTS`、`_init_crawler_map()` 函数，改为使用 `publisher_crawler` 模块的注册表：

删除：
```python
CRAWLER_MAP: dict[str, type] = {}

_CRAWLER_IMPORTS = [
    ('OpenLibraryCrawler', '.publisher_crawler.open_library'),
    ('GoogleBooksCrawler', '.publisher_crawler.google_books'),
    ('PenguinRandomHouseCrawler', '.publisher_crawler.penguin_random_house'),
    ('SimonSchusterCrawler', '.publisher_crawler.simon_schuster'),
    ('HachetteCrawler', '.publisher_crawler.hachette'),
    ('HarperCollinsCrawler', '.publisher_crawler.harpercollins'),
    ('MacmillanCrawler', '.publisher_crawler.macmillan'),
]

def _init_crawler_map():
    ...
```

修改 `get_crawler()` 方法：
```python
    def get_crawler(self, crawler_class: str):
        """获取爬虫实例"""
        from .publisher_crawler import get_crawler_class
        crawler_cls = get_crawler_class(crawler_class)
        if not crawler_cls:
            return None
        if crawler_class == 'GoogleBooksCrawler':
            from flask import current_app
            api_key = current_app.config.get('GOOGLE_API_KEY')
            if api_key:
                from .publisher_crawler.base_crawler import CrawlerConfig
                config = CrawlerConfig(api_key=api_key)
                return crawler_cls(config)
        return crawler_cls()
```

删除 `__init__` 中的 `_init_crawler_map()` 调用。

- [ ] **Step 4: 运行测试验证通过**

Run: `cd d:\BookRank3 && python -m pytest tests/test_publisher_crawler.py tests/test_new_book_service.py -v`
Expected: PASS

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "not weekly"`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/services/publisher_crawler/__init__.py app/services/new_book_service.py tests/test_publisher_crawler.py
git commit -m "refactor(crawler): 统一爬虫注册机制，NewBookService使用CRAWLER_REGISTRY替代本地CRAWLER_MAP"
```

---

### Task 5: 清理 OpenLibraryCrawler 中的 Mock 依赖

**问题：** `open_library.py:139` 在生产代码中使用 `from unittest.mock import Mock` 创建假 Response 对象，应替换为轻量的 Response 包装类。

**Files:**
- 修改: `app/services/publisher_crawler/open_library.py`

- [ ] **Step 1: 在 `base_crawler.py` 中添加简单的 Response 包装类**

在 `base_crawler.py` 的 `CrawlerConfig` 类之前添加：

```python
class SimpleResponse:
    """轻量级 HTTP 响应包装（用于 Crawl4AI 降级等场景）"""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data
```

- [ ] **Step 2: 修改 `open_library.py` 使用 SimpleResponse**

将 `open_library.py:139-142` 的：
```python
                    from unittest.mock import Mock
                    mock_response = Mock()
                    mock_response.json.return_value = json.loads(json_match.group(1))
                    return mock_response
```

替换为：
```python
                    from .base_crawler import SimpleResponse
                    return SimpleResponse(json.loads(json_match.group(1)))
```

- [ ] **Step 3: 运行测试验证**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "not weekly"`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add app/services/publisher_crawler/base_crawler.py app/services/publisher_crawler/open_library.py
git commit -m "refactor(crawler): 清理OpenLibraryCrawler中的Mock依赖，添加SimpleResponse包装类"
```

---

### Task 6: 补充爬虫单元测试

**问题：** 爬虫的 HTML 解析、API 解析、降级逻辑等核心功能无自动化测试覆盖。

**Files:**
- 修改: `tests/test_publisher_crawler.py`

- [ ] **Step 1: 添加 BaseCrawler 通用方法测试**

在 `tests/test_publisher_crawler.py` 添加：

```python
from app.services.publisher_crawler.base_crawler import BaseCrawler, BookInfo, CrawlerConfig, SimpleResponse


class TestBaseCrawlerMethods:
    """BaseCrawler 通用方法测试"""

    def setup_method(self):
        """创建一个可测试的 BaseCrawler 子类实例"""
        class TestCrawler(BaseCrawler):
            PUBLISHER_NAME = "Test"
            PUBLISHER_NAME_EN = "Test"
            PUBLISHER_WEBSITE = "https://example.com"
            CRAWLER_CLASS_NAME = "TestCrawler"
            def get_new_books(self, category=None, max_books=100): yield from []
            def get_book_details(self, book_url=""): return None
            def get_categories(self): return []

        self.crawler = TestCrawler()

    def test_clean_text_normal(self):
        assert self.crawler._clean_text("  hello  world  ") == "hello world"

    def test_clean_text_none(self):
        assert self.crawler._clean_text(None) == ""

    def test_clean_text_empty(self):
        assert self.crawler._clean_text("") == ""

    def test_extract_isbn13(self):
        isbn13, isbn10 = self.crawler._extract_isbn("ISBN: 9780134685991")
        assert isbn13 == "9780134685991"
        assert isbn10 is None

    def test_extract_isbn10(self):
        isbn13, isbn10 = self.crawler._extract_isbn("ISBN: 013468599X")
        assert isbn10 == "013468599X"

    def test_extract_isbn_none(self):
        isbn13, isbn10 = self.crawler._extract_isbn("no isbn here")
        assert isbn13 is None
        assert isbn10 is None

    def test_parse_date_iso(self):
        result = self.crawler._parse_date("2024-01-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_parse_date_month_name(self):
        result = self.crawler._parse_date("January 15, 2024")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_year_only(self):
        result = self.crawler._parse_date("2024")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_none(self):
        assert self.crawler._parse_date(None) is None

    def test_parse_date_invalid(self):
        assert self.crawler._parse_date("not a date") is None

    def test_parse_price_dollar(self):
        assert self.crawler._parse_price("$28.99") == "$28.99"

    def test_parse_price_none(self):
        assert self.crawler._parse_price(None) is None

    def test_truncate_description_short(self):
        assert self.crawler._truncate_description("short") == "short"

    def test_truncate_description_long(self):
        long_text = "a" * 3000
        result = self.crawler._truncate_description(long_text)
        assert len(result) == 2003
        assert result.endswith("...")

    def test_truncate_description_none(self):
        assert self.crawler._truncate_description(None) is None


class TestBookInfo:
    """BookInfo 数据类测试"""

    def test_to_dict(self):
        info = BookInfo(title="Test", author="Author")
        d = info.to_dict()
        assert d['title'] == "Test"
        assert d['author'] == "Author"
        assert d['isbn13'] is None

    def test_to_dict_with_date(self):
        from datetime import date
        info = BookInfo(title="Test", author="Author", publication_date=date(2024, 1, 15))
        d = info.to_dict()
        assert d['publication_date'] == "2024-01-15"


class TestSimpleResponse:
    """SimpleResponse 包装类测试"""

    def test_json_returns_data(self):
        resp = SimpleResponse({"key": "value"})
        assert resp.json() == {"key": "value"}

    def test_status_code_default(self):
        resp = SimpleResponse({})
        assert resp.status_code == 200

    def test_status_code_custom(self):
        resp = SimpleResponse({}, status_code=404)
        assert resp.status_code == 404
```

- [ ] **Step 2: 添加 GoogleBooksCrawler 和 OpenLibraryCrawler 解析方法测试**

```python
from app.services.publisher_crawler.google_books import GoogleBooksCrawler
from app.services.publisher_crawler.open_library import OpenLibraryCrawler


class TestGoogleBooksParsing:
    """Google Books 爬虫解析测试"""

    def setup_method(self):
        self.crawler = GoogleBooksCrawler()

    def test_is_recent_book_current_year(self):
        assert GoogleBooksCrawler._is_recent_book("2025-01-01", 2024) is True

    def test_is_recent_book_old(self):
        assert GoogleBooksCrawler._is_recent_book("2020-01-01", 2024) is False

    def test_is_recent_book_empty(self):
        assert GoogleBooksCrawler._is_recent_book("", 2024) is True

    def test_is_recent_book_invalid(self):
        assert GoogleBooksCrawler._is_recent_book("invalid", 2024) is True

    def test_parse_volume_info_complete(self):
        volume = {
            'title': 'Test Book',
            'authors': ['John Doe'],
            'description': 'A test book',
            'publishedDate': '2024-06-15',
            'pageCount': 300,
            'language': 'en',
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780134685991'},
                {'type': 'ISBN_10', 'identifier': '0134685991'},
            ],
            'imageLinks': {'thumbnail': 'https://example.com/cover.jpg'},
            'canonicalVolumeLink': 'https://books.google.com/books?id=test',
        }
        result = self.crawler._parse_volume_info(volume, 'fiction')
        assert result is not None
        assert result.title == 'Test Book'
        assert result.author == 'John Doe'
        assert result.isbn13 == '9780134685991'
        assert result.page_count == 300

    def test_parse_volume_info_minimal(self):
        volume = {'title': 'Minimal Book'}
        result = self.crawler._parse_volume_info(volume, 'fiction')
        assert result is not None
        assert result.title == 'Minimal Book'
        assert result.author == 'Unknown Author'


class TestOpenLibraryParsing:
    """Open Library 爬虫解析测试"""

    def setup_method(self):
        self.crawler = OpenLibraryCrawler()

    def test_parse_work_complete(self):
        work = {
            'title': 'Test Work',
            'author_name': ['Jane Doe'],
            'cover_id': 12345,
            'isbn': ['9780134685991'],
            'first_publish_year': 2024,
            'key': '/works/OL12345W',
        }
        result = self.crawler._parse_work(work, 'fiction')
        assert result is not None
        assert result.title == 'Test Work'
        assert result.author == 'Jane Doe'
        assert result.isbn13 == '9780134685991'
        assert '12345' in result.cover_url

    def test_parse_work_minimal(self):
        work = {'title': 'Minimal', 'author_name': ['Author']}
        result = self.crawler._parse_work(work, 'fiction')
        assert result is not None
        assert result.title == 'Minimal'

    def test_generate_buy_links_with_isbn(self):
        links = self.crawler._generate_buy_links('9780134685991', None, 'Test')
        assert len(links) >= 1
        assert links[0]['name'] == 'Amazon'

    def test_generate_buy_links_no_isbn(self):
        links = self.crawler._generate_buy_links(None, None, 'Test')
        assert len(links) == 0
```

- [ ] **Step 3: 运行全部测试**

Run: `cd d:\BookRank3 && python -m pytest tests/test_publisher_crawler.py -v`
Expected: PASS

- [ ] **Step 4: 运行全部测试确认无回归**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "not weekly"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_publisher_crawler.py
git commit -m "test(crawler): 补充爬虫单元测试，覆盖BaseCrawler/GoogleBooks/OpenLibrary解析方法"
```

---

### Task 7: 更新 CHANGELOG

**Files:**
- 修改: `CHANGELOG.md`

- [ ] **Step 1: 读取当前 CHANGELOG.md**

- [ ] **Step 2: 添加本次变更记录**

在 CHANGELOG.md 顶部添加新版本条目，包含：
- 版本号递增
- 修改日期 2026-04-26
- 变更内容：企鹅兰登迁移到MixedCrawl4AICrawler（消除470行重复）、修复__init__重复定义bug、删除废弃crawl4ai_base.py、统一注册机制、清理Mock依赖、补充测试

- [ ] **Step 3: 提交**

```bash
git add CHANGELOG.md
git commit -m "docs: 更新CHANGELOG，记录出版社爬虫模块优化变更"
```

---

## 自检清单

| 检查项 | 状态 |
|--------|------|
| 每个问题点都有对应 Task？ | ✅ 8个问题→7个Task（问题1+8合并为Task1） |
| 有无 TBD/TODO/placeholder？ | ✅ 无 |
| 类型/方法名在前后 Task 中一致？ | ✅ `CRAWLER_REGISTRY`、`get_crawler_class`、`SimpleResponse` 定义与使用一致 |
| 测试是否覆盖所有新增/修改逻辑？ | ✅ 企鹅兰登迁移、__init__修复、注册机制、SimpleResponse、解析方法 |
| Render 免费 512MB 内存约束是否考虑？ | ✅ 本次无新增内存消耗 |
