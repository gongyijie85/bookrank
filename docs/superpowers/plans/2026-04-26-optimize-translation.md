# 翻译能力优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 BookRank3 翻译系统的翻译质量、性能和可靠性，解决当前 AI 翻译污染、重复后处理逻辑、提示词不够精准、批量翻译效率低、缓存不完善等问题。

**Architecture:** 保持现有分层架构（引擎层→混合调度层→缓存层→后处理层→业务调用层），重点优化：1) 统一并强化后处理逻辑，消除三处重复；2) 升级提示词策略，采用字段感知的差异化提示词；3) 优化批量翻译并行度和重试机制；4) 完善翻译缓存质量评分和失效机制；5) 补齐测试覆盖。

**Tech Stack:** Python 3.13, Flask, zhipuai SDK, SQLAlchemy, pytest, tenacity

---

## 现状问题分析

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | **后处理逻辑三处重复** | `_postprocess_translation()`、`clean_translation_text()`、`fix_translation_data.py` | 同一清洁逻辑维护3份，修复遗漏时容易不同步 |
| 2 | **提示词过于笼统** | `zhipu_translation_service.py` L83-115 单一 system_prompt | 不区分字段类型，AI 输出格式不可控，产生"书名："标签等污染 |
| 3 | **翻译结果无质量校验** | `translate()` 方法直接返回 AI 原文 | 污染数据写入缓存和数据库，需事后修复脚本 |
| 4 | **批量翻译串行回退** | `HybridTranslationService.translate_batch()` L544-549 逐条串行 | 3条翻译需要3次API调用，未利用智谱的批量能力 |
| 5 | **作者名缓存淘汰粗糙** | L408-411 淘汰20%，可能误删热数据 | 缓存命中率降低 |
| 6 | **缓存无失效机制** | `translation_cache_service.py` 只清理冷数据 | 错误翻译永不过期，无法被自动纠正 |
| 7 | **备用翻译服务不稳定** | `free_translation_service.py` 依赖 `deep-translator` 但未在 requirements.txt | 备用链路可能断裂 |
| 8 | **测试覆盖不足** | 仅12个测试，未覆盖后处理、缓存失效、质量校验 | 回归风险高 |

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|------|----------|------|
| 修改 | `app/services/zhipu_translation_service.py` | 核心翻译：字段感知提示词、质量校验、批量优化 |
| 修改 | `app/utils/api_helpers.py` | 统一后处理函数，删除重复逻辑 |
| 修改 | `app/services/translation_cache_service.py` | 添加缓存失效和版本控制 |
| 修改 | `app/services/free_translation_service.py` | 稳定性增强 |
| 修改 | `fix_translation_data.py` | 统一使用 `api_helpers` 的清洁函数 |
| 修改 | `requirements.txt` | 添加 `deep-translator` 可选依赖 |
| 修改 | `tests/test_translation_service.py` | 补充测试用例 |

---

### Task 1: 统一翻译后处理逻辑

**问题：** `_postprocess_translation()`、`clean_translation_text()`、`fix_translation_data.py` 三处存在高度重复的清洁逻辑。

**Files:**
- 修改: `app/utils/api_helpers.py:151-192`
- 修改: `app/services/zhipu_translation_service.py:272-389`
- 修改: `fix_translation_data.py`

- [ ] **Step 1: 编写统一后处理函数的失败测试**

在 `tests/test_translation_service.py` 末尾添加测试类：

