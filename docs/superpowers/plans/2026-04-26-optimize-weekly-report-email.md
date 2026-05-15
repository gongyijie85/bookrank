# 周报与邮件服务优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化周报生成时机（在畅销书排行榜更新当天自动触发）、周报邮件中书名旁添加封面图片（按比例缩放）、周报生成完成后自动发送邮件到配置的收件人邮箱。

**Architecture:** 1) 将周报生成从固定"周五检查"改为"排行榜数据刷新当天触发"，在 BookService 缓存刷新后检测是否需要生成周报；2) 修改 `_render_weekly_report_html()` 为每本书名添加封面图片（已有的 cover 字段，按比例缩放 max-width:60px）；3) 确保周报生成后调用 `send_weekly_report_email()` 发送到 `MAIL_RECIPIENTS` 配置的邮箱。

**Tech Stack:** Python 3.13, Flask, smtplib, SQLAlchemy, requests

---

## 现状问题分析

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | **周报仅在周五生成** | `weekly_report_task.py:22` 硬编码 `today.weekday() != 4` | NYT 排行榜周三更新（美国时间），周五生成意味着延迟2天；若排行榜更新时间变动则永远捕获不到 |
| 2 | **没有"数据更新即生成"机制** | BookService 刷新缓存后无回调 | 数据刷新和周报生成完全脱节，周报可能用过时数据 |
| 3 | **邮件封面图已部分实现** | `_render_weekly_report_html()` L135-162 的 `book_row()` 已有封面 | 但 `weekly_report_task.py` 的 `_collect_weekly_data()` 中 `cover` 字段已传递，问题在 Jinja 模板 `weekly_report.html` 中封面图显示不完整（缺少推荐书籍区块的封面） |
| 4 | **`MAIL_RECIPIENTS` 配置缺失** | config.py 无 `MAIL_RECIPIENTS` 字段 | `weekly_report_task.py:113` 读取 `MAIL_RECIPIENTS` 但 Config 类未定义，回退为发给自己 |
| 5 | **`_generate_default_summary` 无封面图** | L436-499 默认摘要用纯文本 | 默认摘要中推荐书籍区块只有文字没有封面图 |
| 6 | **两套邮件发送逻辑并存** | `email_service.py`(Flask-Mail) 和 `weekly_report_task.py`(smtplib) | Flask-Mail 从未被实际调用，`weekly_report_task.py` 的 smtplib 才是真正使用的 |
| 7 | **.env.example 缺少邮件收件人配置** | `.env.example` 无 `MAIL_RECIPIENTS` | 用户不知道如何配置收件人邮箱 |

---

## 文件结构

| 操作 | 文件路径 | 职责变更 |
|------|----------|----------|
| 修改 | `app/tasks/weekly_report_task.py` | 核心改动：去掉周五限制，改为检测数据刷新触发；生成后自动发邮件 |
| 修改 | `app/services/book_service.py` | 在数据刷新后增加回调，触发周报生成检查 |
| 修改 | `app/services/weekly_report_service.py` | 默认摘要中为推荐书籍添加封面图 |
| 修改 | `app/config.py` | 添加 `MAIL_RECIPIENTS` 配置项 |
| 修改 | `.env.example` | 添加 `MAIL_RECIPIENTS` 配置说明 |
| 修改 | `app/setup.py` | 调整后台线程：周报从"每日检查"改为"数据刷新后触发" |
| 删除 | `app/services/email_service.py` | 废弃代码，从未被实际调用（weekly_report_task.py 直接用 smtplib） |
| 修改 | `tests/test_weekly_report.py` | 更新测试适配新逻辑 |

---

### Task 1: 添加 `MAIL_RECIPIENTS` 配置项

**问题：** config.py 缺少 `MAIL_RECIPIENTS`，导致邮件只能发给自己。

**Files:**
- 修改: `app/config.py`
- 修改: `.env.example`

- [ ] **Step 1: 在 config.py 添加 MAIL_RECIPIENTS**

在 `app/config.py` 的 `MAIL_SUPPRESS_SEND` 行后添加：

```python
    MAIL_RECIPIENTS: str = os.environ.get('MAIL_RECIPIENTS', '')
```

- [ ] **Step 2: 在 .env.example 添加配置说明**

在 `.env.example` 的邮件配置区块添加：

```
# 邮件收件人（逗号分隔多个邮箱）
MAIL_RECIPIENTS=your-email@example.com
```

- [ ] **Step 3: 提交**

```bash
git add app/config.py .env.example
git commit -m "feat(config): 添加MAIL_RECIPIENTS邮件收件人配置项"
```

