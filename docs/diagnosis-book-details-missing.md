# 诊断报告：部分图书详情页「详细信息」整块消失

- **症状报告**：`https://bookrank-ckml.onrender.com/book/4?category=trade-fiction-paperback` 的「详细信息」标签不见了，只剩「图书简介」
- **诊断日期**：2026-09-17
- **结论**：不是渲染回归，是**数据链路**问题——`details` 字段里存的一直是占位串，而这本书连中文详情兜底都没有，于是模板把占位串归一化成空，标签整块消失。
- **状态**：代码已修（工作树内，未提交），回归测试已加，红/绿双向验证已完成。**尚未部署**。

---

## 1. 证据分级说明

| 分级 | 含义 |
| --- | --- |
| `automated` | 本机可复现的命令输出（脚本 / pytest / lint） |
| `engine-rendered` | 生产站点与生产 API 的真实响应 |
| `manual` | 人工判读、推断 |

---

## 2. 根因链（三段叠加，缺一不复现）

### 第 1 段：占位串被当成数据落库

`app/models/book.py:106-107`（修复前）

```python
description=book_data.get('description', 'No summary available.'),
details=supplement.get('details', 'No detailed description available.'),
```

抓取侧拿不到简介时会写回这些串，落库代码又把它们当**默认值**写进 `details` / `description`。
占位串在语义上等于 `NULL`，但它是一个**真值**。

`engine-rendered` 取证 —— 生产 `/api/public/book/9798890920461` 返回的入库数据：

```json
"description": "When a big quilting competition in Utah is announced, ...",
"details": "No detailed description available.",
"details_zh": null,
"language": "Unknown",
"page_count": "Unknown",
"publication_dt": "Unknown"
```

### 第 2 段：「有值即已补全」把自愈路径封死

`app/services/book_detail_service.py`（修复前）

```python
needs_details = bool(
    book.get('details')
    and book.get('details') != 'No detailed description available.'
    and not book.get('details_zh')
)
```

占位串让前半段为真、后半段为假 → `needs_details` **恒为假** → 这本书永远不会被重新补齐、翻译或存回。
占位串不只是「显示难看」，它**封死了修复入口**。

### 第 3 段：详情只有一个数据源，而它对这本书没有记录

`fetch_google_books_details()` 只查 Google Books。而 9798890920461《Stitched》（Eli McCann，Kirkus/Torrey House，2026-09-27 上市，weeks_on_list=1）是该库没有条目的独立出版新书。
项目的 `OpenLibraryClient` 一直只被获奖书目（`award_book_service`）用于抓封面，**详情页的兜底路径从未调用过它**。

`automated` 取证 —— Open Library 有这本书的完整简介（582 字符）：

```
https://openlibrary.org/search.json?q=isbn:9798890920461&fields=key
  -> /works/OL45900944W
https://openlibrary.org/works/OL45900944W.json
  -> description: "Betty Lou Dearden has been a member of the Ogden Quilter's Association
     for more than twenty years when it's announced that the biggest quilting competition
     in the country is coming to her small Utah town, …"   (582 字符)
```

---

## 3. 判定规则（把机制说清楚）

| `details_zh`（语言包 / BookMetadata） | `book.details` | 页面表现 |
| --- | --- | --- |
| 有值 | 占位串（被模板过滤） | 「详细信息」正常显示中文详情 |
| **缺失** | 占位串（被模板过滤） | **标签整块消失** ← 用户报告的这一本 |

`automated` 全分类扫描（`.debug/probe_details.py`，12 本书）：

```
#0   9781668236512   tab-details=True   details='No detailed description available.'
#1   9780593820254   tab-details=True   details='No detailed description available.'
...
#4   9798890920461   tab-details=False  details='No detailed description available.'
...
汇总: 12 本 | 有真实 details: 0 | 渲染出「详细信息」标签: 11
```

**波及范围比报告的大：该分类 12 本书的 `details` 字段 100% 是占位串。**
11 本之所以还看得见，只是因为静态语言包 `static/data/book_language_pack.zh.json` 里有 `details_zh`
（628 条中 198 条有 `details_zh`，`9798890920461` 不在包里）。

另有旁证：这批书 `language` / `page_count` / `publication_dt` 全部为 `Unknown`，
说明**生产上实时的 Google Books 富化整体没有生效**（原因未能从外部确证，见第 6 节）。

---

## 4. 修改内容