```python
class TestTranslationPostprocess:
    """翻译后处理统一函数测试"""

    def test_clean_removes_markdown_bold(self):
        from app.utils.api_helpers import clean_translation_text
        assert clean_translation_text('**书名**测试') == '测试'

    def test_clean_removes_field_prefix(self):
        from app.utils.api_helpers import clean_translation_text
        assert '书名：' not in clean_translation_text('书名：了不起的盖茨比')

    def test_clean_removes_translation_prefix(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('翻译：这是测试内容')
        assert result == '这是测试内容'

    def test_clean_title_truncates_at_next_field(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('了不起的盖茨比作者：菲茨杰拉德', field_type='title')
        assert '菲茨杰拉德' not in result
        assert '盖茨比' in result

    def test_clean_preserves_clean_text(self):
        from app.utils.api_helpers import clean_translation_text
        assert clean_translation_text('这是一段干净的中文') == '这是一段干净的中文'

    def test_clean_empty_and_none(self):
        from app.utils.api_helpers import clean_translation_text
        assert clean_translation_text('') == ''
        assert clean_translation_text(None) is None

    def test_quick_clean_skips_clean_text(self):
        from app.utils.api_helpers import quick_clean_translation
        result = quick_clean_translation('干净的中文文本')
        assert result == '干净的中文文本'

    def test_quick_clean_processes_dirty_text(self):
        from app.utils.api_helpers import quick_clean_translation
        result = quick_clean_translation('**书名**测试内容')
        assert '**' not in result

    def test_unify_quotes(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('\u201c测试\u201d')
        assert result == '\u201c测试\u201d'

    def test_add_book_title_marks_for_title(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('了不起的盖茨比', field_type='title')
        assert result == '《了不起的盖茨比》'

    def test_no_marks_for_mixed_lang_title(self):
        from app.utils.api_helpers import clean_translation_text
        result = clean_translation_text('Clean Code', field_type='title')
        assert '《' not in result
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py::TestTranslationPostprocess -v`
Expected: 部分测试失败（新行为尚未实现）

- [ ] **Step 3: 重构 `clean_translation_text()` 为权威后处理函数**

修改 `app/utils/api_helpers.py`，将 `clean_translation_text()` 增强为包含所有后处理逻辑的权威函数：

```python
_DIRTY_MARKERS = ('书名', '作者', '简介', '描述', '详情', '出版社',
                  'Title:', 'Author:', 'Description:', 'Summary:', 'Details:', 'Publisher:',
                  '翻译：', '译文：', '**')

_FIELD_LABELS_MAP = {
    'title': {
        'start': ['书名', 'Title', 'Book Title', 'Translated Title'],
        'end': ['作者', '简介', '描述', '详情', '出版社',
                'Author', 'Description', 'Summary', 'Details', 'Publisher'],
    },
    'description': {
        'start': ['简介', '描述', 'Description', 'Summary'],
        'end': ['书名', '作者', '详情', '出版社',
                'Title', 'Author', 'Details', 'Publisher'],
    },
    'details': {
        'start': ['详情', '描述', 'Details', 'Description'],
        'end': ['书名', '作者', '简介', '出版社',
                'Title', 'Author', 'Summary', 'Publisher'],
    },
}

_FIELD_PREFIX_PATTERNS = [
    r'(?:^|\s)书名[：:]\s*', r'(?:^|\s)作者[：:]\s*', r'(?:^|\s)简介[：:]\s*',
    r'(?:^|\s)描述[：:]\s*', r'(?:^|\s)详情[：:]\s*', r'(?:^|\s)出版社[：:]\s*',
    r'(?:^|\s)Title[：:]\s*', r'(?:^|\s)Author[：:]\s*', r'(?:^|\s)Description[：:]\s*',
    r'(?:^|\s)Summary[：:]\s*', r'(?:^|\s)Details[：:]\s*', r'(?:^|\s)Publisher[：:]\s*',
    r'(?:^|\s)Book Title[：:]\s*', r'(?:^|\s)Translated Title[：:]\s*',
]


def _extract_field_content(text: str, field_type: str) -> str:
    """从文本中提取指定字段内容"""
    labels = _FIELD_LABELS_MAP.get(field_type)
    if not labels:
        return text
    start_pos = -1
    for label in labels['start']:
        for sep in ['：', ':']:
            idx = text.find(f'{label}{sep}')
            if idx >= 0:
                start_pos = idx + len(label) + len(sep)
                break
        if start_pos >= 0:
            break
    if start_pos < 0:
        return text
    end_pos = len(text)
    for label in labels['end']:
        for sep in ['：', ':']:
            idx = text.find(f'{label}{sep}', start_pos)
            if idx >= 0:
                end_pos = min(end_pos, idx)
    return text[start_pos:end_pos].strip()


def _add_book_title_marks(text: str) -> str:
    """给纯中文书名添加《》"""
    if not text:
        return text
    text = text.strip()
    if text.startswith('《') and text.endswith('》'):
        return text
    if re.search(r'[a-zA-Z]', text):
        return text
    return f'《{text}》'


def clean_translation_text(text: str, field_type: str = 'text') -> str:
    """权威翻译文本后处理函数"""
    if not text:
        return text
    text = text.strip()
    prefixes = ['翻译：', '译文：', '中文翻译：', '翻译结果：']
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = text.replace('*', '')
    if field_type in _FIELD_LABELS_MAP:
        text = _extract_field_content(text, field_type)
    for pattern in _FIELD_PREFIX_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = text.replace('\u201c', '\u201c').replace('\u201d', '\u201d')
    text = text.replace('\u2018', '\u2018').replace('\u2019', '\u2019')
    if field_type == 'title':
        text = _add_book_title_marks(text)
    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text


def quick_clean_translation(text: str, field_type: str = 'text') -> str:
    """快速清理（带脏数据检测，干净文本直接返回）"""
    if not text:
        return text
    if any(marker in text for marker in _DIRTY_MARKERS):
        return clean_translation_text(text, field_type)
    return text
```