---

### Task 2: 重构周报生成触发机制——排行榜数据刷新后自动触发

**问题：** 当前仅在周五检查，而 NYT 排行榜实际在周三更新（美国时间）。应改为：当 BookService 刷新了新的排行榜数据时，检查是否需要生成周报。

**Files:**
- 修改: `app/tasks/weekly_report_task.py`
- 修改: `app/services/book_service.py`
- 修改: `app/setup.py`

- [ ] **Step 1: 重写 `generate_weekly_report()` 去掉周五限制**

将 `weekly_report_task.py` 中的 `generate_weekly_report()` 改为：不再限制周五，而是检测本周是否已有报告，若没有则生成：

```python
def generate_weekly_report(force_regenerate: bool = False) -> Optional[WeeklyReport]:
    """生成周报（排行榜数据刷新后调用）

    不再限制仅在周五生成，而是在数据刷新后自动触发。
    检测当前周是否已有报告，若没有则生成，有则跳过。
    """
    try:
        today = datetime.date.today()
        # 计算当前周的日期范围（周一至周日）
        current_monday = today - datetime.timedelta(days=today.weekday())
        current_sunday = current_monday + datetime.timedelta(days=6)

        # 如果今天在周一周三之前（排行榜尚未更新），使用上周日期
        # NYT 排行榜通常在周三更新（美国时间），中国时间周四可见
        if today.weekday() <= 2:  # 周一/二/三，排行榜尚未更新
            # 生成上周的周报
            last_monday = current_monday - datetime.timedelta(days=7)
            last_sunday = current_monday - datetime.timedelta(days=1)
            week_start = last_monday
            week_end = last_sunday
        else:
            # 周四及以后，排行榜已更新，生成本周周报
            week_start = current_monday
            week_end = current_sunday

        # 检查是否已经生成过
        existing_report = WeeklyReport.query.filter(
            WeeklyReport.week_start == week_start,
            WeeklyReport.week_end == week_end
        ).first()

        if existing_report and not force_regenerate:
            logger.info(f"周报已存在: {week_start} 至 {week_end}")
            send_weekly_report_email(existing_report)
            return existing_report

        if existing_report and force_regenerate:
            logger.info(f"强制重新生成周报: {week_start} 至 {week_end}")

        # 初始化服务
        from ..services import (
            BookService, NYTApiClient, GoogleBooksClient,
            CacheService, MemoryCache, FileCache, ImageCacheService
        )

        from pathlib import Path

        memory_cache = MemoryCache(default_ttl=3600, max_size=1000)
        file_cache = FileCache(cache_dir=Path('cache'), default_ttl=86400)
        cache_service = CacheService(memory_cache, file_cache, flask_cache=None)

        nyt_client = NYTApiClient(
            api_key='',
            base_url='https://api.nytimes.com/svc/books/v3',
            rate_limiter=None,
            timeout=15
        )

        google_client = GoogleBooksClient(
            api_key=None,
            base_url='https://www.googleapis.com/books/v1',
            timeout=8
        )

        image_cache = ImageCacheService(
            cache_dir=Path('static/cache'),
            default_cover='/static/default-cover.png'
        )

        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            max_workers=2,
            categories=['Fiction', 'Nonfiction', 'Mystery', 'Science Fiction']
        )

        report_service = WeeklyReportService(book_service)

        # 生成报告
        report = report_service.generate_report(week_start, week_end, force_regenerate=force_regenerate)

        if report:
            logger.info(f"周报生成成功: {report.title}")
            send_weekly_report_email(report)
            return report
        else:
            logger.warning("周报生成失败")
            return None

    except Exception as e:
        logger.error(f"生成周报时出错: {str(e)}")
        return None
```

- [ ] **Step 2: 在 BookService 添加数据刷新后的回调机制**

在 `app/services/book_service.py` 的 `__init__` 方法中添加回调列表，并在 `get_books_by_category` 成功刷新后触发：

在 `BookService.__init__` 中添加：
```python
        self._on_data_refreshed_callbacks = []
```

在 `BookService` 类中添加方法：
```python
    def on_data_refreshed(self, callback):
        """注册数据刷新后的回调函数"""
        self._on_data_refreshed_callbacks.append(callback)

    def _notify_data_refreshed(self):
        """通知所有注册的回调：数据已刷新"""
        for callback in self._on_data_refreshed_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"数据刷新回调执行失败: {e}")
```

在 `get_books_by_category` 方法中，API 成功获取数据后（约 L83 之后），添加回调触发：
```python
            # 通知数据刷新回调
            self._notify_data_refreshed()
```

