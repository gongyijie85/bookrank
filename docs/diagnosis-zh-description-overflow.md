# 诊断报告：卡片 5 行简介在中文模式下「内容不全」

- **症状**：紧凑五列卡片的中文简介被 5 行截断，看起来「字看不到 / 内容不全」
- **诊断日期**：2026-09-17
- **结论**：**字号只是缓解，根因在数据侧** —— 这类书的 `description_zh` 不是译文，
  而是翻译模型把上下文里的书名/作者/榜单名**写成了一段图书介绍**（英文 73 字 → 中文 311 字）。
  根因**已确证并修复**（PR #246）。
- **状态**：字号已收一档并上线（PR #243）；翻译层已修（PR #246）；**存量数据回填未做**。

---

## 1. 量化：有多少书受影响

对生产 13 个分类逐榜取样（`automated`，经 `/api/category-books` 统计 `description_zh` 长度）：

| 分类 | 最长中文简介 | ≈行数 | 超 5 行的书 |
| --- | --- | --- | --- |
| series-books | **311 字** | 20.7 | 2/10 |
| hardcover-nonfiction | 208 字 | 13.9 | 4/15 |
| graphic-books-and-manga | 201 字 | 13.4 | 1/15 |
| young-adult-hardcover | 149 字 | 9.9 | 1/10 |
| hardcover-fiction | 115 字 | 7.7 | 3/15 |
| childrens-middle-grade-hardcover | 76 字 | 5.1 | 1/10 |
| 其余 7 个分类 | ≤ 67 字 | ≤ 4.5 | 0 |

**合计 13/165 本（约 8%）超过 5 行。** 静态语言包更严重：457 条有中文简介的条目里
**188 条（41%）超过 5 行**（中位数 57 字，p90 341 字，最长 759 字）—— 但其中绝大多数是
**忠实翻译的原始长宣传语**，并非注水，只是原文本就长。

浏览器实测（CDP，compact 视口 1100px，`hardcover-nonfiction`）：
`-webkit-line-clamp: 5` 生效，5 行能容纳约 100 字；需要 8.97 行的那本 208 字简介仍被截。

---

## 2. 根因（已确证）：`description_zh` 有时根本不是译文

### 2.1 症状

生产快照（`automated`，10 个分类逐榜取样 40 本有 en+zh 的书，中位数 46 字 / p90 112 / max 311）：

| 书 | description (en) | description_zh | 比例 |
| --- | --- | --- | --- |
| AWESOME FRIENDLY KID | 73 字符 | **311 字** | **4.26×** |
| WARRIORS: THE PROPHECIES BEG | 72 字符 | **201 字** | **2.79×** |
| AMERICAN SCOUNDREL | 109 字符 | 208 字 | 1.91× |
| THE KNAVE AND THE MOON | 123 字符 | 115 字 | 0.93× ← 正常 |

超长条目译文开头：

> 《超棒又友善的孩子》（AWESOME FRIENDLY KID）**由杰夫·金尼（Jeff Kinney）创作，
> 属于儿童与青少年系列**……

**书名、作者、榜单名全部出现在译文里，而这些信息一个都不在 73 字符的英文原文中。**
正常译文的字符数只有原文的 0.42 倍（中位数）——**中文字符数暴涨本身就是强信号。**

### 2.2 机制（代码级取证）

两个缺陷叠加：

**① 提示词把元信息当作「素材」交给模型** —— `app/services/zhipu_translation_service.py`
的 `_build_hunyuan_prompt`，`description` 分支原本是：

```python
'要求：… 采用上下文中的书名与术语并保持一致；…'
f'图书上下文：\n{book_context}\n\n待翻译简介：\n{text}'
```

而 `book_context` 由 `_CONTEXT_FIELDS` 渲染，包含 **出版社（publisher）、榜单类别（list_name）、
类别（category/category_name）、系列（series）**。指令一边说「不遗漏、不增添」，一边要求
「采用上下文中的书名与术语并保持一致」——短简介输入下，模型把这些**事实**当素材写进了译文。

> 注意：这与「模型不听话」无关，是提示词设计问题。上下文里除**书名与术语表**之外的部分，
> 对「简介/详情」而言只应是消歧用的背景。

**② 既有的质量校验只打 warning、并不拦截** —— `ZhipuTranslationService.translate()`：

```python
if not self._validate_translation(result, text):
    logger.warning(f'翻译质量校验失败(含污染标记)，将尝试后处理: {result[:100]}')
# ← 然后照样 return result，并写进 translation_cache
```

`_validate_translation` 只检查 `_DIRTY_MARKERS`（`书名：`/`作者：` 这类**标签前缀**）与
「是否等于原文」，而注水译文里并没有这些标签，因此**从未被拦下**，坏值直接进入缓存与语言包，
并通过缓存**自我固化**。