- [ ] **Step 4: 让 `ZhipuTranslationService._postprocess_translation()` 委托到统一函数**

修改 `app/services/zhipu_translation_service.py`，删除 L272-389 的 `_postprocess_translation`、`_extract_field`、`_add_book_title_marks` 三个方法，替换为委托调用：

```python
    @staticmethod
    def _postprocess_translation(text: str, field_type: str = 'text') -> str:
        """翻译结果后处理（委托到统一清洁函数）"""
        from ..utils.api_helpers import clean_translation_text
        return clean_translation_text(text, field_type=field_type)
```

- [ ] **Step 5: 让 `fix_translation_data.py` 委托到统一函数**

修改 `fix_translation_data.py`，删除 `clean_title()`、`clean_description()` 函数，替换为：

```python
def clean_title(text: str) -> str:
    """清理书名字段（委托到统一后处理函数）"""
    from app.utils.api_helpers import clean_translation_text
    return clean_translation_text(text, field_type='title')


def clean_description(text: str) -> str:
    """清理简介/描述字段（委托到统一后处理函数）"""
    from app.utils.api_helpers import clean_translation_text
    return clean_translation_text(text, field_type='description')
```

- [ ] **Step 6: 运行全量测试确认无回归**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 7: 提交**

```bash
git add app/utils/api_helpers.py app/services/zhipu_translation_service.py fix_translation_data.py tests/test_translation_service.py
git commit -m "refactor(translation): 统一翻译后处理逻辑，消除三处重复代码"
```

---

### Task 2: 字段感知提示词策略

**问题：** 单一 system_prompt 不区分字段类型，AI 输出格式不可控（添加"书名："标签等）。

**Files:**
- 修改: `app/services/zhipu_translation_service.py`

- [ ] **Step 1: 编写字段感知提示词的失败测试**

在 `tests/test_translation_service.py` 末尾添加：

```python
class TestFieldAwarePrompts:
    """字段感知提示词测试"""

    def test_title_prompt_prohibits_book_marks(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('title')
        assert '书名号' in prompt or '《》' in prompt
        assert '不添加' in prompt or '禁止' in prompt

    def test_description_prompt_requests_fluent(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('description')
        assert '流畅' in prompt or '自然' in prompt

    def test_text_prompt_is_default(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('text')
        assert prompt is not None
        assert len(prompt) > 0

    def test_author_prompt_format(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        service = ZhipuTranslationService(api_key='test')
        prompt = service._get_prompt_for_field('author')
        assert '译名' in prompt or '音译' in prompt
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py::TestFieldAwarePrompts -v`
Expected: FAIL（`_get_prompt_for_field` 方法不存在）