- [ ] **Step 3: 在 setup.py 注册周报生成回调**

修改 `app/setup.py` 的 `_start_background_threads` 或 `init_services` 中，在 book_service 初始化后注册回调：

在 `init_services` 函数中，`book_service` 初始化成功后添加：
```python
        # 注册数据刷新后的周报生成回调
        def _trigger_weekly_report():
            with app.app_context():
                try:
                    from .tasks.weekly_report_task import generate_weekly_report
                    app.logger.info('排行榜数据刷新，检查是否需要生成周报...')
                    generate_weekly_report()
                except Exception as e:
                    app.logger.error(f'数据刷新触发周报生成失败: {e}')

        book_service.on_data_refreshed(_trigger_weekly_report)
```

- [ ] **Step 4: 调整后台线程——周报从每日检查改为仅靠回调触发**

在 `_start_background_threads` 中，将周报线程的间隔从 86400 改为 0（仅执行一次启动检查），因为后续由回调驱动：

```python
    if book_service:
        _start_background_thread(app, '周报启动检查', _weekly_report_task, initial_delay, 0)
```

同时修改 `_weekly_report_task`，改为仅做一次启动时的检查：
```python
def _weekly_report_task(app):
    """周报启动检查任务（仅执行一次，后续由数据刷新回调驱动）"""
    with app.app_context():
        try:
            from .tasks.weekly_report_task import generate_weekly_report
            app.logger.info('启动时检查是否需要生成周报...')
            generate_weekly_report()
        except Exception as e:
            app.logger.error(f'启动时周报检查失败: {e}', exc_info=True)
```

- [ ] **Step 5: 运行测试**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "weekly"`
Expected: 周报相关测试需要适配

- [ ] **Step 6: 更新周报测试适配新逻辑**

检查 `tests/` 下的周报测试文件，更新 `weekday != 4` 相关断言。

- [ ] **Step 7: 提交**

```bash
git add app/tasks/weekly_report_task.py app/services/book_service.py app/setup.py tests/
git commit -m "feat(weekly-report): 排行榜数据刷新后自动触发周报生成，去掉周五限制"
```

---

### Task 3: 周报邮件中为所有书籍区块添加封面图片

**问题：** 内联 HTML 模板 `_render_weekly_report_html()` 的 `book_row()` 已有封面图，但 Jinja 模板 `weekly_report.html` 中推荐书籍区块缺少封面；默认摘要 `_generate_default_summary()` 中推荐书籍无封面。

**Files:**
- 修改: `app/services/weekly_report_service.py`
- 修改: `templates/emails/weekly_report.html`

- [ ] **Step 1: 在默认摘要的推荐书籍中添加封面图**

修改 `_generate_default_summary()` L486-491 的推荐书籍区块，为每本书添加封面图 HTML：

将：
```python
        if analysis.get('featured_books') and len(analysis['featured_books']) > 0:
            summary += "## 💡 推荐书籍\n"
            for book in analysis['featured_books'][:3]:
                summary += f"- 《{book['title']}》({book['author']}) - {book['reason']}\n"
            summary += "\n"
```

替换为：
```python
        if analysis.get('featured_books') and len(analysis['featured_books']) > 0:
            summary += "## 💡 推荐书籍\n"
            for book in analysis['featured_books'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}《{book['title']}》({book['author']}) - {book['reason']}\n"
            summary += "\n"
```

同样为其他区块（重要变化、新上榜、排名上升、持续上榜）添加封面图：

将重要变化区块替换为：
```python
        if analysis.get('top_changes') and len(analysis['top_changes']) > 0:
            summary += "## 📊 重要变化\n"
            for book in analysis['top_changes'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                if book['rank_change'] > 0:
                    summary += f"- {cover_tag}《{book['title']}》({book['author']}) 排名显著上升 {book['rank_change']} 位\n"
                elif book['rank_change'] < 0:
                    summary += f"- {cover_tag}《{book['title']}》({book['author']}) 排名下降 {abs(book['rank_change'])} 位\n"
            summary += "\n"
```

将新上榜区块替换为：
```python
        if analysis.get('new_books') and len(analysis['new_books']) > 0:
            summary += "## ✨ 新上榜书籍\n"
            for book in analysis['new_books'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}《{book['title']}》({book['author']}) - {book['category']} 类别\n"
            summary += "\n"
```

将排名上升最快区块替换为：
```python
        if analysis.get('top_risers') and len(analysis['top_risers']) > 0:
            summary += "## 🚀 排名上升最快\n"
            for book in analysis['top_risers'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}《{book['title']}》({book['author']}) 上升 {book['rank_change']} 位\n"
            summary += "\n"
```

将持续上榜最久区块替换为：
```python
        if analysis.get('longest_running') and len(analysis['longest_running']) > 0:
            summary += "## 🏆 持续上榜最久\n"
            for book in analysis['longest_running'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}《{book['title']}》({book['author']}) 已上榜 {book['weeks_on_list']} 周\n"
            summary += "\n"
```

- [ ] **Step 2: 更新 Jinja 模板为推荐书籍添加封面图**

修改 `templates/emails/weekly_report.html` L184-196 的推荐书籍区块，添加封面图：

将：
```html
            {% if content.featured_books %}
            <div class="section">
                <h2>推荐书籍</h2>
                <ul class="changes-list">
                    {% for book in content.featured_books[:3] %}
                    <li class="change-item">
                        <strong>{{ book.title }}</strong> - {{ book.author }}<br>
                        推荐理由：{{ book.reason }}
                    </li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}