| 文件 | 改动 |
| --- | --- |
| `app/utils/api_helpers.py` | 新增占位串单一真相源：`_PLACEHOLDER_TEXTS` / `is_placeholder_text()` / `strip_placeholder()` |
| `app/models/book.py` | 落库边界改用 `strip_placeholder()`：占位串统一归一化成空串，不再伪装成「已有详情」 |
| `app/services/open_library_client.py` | 新增 `fetch_work_description_by_isbn()`：`search.json` → `works/<key>.json` 取 work 级简介；`_parse_book_data` 不再编造 `'No description available.'` |
| `app/utils/service_helpers.py` | 新增 `get_open_library_client()` / `get_or_create_open_library_client()` |
| `app/services/book_detail_service.py` | 新增详情富化入口 `enrich_book_details()`：Google Books 优先，无实质详情时回退 Open Library；入口处清理历史占位串；内联占位串比较统一改用判定函数 |
| `app/services/book_service.py` | `BookMetadata.details` 写入改用判定函数 |
| `app/routes/main.py` | 详情路由改调 `enrich_book_details`；`/api/book-details` 返回值先过 `strip_placeholder` |
| `tests/test_book_details_fallback.py` | **新增**根因侧回归锁（12 个用例） |
| `tests/test_open_library_client.py` | `test_no_description` 契约更新：无简介留空，不回填占位串 |

**设计取舍**：`enrich_book_details` 只负责把正文写进 `book['details']`，翻译与持久化仍交给紧随其后的
`merge_or_translate_book`（它已包含 details 的排队翻译 + `save_book_translation`）——避免同一段正文被排队翻译两次。
第 1 段的修复是第 3 段能生效的前提：`details` 不再是占位串，`needs_details` 才可能为真。

**命名**：详情富化入口从 `fetch_google_books_details` 改名为 `enrich_book_details`（它已不再只查 Google Books）。
路由层 20 处 patch 目标同步改名——`unittest.mock.patch` 目标是硬引用，改名会**响亮失败**而不是静默走网络。

---

## 5. 验证

### 5.1 红灯验证（修复确实在做功）

`automated`，`.debug/red_proof.py` 分两阶段把修复拆掉，确认测试各自会红：

| 阶段 | 拆掉什么 | 结果 |
| --- | --- | --- |
| A | 还原 `models/book.py` 落库边界 | `TestPlaceholderIsNotPersisted`：**2 failed** |
| B | 关闭 Open Library 兜底 | `TestEnrichBookDetailsFallback`：**1 failed**；`TestDetailPageShowsDetailsFromFallback`：**1 failed** |

反向断言同时成立：没有兜底源时，「详细信息」标签**确实**不出现 ——
证明上面那条不是恒真用例。（源文件在 `finally` 中自动还原，已验证还原成功。）

### 5.2 门禁

| 门禁 | 结果 |
| --- | --- |
| `ruff check` | All checks passed |
| `ruff format --check` | 232 files already formatted |
| `mypy app/` | Success: no issues found in 107 source files |
| `pytest tests/` | **2609 passed, 1 skipped, 0 failed**（63.9s） |
| 覆盖率 | 83.63%（门禁 ≥70） |

### 5.3 部署后验收（已完成，RED → GREEN）

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| 修复前 | `python .debug/probe_details.py trade-fiction-paperback 12` | `VERDICT: RED — 无任何图书渲染出详细信息`；`#4 tab-details=False` |
| 部署后 | 同上 | **`VERDICT: GREEN — 12/12 本都渲染出「详细信息」标签`**；`#4 tab-details=True` |

`automated`，`python .debug/verify_prod_details.py 4 trade-fiction-paperback`
直接读生产页面上面板的可见正文：

```
第 1 次加载 (tab-details: 有)   ISBN: 9798890920461
  面板正文: 贝蒂·卢·迪尔登（Betty Lou Dearden）已经是奥格登拼布协会的成员超过二十年了。
            这时，协会宣布全国最大的拼布比赛将来到她所在的犹他州小镇。…
            Show original (English)
            Betty Lou Dearden has been a member of the Ogden Quilter's Association …
  是否含占位串: 否
```

即：**Open Library 取到的英文简介 → 被翻译成中文并持久化 → 页面渲染中文详情，
英文原文保留在「查看英文原文」折叠块内**。用户报告的原始 URL 已恢复正常。

### 5.4 发布记录

- PR：**gongyijie85/bookrank#241** → squash 合并，main = `5b77259`
- CI（PR 上）：Ruff / mypy / ESLint / Unit Tests(1m44s) / i18n Drift / Dependency Audit / CodeQL **全绿**
- Deploy：`Deploy to Render & HuggingFace` 成功（含 `Deploy and verify Render revision` 与 HF Space 同步）
- 顺带发现（未处理）：GitHub 报 default branch 有 1 个高危依赖告警（`dependabot/72`）

---

## 6. 未决事项与风险

1. **生产 Google Books 富化整体失效**（`automated` 旁证：GB 来源字段全为 `Unknown`）。
   本机探测到 `429`，且 `quota_limit_value: "0"` / `quota_limit: defaultPerDayPerProject`
   （`engine-rendered`）。但本机是无 Key 匿名请求，**不能据此断定生产项目的配额状态**，
   需要你在 GCP 侧确认 Books API 是否启用 / Key 是否有效 / 配额是否被置 0。
   本次修复用 Open Library 兜底**绕过**了这个问题，但没有解决它。