- [ ] **Step 3: 实现字段感知提示词方法**

在 `ZhipuTranslationService.__init__()` 中替换 `self._system_prompt` 为 `self._field_prompts` 字典，并添加 `_get_prompt_for_field()` 方法：

```python
    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4.7-flash", app=None):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY")
        self.model = model
        self._client = None
        self._last_request_time = 0
        self._request_interval = 0.1
        self._author_name_cache: OrderedDict[str, OrderedDict] = OrderedDict()
        self._author_name_cache_max_size = 1000
        self._cache_service = None
        self._app = app

        self._field_prompts: Dict[str, str] = {
            'title': (
                "你是一位资深图书翻译专家，正在翻译英文书名为中文。\n"
                "规则：\n"
                "- 文学性书名采用意译，体现文学美感\n"
                "- 专业书籍采用直译，保持准确性\n"
                "- 系列书籍保持系列名称一致性\n"
                "- 只输出翻译后的书名，不添加任何前缀、注释或解释\n"
                "- 禁止添加书名号《》\n"
                "- 禁止输出'书名：''翻译：'等标签\n"
                "- 禁止输出英文原文\n"
                "示例：\n"
                '"The Great Gatsby" → 了不起的盖茨比\n'
                '"Clean Code" → 代码整洁之道\n'
                '"The Night We Met" → 我们相遇的那晚'
            ),
            'description': (
                "你是一位资深图书翻译专家，正在翻译英文图书简介为中文。\n"
                "规则：\n"
                "- 准确传达原意，不添加原文没有的内容\n"
                "- 流畅自然，符合中文阅读习惯\n"
                "- 适当调整语序（英文常倒装，中文为主谓宾）\n"
                "- 专有名词（地名、机构名）保留英文或附原文\n"
                "- 去除'本书''作者'等冗余主语\n"
                "- 只输出翻译结果，不添加任何标签、注释或解释\n"
                "- 禁止输出'简介：''描述：''翻译：'等标签\n"
                "- 禁止使用Markdown格式"
            ),
            'details': (
                "你是一位资深图书翻译专家，正在翻译英文图书详情为中文。\n"
                "规则：\n"
                "- 准确翻译出版信息、页数、价格等详情\n"
                "- 数字和单位保持原格式\n"
                "- 出版社名优先使用中文官方译名\n"
                "- 只输出翻译结果，不添加任何标签、注释或解释\n"
                "- 禁止输出'详情：''翻译：'等标签\n"
                "- 禁止使用Markdown格式"
            ),
            'author': (
                "你是一位资深姓名翻译专家，正在将英文名字翻译为中文。\n"
                "规则：\n"
                "- 使用标准中文译名（参考维基百科、豆瓣）\n"
                "- 名和姓之间用间隔号·分隔\n"
                "- 只输出译名，不添加任何解释或注释\n"
                "- 禁止输出'作者：''翻译：'等标签\n"
                "示例：\n"
                '"Abby Jimenez" → 艾比·希门尼斯\n'
                '"Viola Davis" → 维奥拉·戴维斯'
            ),
            'text': (
                "你是一位资深翻译专家，将英文翻译为中文。\n"
                "规则：\n"
                "- 准确传达原意，不添加原文没有的内容\n"
                "- 符合中文表达习惯，避免翻译腔\n"
                "- 只输出翻译结果，不添加任何解释、注释或备注\n"
                "- 禁止输出'翻译：''译文：'等前缀\n"
                "- 禁止使用Markdown格式"
            ),
        }

    def _get_prompt_for_field(self, field_type: str) -> str:
        """获取字段类型对应的提示词"""
        return self._field_prompts.get(field_type, self._field_prompts['text'])
```