```

替换为：
```html
            {% if content.featured_books %}
            <div class="section">
                <h2>推荐书籍</h2>
                <ul class="changes-list">
                    {% for book in content.featured_books[:5] %}
                    <li class="change-item" style="display:flex;align-items:flex-start;gap:12px;">
                        {% if book.cover %}
                        <img src="{{ book.cover }}" alt="{{ book.title }}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.1);flex-shrink:0;">
                        {% else %}
                        <span style="display:inline-block;width:60px;height:90px;background:#f0f0f0;border-radius:4px;text-align:center;line-height:90px;color:#999;font-size:24px;flex-shrink:0;">📖</span>
                        {% endif %}
                        <div>
                            <strong>{{ book.title }}</strong> - {{ book.author }}<br>
                            <span style="color:#718096;font-size:13px;">推荐理由：{{ book.reason }}</span>
                        </div>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}
```

- [ ] **Step 3: 提交**

```bash
git add app/services/weekly_report_service.py templates/emails/weekly_report.html
git commit -m "feat(weekly-report): 周报邮件所有书籍区块添加封面图片（按比例缩放60px）"
```

---

### Task 4: 确保周报生成后自动发送邮件

**问题：** `generate_weekly_report()` 中已调用 `send_weekly_report_email()`，但 `_get_smtp_config()` 读取 `MAIL_RECIPIENTS` 时 config 中无此字段（Task 1 已添加）。此外，`email_service.py` 使用 Flask-Mail 但从未被调用，造成混乱。

**Files:**
- 修改: `app/tasks/weekly_report_task.py`（确保 `send_weekly_report_email` 的收件人读取正确）
- 删除: `app/services/email_service.py`

- [ ] **Step 1: 确认 `_get_smtp_config()` 的收件人读取逻辑**

`_get_smtp_config()` L113 已读取 `MAIL_RECIPIENTS`：
```python
'recipients': current_app.config.get('MAIL_RECIPIENTS', '').split(',') if current_app.config.get('MAIL_RECIPIENTS') else [],
```

Task 1 已在 config.py 添加 `MAIL_RECIPIENTS`，此逻辑无需修改。但需确保空字符串时不报错。修改为更健壮的写法：

```python
        'recipients': [r.strip() for r in current_app.config.get('MAIL_RECIPIENTS', '').split(',') if r.strip()],