2. **`openlibrary.org/api/books` 端点在本机返回 404**（连知名 ISBN 也 404，疑似本机出口限制）。
   `OpenLibraryClient.fetch_book_by_isbn()` 用的正是这个端点；新加的兜底方法改用
   `search.json` + `works/<key>.json`（已验证可达），不受影响。但获奖书目的封面/描述链路是否正常，值得单独复核。
3. **历史缓存**：`books_<category>` 缓存 TTL 24h，里面仍存着占位串。详情页兜底不受影响
   （它在渲染前就清洗了），但要让数据层彻底干净，可等缓存自然过期或强制刷新。
4. **占位串清单散落在 4 处**（`api_helpers` / `book_language_pack._PLACEHOLDERS` /
   `templates/book_detail.html` 的 `_detail_placeholders` / `scripts/backfill_book_titles._PLACEHOLDER_NOISE`）。
   本次只统一了 Python 侧两处，模板与脚本仍是各自维护 —— 建议后续收敛到单一真相源。

---

## 7. ⚠️ 独立于本次故障的 P0：`.git` 对象库被清空 + 一个已确证的 ref 写入环境缺陷

**这两件事与本 bug 无关，但在本次会话中被发现，必须单独告知。已于当日完成恢复。**

### 7.1 真实损伤：refs 目录没了，**对象库也空了**

| 检查 | 结果 |
| --- | --- |
| `.git/refs` 目录 | **不存在** → git 报 `fatal: not a git repository` |
| `.git/packed-refs` | 145 条 ref **一条没少**（heads 49 / remotes 58 / tags 6 / codex 2 / dsh-turn-rewind 30） |
| `.git/objects/pack/` | **只剩 2 个 `.idx`，`.pack` 全没了** |
| `.git/objects/` loose 目录 | 33 个目录、**0 个文件** |
| `.git/worktrees/` | 不存在（所有 worktree 的 gitdir 一并没了） |
| `.scratch/trash` | 没有它们 → 不是 safe-delete 回收机制所为 |

即：**refs 目录与对象数据库同时被清空**，`.idx` 留下而 `.pack` 消失。
会话开始时 `git log` 还可用 → 发生在会话期间；`.git/index`(11:19:53)、
`.git/objects`(11:20:24) 当时仍在被写入，提示有并发进程在操作该仓库（**未确证是哪一方**）。

### 7.2 恢复（已执行，工作树零丢失）

不要跟损坏状态缠斗 —— `git fetch --refetch` 会被 `packed-refs` 里的悬空 ref
（`refs/dsh-turn-rewind/v2/*`、`refs/codex/turn-diffs/*`，对象已不存在）卡成 `fatal: bad object`。
可行路径（已验证）：

1. 完整备份 `.git` → `.debug/git-backup-broken-20260917-114217/`（33 文件）
2. `git clone --no-checkout <remote> <tmp>`（对象齐全，pack 28.4 MB）
3. 移走旧 `.git`（**移动不删除**）→ `.debug/git-broken-inplace-20260917-114501/`
4. 装回克隆的 `.git`，`git config core.bare false` / `core.logallupdates true`
5. `git reset --mixed HEAD` —— **只重建 index，不动工作树任何文件**

结果：`git rev-parse HEAD` = `a49427b2`（正是丢失的 tip，远端已有），历史 0 丢失；
`git status --short` 恰好只剩本次修复的 11 个改动 + 5 个未跟踪项 → 证明工作树未丢东西。

### 7.3 新发现并已确证：**`refs/` 二级路径的 ref 写不进 D:\BookRank3**

- `git update-ref refs/heads/a/b <sha>` 与 `git fetch origin main:refs/remotes/a/b`
  **都返回成功、零报错，但目标文件根本不存在**；同样操作换扁平名
  （`refs/heads/ab`、`refs/remotes/ab`）则正常落盘。
- 已排除：**沙箱**（关闭沙箱复现）、**父目录缺失**（手工预建 `refs/heads/probe5` 后仍失败）
  → 目录能建，**二级子目录里的文件写不进**。疑似文件系统过滤驱动/路径守卫，未定位。
- **实际踩坑**：`git checkout -b fix/xxx` 静默得到一个「未出生」分支却不报错，
  随后的 `git commit` 变成 **root-commit（542 files / +145043，把整棵树提交）**。
  核对提交时务必 `git rev-parse HEAD^` 确认有父提交。
- **规避**：在本工作副本里**只用扁平分支名**（本次 PR 分支即
  `fix-book-details-fallback`）；`git branch --show-current` 之后确认
  `.git/refs/heads/<name>` 文件真的存在。需要嵌套分支名，请换路径重新克隆。
- 影响面：远端 62 个分支大多带 `/`，因此 `git fetch` 也不会为它们生成
  `origin/<name>` 跟踪 ref，`push -u` 的 upstream 追踪同样无效。
