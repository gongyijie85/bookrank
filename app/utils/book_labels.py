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