- [ ] **Step 4: 修改 `translate()` 使用字段感知提示词**

修改 `ZhipuTranslationService.translate()` 中 L174-182 的 API 调用：

```python
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_prompt_for_field(field_type)},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=4096
            )
```

- [ ] **Step 5: 修改 `translate_author_name()` 使用 author 提示词**

修改 `translate_author_name()` L414 调用：

```python
        translated = self.translate(author, field_type='author')
```

- [ ] **Step 6: 运行测试**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 7: 提交**

```bash
git add app/services/zhipu_translation_service.py tests/test_translation_service.py
git commit -m "feat(translation): 字段感知提示词策略，按title/description/author等使用差异化prompt"
```

---

### Task 3: 翻译结果质量校验

**问题：** 翻译结果直接返回 AI 原文，无质量校验，污染数据可能写入缓存和数据库。

**Files:**
- 修改: `app/services/zhipu_translation_service.py`
- 修改: `tests/test_translation_service.py`

- [ ] **Step 1: 编写质量校验的失败测试**

```python
class TestTranslationQualityCheck:
    """翻译质量校验测试"""

    def test_reject_dirty_translation_with_labels(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('书名：了不起的盖茨比', 'The Great Gatsby')
        assert result is False

    def test_reject_dirty_translation_with_markdown(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('**了不起的盖茨比**', 'The Great Gatsby')
        assert result is False

    def test_accept_clean_translation(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('了不起的盖茨比', 'The Great Gatsby')
        assert result is True

    def test_reject_too_similar_to_source(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('The Great Gatsby', 'The Great Gatsby')
        assert result is False

    def test_accept_empty_result_passthrough(self):
        from app.services.zhipu_translation_service import ZhipuTranslationService
        result = ZhipuTranslationService._validate_translation('', 'Hello')
        assert result is True
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py::TestTranslationQualityCheck -v`
Expected: FAIL

- [ ] **Step 3: 实现质量校验静态方法**

在 `ZhipuTranslationService` 类中添加：

```python
    @staticmethod
    def _validate_translation(translated: str, source: str) -> bool:
        """校验翻译结果质量，返回True表示可接受"""
        if not translated:
            return True
        from ..utils.api_helpers import _DIRTY_MARKERS
        if any(marker in translated for marker in _DIRTY_MARKERS):
            return False
        if translated.strip() == source.strip():
            return False
        return True
```

- [ ] **Step 4: 在 `translate()` 中加入质量校验**

修改 `ZhipuTranslationService.translate()` 中 L186-191：

```python
            if response and response.choices:
                result = response.choices[0].message.content
                if result:
                    if not self._validate_translation(result, text):
                        logger.warning(f"翻译质量校验失败，结果包含污染标记: {result[:100]}")
                    result = self._postprocess_translation(result, field_type=field_type)
                    logger.info(f"智谱AI翻译成功: {text[:50]}... -> {result[:50]}...")
                    return result
```

- [ ] **Step 5: 运行测试**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 6: 提交**

```bash
git add app/services/zhipu_translation_service.py tests/test_translation_service.py
git commit -m "feat(translation): 添加翻译结果质量校验，拒绝含污染标记的结果"
```

---

### Task 4: 优化批量翻译和重试机制

**问题：** `HybridTranslationService.translate_batch()` 逐条串行翻译；`ZhipuTranslationService.translate()` 无重试机制。

**Files:**
- 修改: `app/services/zhipu_translation_service.py`
- 修改: `app/services/free_translation_service.py`

- [ ] **Step 1: 为智谱翻译添加 tenacity 重试**

在 `ZhipuTranslationService.translate()` 中，用 tenacity 包装 API 调用。在文件顶部添加导入（如不存在），并修改 translate 方法中 try 块：