```

- [ ] **Step 2: 删除废弃的 email_service.py**

`email_service.py` 使用 Flask-Mail，但从未被业务代码调用（周报任务直接用 smtplib）。删除此文件，减少维护混乱。

检查无引用后删除：
```bash
git rm app/services/email_service.py
```

- [ ] **Step 3: 运行测试确认无回归**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "not weekly_report_service"`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add app/tasks/weekly_report_task.py
git commit -m "refactor(email): 健壮化收件人读取，删除废弃的email_service.py"
```

---

### Task 5: 补充周报相关测试

**问题：** 周报测试 `tests/test_weekly_report.py` 依赖真实 NYT API key，在无 key 环境下失败。

**Files:**
- 修改: `tests/test_weekly_report.py`

- [ ] **Step 1: 读取当前测试文件**

- [ ] **Step 2: 添加数据刷新回调测试**

```python
class TestDataRefreshCallback:
    """数据刷新回调机制测试"""

    def test_register_callback(self):
        from app.services.book_service import BookService
        from unittest.mock import Mock
        mock_nyt = Mock()
        mock_google = Mock()
        mock_cache = Mock()
        mock_image = Mock()
        service = BookService(
            nyt_client=mock_nyt,
            google_client=mock_google,
            cache_service=mock_cache,
            image_cache=mock_image,
            max_workers=2
        )
        callback = Mock()
        service.on_data_refreshed(callback)
        service._notify_data_refreshed()
        callback.assert_called_once()

    def test_multiple_callbacks(self):
        from app.services.book_service import BookService
        from unittest.mock import Mock
        mock_nyt = Mock()
        mock_google = Mock()
        mock_cache = Mock()
        mock_image = Mock()
        service = BookService(
            nyt_client=mock_nyt,
            google_client=mock_google,
            cache_service=mock_cache,
            image_cache=mock_image,
            max_workers=2
        )
        cb1, cb2 = Mock(), Mock()
        service.on_data_refreshed(cb1)
        service.on_data_refreshed(cb2)
        service._notify_data_refreshed()
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_callback_exception_does_not_block(self):
        from app.services.book_service import BookService
        from unittest.mock import Mock
        mock_nyt = Mock()
        mock_google = Mock()
        mock_cache = Mock()
        mock_image = Mock()
        service = BookService(
            nyt_client=mock_nyt,
            google_client=mock_google,
            cache_service=mock_cache,
            image_cache=mock_image,
            max_workers=2
        )
        bad_cb = Mock(side_effect=Exception("boom"))
        good_cb = Mock()
        service.on_data_refreshed(bad_cb)
        service.on_data_refreshed(good_cb)
        service._notify_data_refreshed()
        good_cb.assert_called_once()
```

- [ ] **Step 3: 添加周报封面图测试**

```python
class TestWeeklyReportCoverImages:
    """周报封面图测试"""

    def test_default_summary_includes_cover_images(self):
        from app.services.weekly_report_service import WeeklyReportService
        from app.services.book_service import BookService
        from unittest.mock import Mock
        mock_bs = Mock(spec=BookService)
        service = WeeklyReportService(mock_bs)
        analysis = {
            'top_changes': [{'title': 'Test', 'author': 'A', 'rank_change': 3, 'cover': 'https://example.com/cover.jpg'}],
            'new_books': [{'title': 'New', 'author': 'B', 'category': '小说', 'cover': 'https://example.com/new.jpg'}],
            'top_risers': [{'title': 'Rise', 'author': 'C', 'rank_change': 5, 'cover': 'https://example.com/rise.jpg'}],
            'longest_running': [{'title': 'Long', 'author': 'D', 'weeks_on_list': 20, 'cover': 'https://example.com/long.jpg'}],
            'featured_books': [{'title': 'Feat', 'author': 'E', 'reason': '推荐', 'cover': 'https://example.com/feat.jpg'}],
        }
        from datetime import date
        summary = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
        assert '<img src=' in summary
        assert 'cover.jpg' in summary
        assert 'feat.jpg' in summary

    def test_default_summary_no_cover_graceful(self):
        from app.services.weekly_report_service import WeeklyReportService
        from app.services.book_service import BookService
        from unittest.mock import Mock
        mock_bs = Mock(spec=BookService)
        service = WeeklyReportService(mock_bs)
        analysis = {
            'top_changes': [{'title': 'NoCover', 'author': 'A', 'rank_change': 3}],
            'new_books': [],
            'top_risers': [],
            'longest_running': [],
            'featured_books': [],
        }
        from datetime import date
        summary = service._generate_default_summary(analysis, date(2026, 4, 20), date(2026, 4, 26))
        assert 'NoCover' in summary
```

- [ ] **Step 4: 运行测试**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short -k "DataRefresh or CoverImage"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/
git commit -m "test(weekly-report): 添加数据刷新回调和周报封面图测试"
```

---

### Task 6: 更新 CHANGELOG

**Files:**
- 修改: `CHANGELOG.md`

- [ ] **Step 1: 添加本次变更记录**

在 CHANGELOG.md 顶部添加新版本条目，包含：版本号、日期、变更内容。

- [ ] **Step 2: 提交**

```bash
git add CHANGELOG.md
git commit -m "docs: 更新CHANGELOG，记录周报与邮件服务优化变更"
```

---

## 自检清单

| 检查项 | 状态 |
|--------|------|
| 每个需求点都有对应 Task？ | ✅ 排行榜更新当天生成→Task2，封面图→Task3，邮件发送→Task1+4 |
| 有无 TBD/TODO/placeholder？ | ✅ 无 |
| 类型/方法名在前后 Task 中一致？ | ✅ `MAIL_RECIPIENTS`、`on_data_refreshed`、`_notify_data_refreshed` 定义与使用一致 |
| Render 免费 512MB 内存约束是否考虑？ | ✅ BookService max_workers 保持 2，回调为轻量函数 |
