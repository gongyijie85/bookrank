# BookRank 评审 P0 速修实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 2026-07-28 四维红蓝军评审报告中标记为 P0 的 4 项低成本高风险问题：桌面端 `/profile` 500、`/api/cron/` 限流豁免、"8 大国际文学奖项"文案与实际配置不符、`docs/项目状态报告.md` 中未经验证的用户画像数据。

**Architecture:** 4 个任务互相独立，可任意顺序执行、任意子集合并：Task 1/2 各自新增一个模板文件/调整一处中间件逻辑并各自可独立测试；Task 3/4 为纯文档修正，不涉及代码或测试运行。

**Tech Stack:** Flask 3.1 / Jinja2（Task 1），Python 限流中间件（Task 2），Markdown 文档（Task 3/4）

## Global Constraints

- Python 代码改动需通过 `pytest`、`ruff check .`、`mypy app/`（沿用 `pyproject.toml` 现有配置，不新增也不移除 override）。
- 提交信息格式：`type(scope): 描述`，与仓库现有 CHANGELOG/commit 风格一致；类型使用 `fix`/`docs`。
- Task 3、4 为纯 Markdown 文档修正，没有可运行的自动化测试；用 `grep` 核实修改前后的文本状态代替"写测试"步骤，保持同等的可验证性。
- 不在本计划范围内的事项（见文末"暂不规划"）：不要提前实现 ONIX/CSV 导出、不要改动出版社爬虫合规底座、不要改动移动端导航——这些都还卡在 `research/` 目录里团队自己未走完的 wayfinder 决策链上。

---

## 文件变更清单

| 文件 | 操作 | 变更内容 |
|------|------|----------|
| `templates/profile.html` | 新建 | 桌面版个人中心模板，复用 `favorites`/`search_history` 上下文 |
| `tests/test_mobile_routes.py` | 修改 | 新增 `TestDesktopProfileRoute` 测试类 |
| `app/__init__.py:380-407` | 修改 | `/api/cron/` 从"完全豁免限流"改为"独立、更宽松的限流器" |
| `app/config.py:73-74` | 修改 | 新增 `CRON_RATE_LIMIT` / `CRON_RATE_LIMIT_WINDOW` 配置项 |
| `.env.example` | 修改 | 补充 `CRON_RATE_LIMIT` / `CRON_RATE_LIMIT_WINDOW` 说明 |
| `tests/test_cron_routes.py` | 修改 | 新增 `TestCronRateLimit` 测试类 |
| `docs/项目说明文档.md:36` | 修改 | "8大国际文学奖项" → "7 大国际文学奖项" |
| `docs/项目状态报告.md:56-64` | 修改 | 用户画像表前加注"未经验证 + 已被 B 端定位取代"的说明 |

---

## Task 1: 修复桌面端 `/profile` 500

**背景**：`app/utils/template_resolver.py` 的 `render_adaptive()` 只做"移动端优先，缺失回退桌面版"的单向回退（第 23-29 行）。`app/routes/main.py:642` 的 `/profile` 路由渲染 `profile.html`，但 `templates/` 目录下只有 `templates/mobile/profile.html`，没有桌面版 `templates/profile.html`。桌面 UA 命中该路由时 `is_mobile()` 为 `False`，直接调用 `render_template('profile.html', ...)`，触发 `jinja2.TemplateNotFound`，被 `app/__init__.py:210` 的全局 500 handler 兜住，用户看到的是错误页而非个人中心。

**Files:**
- Create: `templates/profile.html`
- Modify: `tests/test_mobile_routes.py`（在文件末尾追加新测试类，紧邻现有 `TestMobileProfileRoute` 之后）

**Interfaces:**
- 消费：`main.profile` 视图传入的上下文 `favorites: list[dict]`（含 `title`/`author`/`isbn` 键，见 `app/routes/main.py:627-640`）、`search_history: list[dict]`（含 `keyword`/`result_count` 键）、`session_id: str`。
- 产出：无（叶子页面，不被其他任务消费）。

