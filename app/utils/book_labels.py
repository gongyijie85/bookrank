"""语言名的中英对照（显示层，不改数据库）。

`google_books_client.py:202` 在抓取时就把 `Config.LANGUAGE_MAP` 的**中文名**写进了
`books.language` / `book_metadata.language`，所以英文页会显示「英语」。这些值已持久化，
改数据要回填、也要冒冲突风险；正确层次是显示期按 locale 反查。

不走 gettext：这些串只存在于数据库，模板里没有任何字面量，babel 抽不到；即便手工塞进
`.po`，下一次 `pybabel update` 也会按"无引用"把它们清掉。

`_ZH_TO_EN` 的键必须与 `Config.LANGUAGE_MAP` 的值集一一对应，由
tests/test_language_labels.py 钉住 —— 只比键集合不比值的 parity 测试曾在 #235 放过
真实分歧（`and` vs `&`），这里直接比值。
"""

from __future__ import annotations

from datetime import date, datetime

from flask_babel import get_locale

_ZH_TO_EN: dict[str, str] = {
    '英语': 'English',
    '中文': 'Chinese',
    '日语': 'Japanese',
    '韩语': 'Korean',
    '法语': 'French',
    '德语': 'German',
    '西班牙语': 'Spanish',
    '俄语': 'Russian',
}


def positive_int_text(value: object) -> str:
    """把「页数」这类正整数字段归一化成可展示文本；无效值一律返回空串。

    库里的 `page_count` 是脏数据重灾区：既有字符串 `'320'`，也有 `0`/`'0'`（NYT 用它表示
    "未知"，直接渲染就是「页数：0 页」）、负数、布尔、分数，以及 `'Unknown'`/'N/A' 之类的
    占位串。模板侧的旧写法是逐个字面量比较（`not in ('', 'Unknown', 'N/A', ...)`），
    每碰到一种新脏值就漏一次；这里收敛成单一判定：

    - 只接受正数（`bool` 是 `int` 的子类，显式排除，否则 `True` 会渲染成「1 页」）；
    - 数值字符串先去空白再解析（`'320'` OK，`'3.5'` 因非整数被拒）；
    - 解析结果必须 > 0，故 `0`/`'0'`/`'-12'`/`None`/`''`/`'abc'` 全部落空。

    返回**规范化后的十进制字符串**（去掉 `'0320'` 这类前导零与 `' 320 '` 的空白），
    模板直接输出它即可；空串表示"没有可展示的页数"，调用方据此整行隐藏。
    """
    if isinstance(value, bool) or value is None:
        return ''
    if isinstance(value, int):
        return str(value) if value > 0 else ''
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() and value > 0 else ''
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ''
        # 只认纯十进制整数串：'3.5' / '3e2' / 'Unknown' / 'N/A' 一律落空
        if not text.isdecimal():
            return ''
        number = int(text, 10)
        return str(number) if number > 0 else ''
    return ''


def language_name(value: object, locale: str | None = None) -> str:
    """把库里存的语言名按 locale 呈现。

    英文 locale 下未收录的名字（例如 Google 直接给了原始码 `en`/`zu`）原样返回，
    不猜、不编造 —— 宁可显示一个中性码，也不要显示错的语种名。
    """
    text = '' if value is None else str(value)
    if not text:
        return ''
    active = locale or str(get_locale() or 'zh')
    if active.startswith('en'):
        return _ZH_TO_EN.get(text, text)
    return text


def bilingual(zh: object, en: object, locale: str | None = None) -> str:
    """双语字段择一，另一侧兜底：中文侧为 `zh or en`，英文侧为 `en or zh`。

    调用点都是"库里可能只填了一边"的可变字段（书名、奖项名、出版社名），所以两侧都不
    允许空着。与 `award_term` 的兜底方向相反：奖项名/书名是**标识**，隐掉等于把条目变成
    空白，所以没译文时宁可退回另一种语言；而国家/类别只是装饰性标签，退中文就是 #227 报
    的泄漏本身。
    """
    zh_text = '' if zh is None else str(zh)
    en_text = '' if en is None else str(en)
    active = locale or str(get_locale() or 'zh')
    if active.startswith('en'):
        return en_text or zh_text
    return zh_text or en_text


