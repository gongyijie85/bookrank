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