- [ ] **Step 1: 编写失败测试**

在 `tests/test_mobile_routes.py` 中 `class TestMobileProfileRoute` 代码块之后追加：

```python
class TestDesktopProfileRoute:
    """个人中心桌面端渲染"""

    def test_desktop_ua_renders_profile(self, client, db) -> None:
        """桌面端 UA 访问 /profile 应渲染桌面版个人中心，而非 500"""
        resp = client.get('/profile?lang=zh', headers={'User-Agent': DESKTOP_UA})
        assert resp.status_code == 200
        assert b'm-tabbar' not in resp.data  # 确认走的是桌面模板，不是移动模板
        assert '我的收藏'.encode() in resp.data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_mobile_routes.py::TestDesktopProfileRoute -v`
Expected: FAIL，`jinja2.exceptions.TemplateNotFound: profile.html`（或断言 `resp.status_code == 200` 失败，实际为 500）

- [ ] **Step 3: 新建桌面版模板**

创建 `templates/profile.html`：

```html
{% extends "base.html" %}

{% block og_title %}{{ _('个人中心') }} - BookRank{% endblock %}
{% block twitter_title %}{{ _('个人中心') }} - BookRank{% endblock %}

{% block title %}{{ _('个人中心') }} - BookRank{% endblock %}

{% block breadcrumbs %}
{% from '_breadcrumbs.html' import breadcrumbs %}
{{ breadcrumbs([
    {'label': _('首页'), 'url': url_for('main.index')},
    {'label': _('个人中心'), 'url': url_for('main.profile')}
], csp_nonce()) }}
{% endblock %}

{% block content %}
<div class="about-container">
    <section class="about-hero">
        <h1 class="page-title">
            <svg class="icon text-gold" width="28" height="28"><use href="#icon-book"/></svg>
            {{ _('个人中心') }}
        </h1>
        <p class="about-subtitle">{{ _('已收藏') }} {{ favorites|length }} {{ _('本') }}</p>
    </section>

    <section class="about-section">
        <h2 class="section-title">{{ _('我的收藏') }} ({{ favorites|length }})</h2>
        {% if favorites %}
        <ul class="data-sources">
            {% for fav in favorites %}
            <li class="source-card">
                <h3>{{ fav.title }}</h3>
                {% if fav.author %}<p>{{ fav.author }}</p>{% endif %}
            </li>
            {% endfor %}
        </ul>
        {% else %}
        <p class="about-text">{{ _('暂无收藏，浏览书籍时点击收藏按钮即可添加') }}</p>
        {% endif %}
    </section>

    <section class="about-section">
        <h2 class="section-title">{{ _('搜索历史') }} ({{ search_history|length }})</h2>
        {% if search_history %}
        <ul class="data-sources">
            {% for item in search_history %}
            <li class="source-card">
                <a href="/?search={{ item.keyword | urlencode }}">{{ item.keyword }}</a>
                {% if item.result_count %}<span>({{ item.result_count }})</span>{% endif %}
            </li>
            {% endfor %}
        </ul>
        {% else %}
        <p class="about-text">{{ _('暂无搜索历史') }}</p>
        {% endif %}
    </section>
</div>
{% endblock %}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_mobile_routes.py::TestDesktopProfileRoute -v`
Expected: PASS

- [ ] **Step 5: 跑一遍完整移动端测试确认无回归**

Run: `pytest tests/test_mobile_routes.py -v`
Expected: 全部 PASS（含原有 `TestMobileProfileRoute` 三个用例）

- [ ] **Step 6: Commit**

```bash
git add templates/profile.html tests/test_mobile_routes.py
git commit -m "fix(routes): add desktop profile template to stop 500 on /profile"
```

---

## Task 2: `/api/cron/` 重新纳入限流（而非完全豁免）