_COUNTRY_ZH_TO_EN: dict[str, str] = {
    '美国': 'United States',
    '英国': 'United Kingdom',
    '瑞典': 'Sweden',
}

_AWARD_CATEGORY_ZH_TO_EN: dict[str, str] = {
    '小说': 'Fiction',
    '文学': 'Literature',
    '最佳小说': 'Best Fiction',
    '最佳长篇小说': 'Best Novel',
    '翻译小说': 'Translated Fiction',
    '非虚构': 'Nonfiction',
    '非虚构 (获奖)': 'Nonfiction (Winner)',
    '非虚构 (入围)': 'Nonfiction (Shortlist)',
}

_AWARD_TERM_ZH_TO_EN: dict[str, str] = {**_COUNTRY_ZH_TO_EN, **_AWARD_CATEGORY_ZH_TO_EN}


def award_term(value: object, locale: str | None = None) -> str:
    """库里存的中文枚举词（奖项国家、奖项类别）按 locale 呈现。

    未知值在英文 locale 下返回空串，让模板把整个标签隐掉：国家/类别是装饰性信息，
    缺一个标签不伤识别，挂一段中文则正是 #227 要消除的泄漏。两张映射的键集由
    tests/test_language_labels.py 对着种子数据（AWARDS_FALLBACK_DATA 的 country、
    sample_award_books 的 category）钉住，新增种子词不登记就红。
    """
    text = '' if value is None else str(value)
    if not text:
        return ''
    active = locale or str(get_locale() or 'zh')
    if active.startswith('en'):
        return _AWARD_TERM_ZH_TO_EN.get(text, '')
    return text


_CATEGORY_ZH_TO_EN: dict[str, str] | None = None


def _category_zh_to_en() -> dict[str, str]:
    """从爬虫自己的 CATEGORY_EN_TO_ZH 反查，不再手抄第二张表（抄来的会漂移）。

    `General`/`general` 都映射到「综合」，取非全小写的那个作英文显示名。
    """
    global _CATEGORY_ZH_TO_EN
    if _CATEGORY_ZH_TO_EN is None:
        from ..services.publisher_data import CATEGORY_EN_TO_ZH

        reversed_map: dict[str, str] = {}
        for en, zh in CATEGORY_EN_TO_ZH.items():
            current = reversed_map.get(zh)
            if current is None or current.islower():
                reversed_map[zh] = en
        _CATEGORY_ZH_TO_EN = reversed_map
    return _CATEGORY_ZH_TO_EN


def _category_en_to_zh() -> dict[str, str]:
    """英文别名 → 中文显示名，直接复用 publisher_data 的单一真相源。

    不另建第二张部分表：手工表没覆盖到的已知英文键会原样漏出英文（本次要修的
    「zh 页显示 Business」）。表内已收录同义键（Biography / Biography &
    Autobiography），所以别名与规范键都命中同一中文值。
    """
    from ..services.publisher_data import CATEGORY_EN_TO_ZH

    return CATEGORY_EN_TO_ZH


def category_name(value: object, locale: str | None = None) -> str:
    """新书分类按 locale 呈现。

    中文页：库里的英文别名（`Business` / `Biography & Autobiography`）经
    `CATEGORY_EN_TO_ZH` 显示为中文；已是中文的值原样返回；表里没有的未知值原样
    返回（诚实展示，不猜、不隐掉筛选项）。

    英文页：反查 `CATEGORY_EN_TO_ZH` 的键集，把中文值还原为英文；未知值原样返回
    （chip 是**可点的筛选项**，隐掉等于悄悄删掉一种筛选）。新增分类只会经
    CATEGORY_EN_TO_ZH 写进库，所以这两张表天然覆盖全部取值。
    """
    text = '' if value is None else str(value)
    if not text:
        return ''
    active = locale or str(get_locale() or 'zh')
    if active.startswith('en'):
        return _category_zh_to_en().get(text, text)
    return _category_en_to_zh().get(text, text)