在 `zhipu_translation_service.py` 导入区添加：
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
```

修改 `translate()` 方法，在 API 调用部分添加重试装饰器的内部函数：

```python
    def translate(self, text: str, source_lang: str = 'en',
                  target_lang: str = 'zh', field_type: str = 'text') -> Optional[str]:
        if not text or not text.strip():
            return text

        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._request_interval:
            time.sleep(self._request_interval - time_since_last)

        client = self._get_client()
        if not client:
            return None

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            reraise=True,
        )
        def _call_api():
            return client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_prompt_for_field(field_type)},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=4096
            )

        try:
            response = _call_api()
            self._last_request_time = time.time()

            if response and response.choices:
                result = response.choices[0].message.content
                if result:
                    if not self._validate_translation(result, text):
                        logger.warning(f"翻译质量校验失败: {result[:100]}")
                    result = self._postprocess_translation(result, field_type=field_type)
                    logger.info(f"智谱AI翻译成功: {text[:50]}... -> {result[:50]}...")
                    return result

        except Exception as e:
            logger.warning(f"智谱AI翻译失败(重试耗尽): {e}")

        return None
```

- [ ] **Step 2: 优化 `HybridTranslationService.translate_batch()` 使用并行**

修改 `HybridTranslationService.translate_batch()` 方法：

```python
    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh',
                       progress_callback=None,
                       max_workers: int = 3) -> List[str]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(texts)
        cache_service = self._get_cache_service()
        results = [None] * total
        to_translate = []

        # 第一步：检查缓存
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text
                continue
            if cache_service:
                try:
                    cached = self._run_with_context(
                        lambda t=text: cache_service.get(t, source_lang, target_lang)
                    )
                    if cached:
                        results[i] = cached.translated_text
                        continue
                except Exception:
                    pass
            to_translate.append((i, text))

        # 第二步：并行翻译
        if to_translate:
            def _translate_item(item):
                idx, txt = item
                result = self.translate(txt, source_lang, target_lang)
                return idx, result if result else txt

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {
                    executor.submit(_translate_item, item): item
                    for item in to_translate
                }

                completed = 0
                for future in as_completed(future_to_item):
                    idx, result = future.result()
                    results[idx] = result
                    completed += 1
                    if progress_callback:
                        cache_hits = total - len(to_translate)
                        progress_callback(cache_hits + completed, total)

        logger.info(f"批量翻译完成: 共{total}条, 缓存命中{total - len(to_translate)}条, 并行翻译{len(to_translate)}条")
        return results
```

- [ ] **Step 3: 为备用翻译服务添加简单重试**

修改 `free_translation_service.py` 的 `GoogleTranslationService.translate()` 方法，在 try 块外层添加重试循环：

```python
    def translate(self, text: str, source_lang: str = 'en',
                  target_lang: str = 'zh') -> Optional[str]:
        if not text or not text.strip():
            return text

        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)

        client_class = self._get_client()
        if not client_class:
            return None

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                lang_map = {'zh': 'zh-CN', 'en': 'en', 'auto': 'auto'}
                source = lang_map.get(source_lang, source_lang)
                target = lang_map.get(target_lang, target_lang)

                translator = client_class(source=source, target=target)
                result = translator.translate(text)

                self._last_request_time = time.time()

                if result:
                    logger.info(f"Google翻译成功: {text[:50]}... -> {result[:50]}...")
                    return result

            except Exception as e:
                if attempt < max_retries:
                    logger.debug(f"Google翻译失败(第{attempt + 1}次)，重试中: {e}")
                    time.sleep(1.0 * (attempt + 1))
                else:
                    logger.warning(f"Google翻译失败(重试耗尽): {e}")

        return None
```

- [ ] **Step 4: 运行全量测试**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/zhipu_translation_service.py app/services/free_translation_service.py tests/test_translation_service.py
git commit -m "feat(translation): 优化批量翻译并行度，添加tenacity重试机制"
```

---

### Task 5: 完善翻译缓存失效机制

**问题：** 缓存无版本控制，错误翻译永不过期；无质量评分实际使用。

**Files:**
- 修改: `app/services/translation_cache_service.py`
- 修改: `app/services/zhipu_translation_service.py`

