"""书名/作者归一化，用于跨榜匹配同一本书的不同版本。

NYT 各分类榜对同一本书使用不同 ISBN（精装、平装、儿童版各自独立），
因此跨榜聚合只能按归一化后的书名 + 作者匹配，按 ISBN 匹配会大量漏配。
"""

import re
import unicodedata

# 撇号直接删除（不留空格），让 "Handmaid's" 与 "Handmaids" 落到同一个键；
# 其余非字母数字/非中日韩字符一律视为分隔符
_APOSTROPHES = re.compile(r"['’`ʼ´′]")
_NON_WORD = re.compile(r'[^0-9a-z\u3040-\u30ff\u4e00-\u9fff\s]+')
_WHITESPACE = re.compile(r'\s+')
_LEADING_ARTICLE = re.compile(r'^(?:a|an|the)\s+')


def normalize_text(value: object) -> str:
    """小写、去变音符、去标点、压缩空白，并去掉英文标题开头的冠词。"""
    if not value:
        return ''
    decomposed = unicodedata.normalize('NFKD', str(value))
    stripped = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_apostrophes = _APOSTROPHES.sub('', stripped)
    collapsed = _WHITESPACE.sub(' ', _NON_WORD.sub(' ', without_apostrophes.lower())).strip()
    return _LEADING_ARTICLE.sub('', collapsed)


def book_match_key(title: object, author: object) -> str:
    """同一本书不同版本的稳定标识；缺作者时退化为书名键。"""
    author_key = normalize_text(author)
    title_key = normalize_text(title)
    if not title_key:
        return ''
    return f'{title_key}|{author_key}'