def category_alias_labels() -> dict[str, str]:
    """英文别名 → 规范中文显示名，供前端复用同一张映射。

    `publisher_data.CATEGORY_EN_TO_ZH` 是唯一真相源，这里只是把它交出去，
    不做增删；前端据此把 chip / 分类标签翻成中文，未知别名原样保留。
    """
    return dict(_category_en_to_zh())


def publisher_labels(zh: object, en: object) -> dict[str, str]:
    """单个出版社的 bilingual 展示名：`{'zh': ..., 'en': ...}`。

    两侧都做 `or` 兜底（与 `bilingual()` 同口径）：库里可能只填了一边，
    前端切语言时不能把出版社名渲染成空白。

    **不是**第二张别名表：调用方传进来的就是 ORM 上的 `name` / `name_en`
    两列本身，这里只负责把它们整理成前端可按语言取值的形状。
    """
    zh_text = '' if zh is None else str(zh)
    en_text = '' if en is None else str(en)
    return {'zh': zh_text or en_text, 'en': en_text or zh_text}


def _as_date(value: object) -> date | None:
    """把 date / datetime / ISO 字符串归一为 date；其他类型返回 None。"""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


# 出版日期状态：**只由 publication_date 决定**。绝不能用 created_at（系统发现/
# 入库时间）冒充出版日期 —— 那会把「日期待确认」的书说成已出版。
DATE_STATE_UPCOMING = 'upcoming'
DATE_STATE_PUBLISHED = 'published'
DATE_STATE_PENDING = 'pending'

_PUBLICATION_STATE_TEXT: dict[str, dict[str, str]] = {
    'zh': {
        DATE_STATE_UPCOMING: '即将出版',
        DATE_STATE_PUBLISHED: '已出版',
        DATE_STATE_PENDING: '出版日期待确认',
    },
    'en': {
        DATE_STATE_UPCOMING: 'Upcoming',
        DATE_STATE_PUBLISHED: 'Published',
        DATE_STATE_PENDING: 'Publication date pending',
    },
}


def publication_state(value: object, today: date | None = None) -> str:
    """出版日期状态：future=即将出版，past/today=已出版，无日期=待确认。"""
    parsed = _as_date(value)
    if parsed is None:
        return DATE_STATE_PENDING
    reference = today or date.today()
    return DATE_STATE_PUBLISHED if parsed <= reference else DATE_STATE_UPCOMING


def publication_state_label(value: object, locale: str | None = None, today: date | None = None) -> str:
    """出版日期状态的可显示文案（中/英，与模板 `_()` 字面量同源）。

    模板调用点显式传入已解析的 `_l`（`get_locale()`），不用 `get_locale()` 的隐式
    结果：`flask_babel.get_locale()` 把结果缓存在 app context 上（`ctx.babel_locale`），
    一旦同一个 app context 里渲染第二个请求（测试、脚本、复用上下文的批量渲染），
    就会拿到第一个请求缓存下来的语言，中文页会显示英文状态。把 locale 作为显式参数
    交给过滤器，既不改动其它 display helper 的既有语义，也不复刻一套 locale 优先级。

    未识别的 locale 退中文 —— 与 `category_name` 等本模块其余函数一致的兜底方向。
    """
    state = publication_state(value, today=today)
    active = locale or str(get_locale() or 'zh')
    table = _PUBLICATION_STATE_TEXT['en' if active.startswith('en') else 'zh']
    return table[state]