**背景**：`app/__init__.py:390` 的 `rate_limit_requests()` 把 `/api/cron/` 前缀路径直接排除在限流之外。该端点唯一的防护是 `app/routes/api/cron.py:_verify_cron_secret()` 的 Bearer token 恒定时间比较，一旦 `CRON_SECRET` 泄露（日志误打印、CI 变量配置错误等），攻击者可以无限速率调用 `/api/cron/trigger-weekly-report` 触发昂贵的周报生成任务。改为独立、更宽松的限流器（而不是直接套用 `API_RATE_LIMIT=100/60s` 的公开 API 限额），因为合法的外部调度器（GitHub Actions/Render cron）调用频率本身就很低，不需要和公开 API 共享额度，也不应该被完全豁免。

**Files:**
- Modify: `app/__init__.py:376-407`
- Modify: `app/config.py:73-74`
- Modify: `.env.example`
- Modify: `tests/test_cron_routes.py`（在文件末尾追加新测试类）

**Interfaces:**
- 消费：`app/utils/rate_limiter.py` 已有的 `get_rate_limiter(max_requests, window_seconds) -> IPRateLimiter`（按参数组合缓存实例，见该文件第 119-124 行）。
- 产出：无（中间件级改动，不被其他任务消费）。

- [ ] **Step 1: 编写失败测试**

在 `tests/test_cron_routes.py` 文件末尾追加（需要在文件顶部已有的 `from unittest.mock import patch` 基础上，新增一行 import）：

```python
from app.utils.rate_limiter import get_rate_limiter


class TestCronRateLimit:
    """cron 端点限流测试（此前 /api/cron/ 完全豁免限流，属安全缺口）"""

    def test_exceeding_cron_rate_limit_returns_429(self, client, app, cron_secret) -> None:
        """连续请求超过 CRON_RATE_LIMIT 后应返回 429，而非无限放行"""
        app.config['TESTING'] = False
        limit = app.config.get('CRON_RATE_LIMIT', 20)
        window = app.config.get('CRON_RATE_LIMIT_WINDOW', 60)
        # 复用与 app/__init__.py 相同的缓存 key 拿到同一限流器实例并清空历史，
        # 避免同一 pytest 会话内其它用例的残留调用计数影响本测试判断。
        get_rate_limiter(max_requests=limit, window_seconds=window).reset()

        headers = {'Authorization': f'Bearer {cron_secret}'}
        with patch('app.tasks.weekly_report_task.generate_weekly_report') as mock_generate:
            mock_generate.return_value = None
            for _ in range(limit):
                resp = client.get('/api/cron/trigger-weekly-report', headers=headers)
                assert resp.status_code == 200

            resp = client.get('/api/cron/trigger-weekly-report', headers=headers)
        assert resp.status_code == 429
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_cron_routes.py::TestCronRateLimit -v`
Expected: FAIL，最后一次请求返回 200 而非 429（因为当前 `/api/cron/` 完全豁免限流）

- [ ] **Step 3: 在 `app/config.py` 新增限流配置项**

在第 74 行 `API_RATE_LIMIT_WINDOW` 之后新增两行：

```python
    API_RATE_LIMIT: int = int(os.environ.get('API_RATE_LIMIT', 100))
    API_RATE_LIMIT_WINDOW: int = int(os.environ.get('API_RATE_LIMIT_WINDOW', 60))
    CRON_RATE_LIMIT: int = int(os.environ.get('CRON_RATE_LIMIT', 20))
    CRON_RATE_LIMIT_WINDOW: int = int(os.environ.get('CRON_RATE_LIMIT_WINDOW', 60))
```

- [ ] **Step 4: 修改 `app/__init__.py` 的限流中间件**

将第 376-407 行整体替换为：