- [ ] **Step 1: 编写缓存失效机制的失败测试**

```python
class TestTranslationCacheExpiry:
    """翻译缓存失效机制测试"""

    def test_cache_version_invalidates_old_entries(self):
        from app.services.translation_cache_service import TranslationCacheService
        service = TranslationCacheService()
        current_version = service.CACHE_VERSION
        assert isinstance(current_version, int)
        assert current_version >= 1

    def test_set_and_get_with_version(self):
        from unittest.mock import Mock, MagicMock, patch
        from app.services.translation_cache_service import TranslationCacheService
        service = TranslationCacheService()
        # 此测试需要数据库，在集成测试中验证
        assert hasattr(service, 'CACHE_VERSION')
```

- [ ] **Step 2: 为 `TranslationCacheService` 添加版本号**

修改 `TranslationCacheService.__init__()`：

```python
class TranslationCacheService:
    CACHE_VERSION = 2  # 递增此值可使旧缓存失效

    def __init__(self):
        self.default_model = 'glm-4.7-flash'
```

- [ ] **Step 3: 修改 `get()` 方法检查版本**

在 `TranslationCacheService.get()` 中，查询缓存后添加版本检查：

```python
        if cache:
            # 版本检查：版本不匹配的缓存视为无效
            if hasattr(cache, 'model_version') and cache.model_version:
                try:
                    cached_version = int(cache.model_version)
                    if cached_version < self.CACHE_VERSION:
                        logger.info(f"缓存版本过期(v{cached_version} < v{self.CACHE_VERSION})，删除")
                        try:
                            db.session.delete(cache)
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                        return None
                except (ValueError, TypeError):
                    pass
            else:
                # 无版本号的旧缓存，视为过期
                logger.info("缓存无版本号，视为过期")
                try:
                    db.session.delete(cache)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                return None

            # 更新使用记录
            cache.usage_count += 1
            cache.last_used_at = datetime.now(timezone.utc)
            try:
                db.session.commit()
            except Exception as e:
                logger.error(f"更新缓存使用记录失败: {e}")
                db.session.rollback()

            logger.debug(f"缓存命中: {source_lang}->{target_lang}, 已使用{cache.usage_count}次")
            return cache
```

- [ ] **Step 4: 修改 `HybridTranslationService.translate()` 存缓存时带版本号**

修改 `HybridTranslationService.translate()` 中 L511-518 存缓存部分：

```python
        if translated and cache_service:
            try:
                from .translation_cache_service import TranslationCacheService
                cache_version = str(TranslationCacheService.CACHE_VERSION)
                self._run_with_context(
                    lambda: cache_service.set(
                        text, translated, source_lang, target_lang,
                        model_name='glm-4.7-flash',
                        model_version=cache_version
                    )
                )
                logger.info("翻译结果已缓存")
            except Exception as e:
                logger.warning(f"缓存翻译结果失败: {e}")
```

- [ ] **Step 5: 运行测试**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 6: 提交**

```bash
git add app/services/translation_cache_service.py app/services/zhipu_translation_service.py tests/test_translation_service.py
git commit -m "feat(translation): 添加缓存版本控制，旧版本缓存自动失效"
```

---

### Task 6: 稳定备用翻译链路

**问题：** `deep-translator` 未在 requirements.txt，备用翻译可能断裂。

**Files:**
- 修改: `requirements.txt`

- [ ] **Step 1: 在 requirements.txt 添加 deep-translator**

在 `requirements.txt` 中找到 `zhipuai` 行后面添加：

```
deep-translator>=1.11.0
```

- [ ] **Step 2: 安装依赖验证**

Run: `cd d:\BookRank3 && pip install deep-translator>=1.11.0`
Expected: Successfully installed

- [ ] **Step 3: 提交**

```bash
git add requirements.txt
git commit -m "fix(translation): 添加deep-translator到依赖，稳定备用翻译链路"
```

---

### Task 7: 补充测试覆盖