---

## 3. 已做的缓解（PR #243，已上线）

紧凑五列 `.card-desc` 字号 `12px → 11px`（行高 1.45、钳制 5 行不变）：

| 字号 | 每行约 | 5 行容量 |
| --- | --- | --- |
| 12px | 15 字 | ≈75 字 |
| **11px** | **16~17 字** | **≈100 字（+33%）** |

效果：`hardcover-nonfiction` 超 5 行的书从 4/15 降到 3/15；`trade-fiction-paperback`
本来就都在 5 行内。**对 100 字以上的文本无效** —— 208 字那本仍需 8.97 行。

---

## 4. 已做的修复（PR #246）

1. **提示词按字段裁剪上下文**（`_PROMPT_CONTEXT_FIELDS`）：`description` / `details` 只保留
   书名、作者、术语表；出版社/榜单/类别/系列不再进入提示词。**只对有实证问题的字段设限** ——
   书名翻译与自定义 `field_type` 保持完整上下文，不做无依据的行为改动。
   同时把「不得出现原文没有的任何事实」写成显式约束，并点名不许提及出版社/榜单/系列。
2. **`translate()` 加防线**：命中注水判定后**去掉上下文重译一次**；仍不可信则返回 `None`
   —— 宁可不翻译，也不把「模型自撰的介绍」写进缓存与语言包。
3. **缓存读取同样过滤**：旧缓存里的注水译文按「未命中」处理并重译，用新提示词覆盖同一个
   缓存键，**自愈**；不整体 bump `PROMPT_VERSION`（那会把没问题的缓存一并作废，代价过大）。
4. 判定收敛到 `api_helpers.is_inflated_translation`（与 `is_english_echo` /
   `is_non_substantive_details` 同处），两条规则互相独立：

   - 译文 ≥ 120 字符**且**超过原文 1.5 倍（阈值按语料标定：正常中位数 0.42×，注水样本 ≥1.91×）；
   - 上下文元信息（出版社/榜单/类别/系列）出现在译文、却没出现在原文。

---

## 5. 仍未做：存量数据回填

**已在库里的注水译文不会被 PR #246 清除**，因为 `_fill_missing` 只填**空**字段。

### 5.1 关键事实：仓库里的语言包是干净的，坏值只在生产 DB

对同一本书（`9781419788109` / AWESOME FRIENDLY KID）逐处比对（`engine-rendered`）：

| 来源 | 长度 | 内容 |
| --- | --- | --- |
| 仓库静态包 `static/data/book_language_pack.zh.json` | **36 字** | 罗利·杰斐逊记录了自己的生活故事和冒险经历。（适合9至12岁的读者阅读） |
| 生产 API 返回值（即生产 DB） | **311 字** | 《超棒又友善的孩子》（AWESOME FRIENDLY KID）由杰夫·金尼（Jeff Kinney）创作，属于儿童与青少年文学系列… |

水合优先级见 `app/services/book_language_pack.py:39`（docstring 原文）：
**DB metadata → 静态语言包 → 翻译缓存**，且 `_fill_missing` 只在字段为空时写入。
所以 **DB 里的 311 字把语言包里正确的 36 字遮住了**。

### 5.2 结论：清空 DB 即可，无需重新翻译

把 DB 里命中 `is_inflated_translation` 的 `description_zh` / `details_zh` 置 **NULL**，
下一次水合会自动回落到静态语言包里的正确译文 —— **零 API 调用**。

> 注：语言包内仍有 113/457 条超过 100 字，但抽样显示它们是**忠实翻译的原始长宣传语**
> （原文本就长），不是注水；清空判定用的是与注入同样的谓词，不会误伤这类条目。

后续路径：

1. **回填脚本**（进行中）：`scripts/backfill_inflated_translations.py`，默认 dry-run，
   `--apply` 才写库。
2. 卡片改取更短的字段来源，把长 `description_zh` 留给详情页。

> **仍需产品决策**：卡片的定位是「摘要 teaser」还是「尽量完整」。
> 若是 teaser，5 行截断本身不是 bug，问题只在「截断点被注水挤掉」；注水修好后，
> 剩下的超长条目就是**真实的原始长宣传语**，属于版式取舍而非缺陷。

---

## 6. 证据分级

| 内容 | 分级 |
| --- | --- |
| 各分类简介长度统计、行数测量、en/zh 比例 | `automated`（自写脚本 + CDP 测量） |
| 生产页面渲染结果、字号生效、生产 API 字段原文 | `engine-rendered` |
| 提示词原文、`_validate_translation` 只 warn 不拦的代码路径 | `engine-rendered`（源码原文） |
| 「模型把元信息当素材写进译文」的机制 | `automated` + `manual`：译文含原文没有的书名/作者/榜单名（可复现），机制解释为人工归纳 |