```python
    rate_limiter = get_rate_limiter(
        max_requests=app.config.get('API_RATE_LIMIT', 60), window_seconds=app.config.get('API_RATE_LIMIT_WINDOW', 60)
    )
    cron_rate_limiter = get_rate_limiter(
        max_requests=app.config.get('CRON_RATE_LIMIT', 20),
        window_seconds=app.config.get('CRON_RATE_LIMIT_WINDOW', 60),
    )

    @app.before_request
    def rate_limit_requests() -> Response | None:
        from flask import current_app

        if current_app.config.get('TESTING'):
            return None

        if request.path.startswith('/static/') or request.path.startswith('/health/'):
            return None

        if request.path.startswith('/api/cron/'):
            client_ip = request.remote_addr or 'unknown'
            if not cron_rate_limiter.is_allowed(client_ip):
                retry_after = cron_rate_limiter.get_retry_after(client_ip)
                response = make_response(
                    {'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429
                )
                response.headers['Retry-After'] = str(retry_after)
                return response
            return None

        if not request.path.startswith('/api/'):
            return None

        excluded_paths = ['/api/csrf-token', '/api/health']
        if request.path in excluded_paths:
            return None

        client_ip = request.remote_addr or 'unknown'

        if not rate_limiter.is_allowed(client_ip):
            retry_after = rate_limiter.get_retry_after(client_ip)
            response = make_response({'success': False, 'message': 'Rate limit exceeded. Please try again later.'}, 429)
            response.headers['Retry-After'] = str(retry_after)
            return response

        return None
```

- [ ] **Step 5: 在 `.env.example` 补充说明**

在 `API_RATE_LIMIT_WINDOW=60` 那一行之后新增：

```
CRON_RATE_LIMIT=20
CRON_RATE_LIMIT_WINDOW=60
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_cron_routes.py -v`
Expected: 全部 PASS，含新增的 `TestCronRateLimit`

- [ ] **Step 7: 跑一遍限流相关全部测试确认无回归**

Run: `pytest tests/test_rate_limiter.py tests/test_cron_routes.py -v`
Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add app/__init__.py app/config.py .env.example tests/test_cron_routes.py
git commit -m "fix(security): rate-limit /api/cron/ instead of exempting it entirely"
```

---

## Task 3: 修正"8 大国际文学奖项"文案

**背景**：`app/services/wikidata_client.py` 的 `WikidataClient.AWARD_IDS` 只配置了 7 个奖项键（`nebula`/`hugo`/`booker`/`international_booker`/`pulitzer_fiction`/`edgar`/`nobel_literature`），但 `docs/项目说明文档.md:36` 写的是"整合纽约时报畅销书榜单 + 8大国际文学奖项"，数字与实际配置不符，是可被直接核对出的具体错误。

**Files:**
- Modify: `docs/项目说明文档.md:36`

**Interfaces:** 无（纯文档，不涉及代码接口）。

- [ ] **Step 1: 核实当前文本状态**

Run: `grep -n "8大国际文学奖项" docs/项目说明文档.md`
Expected: 输出 `36:| **数据聚合** | 整合纽约时报畅销书榜单 + 8大国际文学奖项 |`

- [ ] **Step 2: 修改文案**

将 `docs/项目说明文档.md` 第 36 行：

```markdown
| **数据聚合** | 整合纽约时报畅销书榜单 + 8大国际文学奖项 |
```

改为：

```markdown
| **数据聚合** | 整合纽约时报畅销书榜单 + 7 大国际文学奖项（诺贝尔文学奖/布克奖/国际布克奖/普利策奖/雨果奖/星云奖/爱伦·坡奖，见 `app/services/wikidata_client.py::WikidataClient.AWARD_IDS`） |
```

- [ ] **Step 3: 核实修改结果**

Run: `grep -n "7 大国际文学奖项\|8大国际文学奖项" docs/项目说明文档.md`
Expected: 只匹配到"7 大国际文学奖项"这一行，不再匹配"8大国际文学奖项"

- [ ] **Step 4: Commit**

```bash
git add docs/项目说明文档.md
git commit -m "docs: correct award count from 8 to actual 7 configured awards"
```

---

## Task 4: 标注用户画像数据未经验证

**背景**：`docs/项目状态报告.md:56-64` 的目标用户表给出精确到个位数的占比（"图书采购人员 35%"等），全仓库搜索不到任何问卷、埋点或访谈记录支撑这些数字。且该文档写于 2026-02-25，早于 `research/issue-45-resolution.md`（2026-07）确立的 B 端定位（核心用户为原版书销售公司）。不删除这段历史内容（保留可追溯性），但需要加注说明其性质，避免被误当作当前决策依据。

**Files:**
- Modify: `docs/项目状态报告.md`（在第 56 行 `### 1.3 目标用户` 标题之后、表格之前插入一段说明）