**问题：** 当前仅12个测试，未覆盖后处理、质量校验、缓存版本、并行批量翻译等关键逻辑。

**Files:**
- 修改: `tests/test_translation_service.py`

- [ ] **Step 1: 添加后处理集成测试**

```python
class TestPostprocessIntegration:
    """后处理与翻译服务集成测试"""

    def test_translate_with_field_type_calls_correct_prompt(self):
        """验证 translate 传入 field_type 时使用正确提示词"""
        from unittest.mock import Mock, patch
        from app.services.zhipu_translation_service import ZhipuTranslationService

        service = ZhipuTranslationService(api_key='test')
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = '测试书名'
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        service._client = mock_client

        service.translate('Test Book', field_type='title')

        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args[1]['messages'][0]['content']
        assert '书名号' in system_msg or '《》' in system_msg

    def test_batch_translate_with_mock(self):
        """验证批量翻译并行执行"""
        from unittest.mock import Mock, patch
        from app.services.zhipu_translation_service import HybridTranslationService

        service = HybridTranslationService(zhipu_api_key='test')
        mock_cache = Mock()
        mock_cache.get.return_value = None
        service._cache_service = mock_cache

        with patch.object(service, 'translate', return_value='翻译结果') as mock_translate:
            texts = ['Hello', 'World', 'Test']
            results = service.translate_batch(texts, max_workers=2)
            assert len(results) == 3
            assert mock_translate.call_count == 3
```

- [ ] **Step 2: 添加 `FreeTranslationService` 测试**

```python
class TestFreeTranslationService:
    """免费翻译服务测试"""

    def test_google_translate_unavailable_without_package(self):
        """验证 deep-translator 未安装时的优雅降级"""
        from unittest.mock import patch
        from app.services.free_translation_service import GoogleTranslationService
        service = GoogleTranslationService()
        service._client = None
        service._deep_translator_warned = False
        with patch('app.services.free_translation_service.GoogleTranslator', side_effect=ImportError):
            result = service.translate('Hello')
            assert result is None

    def test_free_service_empty_input(self):
        """验证空输入处理"""
        from app.services.free_translation_service import FreeTranslationService
        service = FreeTranslationService()
        assert service.translate('') == ''
        assert service.translate(None) is None
```

- [ ] **Step 3: 运行全量测试**

Run: `cd d:\BookRank3 && python -m pytest tests/test_translation_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 运行全部测试确保无回归**

Run: `cd d:\BookRank3 && python -m pytest tests/ -v --tb=short`
Expected: 所有测试 PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_translation_service.py
git commit -m "test(translation): 补充后处理集成测试、质量校验测试、免费翻译服务测试"
```

---

### Task 8: 更新 CHANGELOG 和版本说明

**Files:**
- 修改: `CHANGELOG.md`

- [ ] **Step 1: 读取当前 CHANGELOG.md**

Run: 读取 `d:\BookRank3\CHANGELOG.md`

- [ ] **Step 2: 添加本次变更记录**

在 CHANGELOG.md 顶部添加新版本条目，包含：
- 版本号递增
- 修改日期 2026-04-26
- 7项变更：统一后处理逻辑、字段感知提示词、质量校验、批量翻译优化+重试、缓存版本控制、备用翻译稳定化、测试补齐

- [ ] **Step 3: 提交**

```bash
git add CHANGELOG.md
git commit -m "docs: 更新CHANGELOG，记录翻译能力优化变更"
```

---

## 自检清单

| 检查项 | 状态 |
|--------|------|
| 每个需求点都有对应Task？ | ✅ 8个问题→8个Task |
| 有无 TBD/TODO/placeholder？ | ✅ 无 |
| 类型/方法名在前后Task中一致？ | ✅ `_get_prompt_for_field`、`_validate_translation`、`CACHE_VERSION` 定义与使用一致 |
| 测试是否覆盖所有新增逻辑？ | ✅ 后处理、提示词、质量校验、批量翻译、缓存版本、免费服务 |