**Interfaces:** 无（纯文档）。

- [ ] **Step 1: 核实当前文本状态**

Run: `sed -n '56,65p' docs/项目状态报告.md`
Expected: 看到 `### 1.3 目标用户` 标题后直接是表格，中间没有任何免责说明。

- [ ] **Step 2: 插入说明**

在 `docs/项目状态报告.md` 第 56 行 `### 1.3 目标用户` 之后插入：

```markdown
### 1.3 目标用户

> ⚠️ **历史数据说明**：下表占比为 2026-02 早期假设性画像，未经用户调研、问卷或埋点数据验证。且该假设早于 2026-07 确立的 B 端战略定位——见
> [`research/issue-45-resolution.md`](../research/issue-45-resolution.md)：核心用户已明确为**原版书销售公司**（进口书商、英文原版书店、外文图书电商），
> 不再以普通读者为主。本表仅供历史参考，不应作为当前产品或资源分配决策的依据。

| 用户群体 | 占比 | 核心需求 |
```

（原表格其余行保持不变，紧接在 `| 用户群体 | 占比 | 核心需求 |` 之后。）

- [ ] **Step 3: 核实修改结果**

Run: `grep -n "历史数据说明" docs/项目状态报告.md`
Expected: 命中新插入的说明行

- [ ] **Step 4: Commit**

```bash
git add docs/项目状态报告.md
git commit -m "docs: flag stale unverified user-persona table in status report"
```

---

## 暂不规划的事项（评审 P1/P2，需先解决团队自己的决策阻塞）

以下事项**有意不在本计划中展开为详细任务**，因为它们各自卡在 `research/` 目录里尚未走完的 wayfinder 决策链上，提前写详细实施步骤等于绕过团队既定流程：

| 事项 | 为什么现在不写详细计划 |
|------|------------------------|
| ONIX 3.0 导出器 / 多平台 CSV 模板 | `research/map-body.md` 显示字段映射方案在单独的 issue #49，尚未创建/研究；`research/issue-51-body.md` 也在问"是否与 #49 合并推进"，尚无定论 |
| 出版社爬虫 → Open Library/Wikidata 合规底座迁移 | 技术方案见 `research/map-body.md` "Not yet specified"：数据底座迁移的详细技术方案在单独的 issue #50，尚未创建/研究 |
| 移动端补齐新书速递/周报入口、导航层级调整 | `research/ia-map-body.md`（issue #55 地图）主导航/栏目优先级的问题链 #56-#65 **全部尚未回答**，属于团队正在进行中的决策过程，不应在此提前拍板 |
| 爬虫选择器健康检查 + 告警 | 依赖上面"合规底座迁移"先决定是否还要继续维护现有爬虫，避免重复投入 |
| `quality_score` 字段启用 / 术语表处理 | 需要先决定翻译质量的验收口径（人工抽样比例、启发式规则设计），属于产品决策而非纯技术任务 |

这些事项的下一步不是"写代码"，而是"把对应的 research/ 问题链走完"——见 `research/ia-map-body.md`（issue #55）和 `research/map-body.md`（issue #41）的 "Not yet specified" 部分。走完之后回来找我，我可以照本计划同样的格式为其中任意一项单独出一份实施计划。
