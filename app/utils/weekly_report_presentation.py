"""周报展示准备（audit04）。

侧效应为零：只返回准备好的值/字典，绝不改写附着在 ORM 对象上的
``report.summary`` / ``report.content``（读路径上的 record-view 提交 / autoflush
可能把意外改写持久化）。列表、详情、导出共用同一套准备逻辑，保证
上榜记录 / 新书 / 上升 / 下降在任何一处展示都一致。

权威口径：以结构化 ``content`` 里的 ``total_books``（展示为「上榜记录」）/ ``total_new`` /
``total_rising`` / ``total_falling`` 为准，绝不用被截断到 Top-N 的数组长度冒充总量。
上榜记录 = 本报告周期所采集分类榜单上的条目数，同一本书出现在多个分类榜单会计多次，
因此不等于去重后的书数 / ISBN 数。缺失的权威值视为「数据待补全」，不臆造为 0；
已知为 0 就保持 0。若只有某一个总量缺失，其余已知总量仍照常呈现。

摘要策略（audit04 设计更正）：公共展示摘要一律使用由已校验结构化总量构造的**确定性**
事实摘要，不再信任/复用存储叙述（存储叙述是 AI 生成的自由文本，正则校验不足以拦截
「本周新上榜书籍10本」这类与结构化计数冲突但匹配不上任何模式的说法）。库里的
``report.summary`` 原样保留、不改写，但绝不当作「已校验文本」展示或导出。新生成周报
在首次保存前也先把确定性事实摘要写入 ``report.summary``，使新入库周报不可能携带
未经验证的 AI 数值断言。

文案国际化：不走 gettext（这些串只在服务层/模板里动态拼接，抽不到 msgid），改用
``locale`` 参数的中英对照表（同 ``book_labels.py`` 的口径），由 ``get_locale()``
解析当前语言，缺省回退中文。这样英文页不会出现未翻译的中文标签。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .date_helpers import parse_report_content

if TYPE_CHECKING:
    from datetime import date

_TOTAL_KEYS = ('total_books', 'total_new', 'total_rising', 'total_falling')

# 占位指标：X / XX 后跟量词「本」，是「占位数字」的强信号（如「上榜书籍总数：X本」）。
# 只匹配 X+ 紧邻「本」，不会误伤书名里的数字或字母 X（书名带书名号，且无「X本」形态）。
# 仅用于兼容既有 AI 摘要生成链路（见 weekly_report_service._generate_ai_summary）；
# 公共展示摘要不再依赖它。
_PLACEHOLDER_METRIC_RE = re.compile(r'\bX+\s*本(?:书)?', re.IGNORECASE)

# 确定性摘要里各指标的典型断言模式，仅用于校验「存储叙述与结构化计数是否冲突」。
# 仅用于兼容既有 AI 摘要生成链路；公共展示摘要不再依赖它。
_METRIC_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    'total_books': [
        ('共有 **{}** 本书籍进入纽约时报畅销书榜', re.compile(r'共有\s*\**\s*(\d+)\s*\**\s*本书籍')),
        ('共 {} 本', re.compile(r'共\s*(\d+)\s*本')),
        ('{} 本书籍', re.compile(r'(\d+)\s*本书籍')),
    ],
    'total_new': [
        ('{} 本为新上榜', re.compile(r'(\d+)\s*本为新上榜')),
        ('新上榜 {} 本', re.compile(r'新上榜\s*(\d+)\s*本')),
    ],
    'total_rising': [
        ('{} 本上升', re.compile(r'(\d+)\s*本上升')),
    ],
    'total_falling': [
        ('{} 本下降', re.compile(r'(\d+)\s*本下降')),
    ],
}

# ---- 中英文案（locale 参数策略，同 book_labels.py，不引入 gettext msgid）----

_ZH: dict[str, str] = {
    'unknown': '数据待补全',
    'no_books': '本周（{range}）上榜记录数量待补全',
    'books': '本周（{range}）共记录 {count} 条上榜记录',
    'books_no_range': '本报告周期共记录 {count} 条上榜记录',
    'books_unknown_no_range': '本报告周期上榜记录数量待补全',
    'new': '其中 {count} 条为新上榜',
    'rank_both': '排名方面，{rising} 条上升、{falling} 条下降',
    'rank_rising': '排名方面，{count} 条上升，下降数量待补全',
    'rank_falling': '排名方面，{count} 条下降，上升数量待补全',
    'rank_unknown': '排名变动数量待补全',
    'new_unknown': '其中新上榜记录数量待补全',
    'scope': '口径：本报告周期所采集分类榜单的上榜记录数，同一本书出现在多个分类榜单会分别计数，不等于去重后的书数或 ISBN 数',
    'term': '。',
}

_EN: dict[str, str] = {
    'unknown': 'Data pending',
    'no_books': 'The number of list entries is pending for this week ({range})',
    'books': 'This week ({range}) recorded {count} list entries',
    'books_no_range': 'This reporting period recorded {count} list entries',
    'books_unknown_no_range': 'The number of list entries is pending for this reporting period',
    'new': '{count} entries are new to the lists',
    'rank_both': 'By rank movement, {rising} rose and {falling} fell',
    'rank_rising': 'By rank movement, {count} rose and the falling count is pending',
    'rank_falling': 'By rank movement, {count} fell and the rising count is pending',
    'rank_unknown': 'Rank-movement counts are pending',
    'new_unknown': 'The number of new-to-list entries is pending',
    'scope': 'Scope: list entries collected for this reporting period across category lists; the same book on multiple category lists counts separately, so this is not a count of unique books or ISBNs',
    'term': '. ',
}


def _resolve_locale(locale: str | None) -> str:
    """解析当前语言；无请求上下文或未知值一律回退中文。"""
    if locale:
        return 'en' if str(locale).startswith('en') else 'zh'
    try:
        from flask_babel import get_locale

        active = str(get_locale() or 'zh')
        return 'en' if active.startswith('en') else 'zh'
    except Exception:
        return 'zh'


def _labels(locale: str | None) -> dict[str, str]:
    return _EN if _resolve_locale(locale) == 'en' else _ZH


def _fmt_date(value: date | None, locale: str | None) -> str:
    """日期展示：英文用 ISO，中文用 YYYY年MM月DD日。"""
    if value is None:
        return ''
    if _resolve_locale(locale) == 'en':
        return value.strftime('%Y-%m-%d')
    return f'{value.year:04d}年{value.month:02d}月{value.day:02d}日'


def range_connector(locale: str | None = None) -> str:
    """日期区间连接词；中文「至」，英文用 en dash（英文不用「至」）。"""
    return ' 至 ' if _resolve_locale(locale) == 'zh' else '–'


def format_week_range(
    week_start: date | None,
    week_end: date | None,
    locale: str | None = None,
) -> str:
    """按当前语言渲染周报日期区间，缺任一端时返回空串（不臆造日期）。"""
    start = _fmt_date(week_start, locale)
    end = _fmt_date(week_end, locale)
    if not start or not end:
        return ''
    return f'{start}{range_connector(locale)}{end}'


# 系统生成的周报标准标题（weekly_report_service 写入 DB 的固定形态）：
# '{中文起}-{中文止} 畅销书周报'。只用于**识别**该形态，命中才做展示层本地化。
_STANDARD_TITLE_RE = re.compile(
    r'^\s*(?P<start>\d{4}年\d{2}月\d{2}日)\s*[-–—]\s*(?P<end>\d{4}年\d{2}月\d{2}日)\s*(?P<suffix>畅销书周报)\s*$'
)

# 另一已知标准标题（weekly_report_service 写入的无日期区间固定标题）：
# 精确匹配才本地化，绝不前缀/子串匹配 —— 任意标题（含带该短语的运营标题）原样透传。
_STANDARD_PLAIN_TITLE_ZH = '纽约时报畅销书周报'
_STANDARD_PLAIN_TITLE_EN = 'NYT Weekly Bestseller Report'


def localize_report_title(title: str | None, locale: str | None = None) -> str:
    """本地化**系统生成的标准周报标题**；其余（人工/任意 DB 标题）原样返回。

    仅当标题严格匹配 ``服务层生成的`` 固定形态时才改写：任意标题（含运营手写的
    中英文标题）一律 verbatim 透传，绝不猜测、绝不改写数据库。
    非字符串（缺省/None/测试替身）按空串处理，绝不抛异常。
    """
    if not isinstance(title, str):
        return ''
    raw = title.strip()
    if not raw:
        return raw
    if _resolve_locale(locale) == 'zh':
        # 中文侧：标准标题本来就是中文，原样返回（含无日期的固定标题）。
        return raw
    if raw == _STANDARD_PLAIN_TITLE_ZH:
        return _STANDARD_PLAIN_TITLE_EN
    match = _STANDARD_TITLE_RE.match(raw)
    if not match:
        return raw
    start = match.group('start')
    end = match.group('end')

    def _iso(cn: str) -> str:
        year, month, day = re.findall(r'\d+', cn)
        return f'{year}-{month}-{day}'

    return f'{_iso(start)}–{_iso(end)} Weekly Bestseller Report'


def _is_valid_total(value: Any) -> bool:
    """权威总量必须是非负整数；缺省、None、字符串、负数都视为未知。"""
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    return value >= 0


def extract_totals(content: dict[str, Any] | None) -> dict[str, Any]:
    """从结构化 content 提取并校验四个权威总量。

    Returns:
        {'total_books': int|None, 'total_new': ..., 'total_rising': ..., 'total_falling': ...}
    """
    content = content or {}
    result: dict[str, Any] = {}
    for key in _TOTAL_KEYS:
        value = content.get(key)
        result[key] = value if _is_valid_total(value) else None
    return result


def has_placeholder_metric(text: str) -> bool:
    """判断叙述是否含 X / XX 占位指标（如「X本」）。仅兼容 AI 生成链路。"""
    if not text:
        return False
    return bool(_PLACEHOLDER_METRIC_RE.search(text))


def summary_conflicts_with_totals(text: str, totals: dict[str, Any]) -> bool:
    """叙述里出现的明确计数若与任一已知权威总量冲突，视为不可信。仅兼容 AI 生成链路。"""
    if not text:
        return False
    for key, patterns in _METRIC_PATTERNS.items():
        known = totals.get(key)
        if known is None:
            continue
        for _label, pattern in patterns:
            for match in pattern.finditer(text):
                try:
                    claimed = int(match.group(1))
                except (TypeError, ValueError):
                    continue
                if claimed != known:
                    return True
    return False


def _all_totals_known(totals: dict[str, Any]) -> bool:
    return all(totals[key] is not None for key in _TOTAL_KEYS)


def build_factual_summary(
    totals: dict[str, Any],
    week_start: date | None = None,
    week_end: date | None = None,
    locale: str | None = None,
) -> str:
    """从已知权威总量构造确定性、纯文本的事实摘要（公共展示/导出/入库共用）。

    - 日期区间总是保留（缺日期时不留空括号）；
    - 缺失的权威值不臆造为 0，逐项标注「数据待补全」；
    - 已知为 0 就保持 0（``0`` 与「待补全」语义不同）；
    - 无论缺失哪些总量，其余**全部**已知总量都照常呈现；
    - 只有上升已知时同样点明下降待补全（反之亦然）；
    - 包含「上榜记录」口径说明。
    """
    L = _labels(locale)
    term = L['term']
    start = _fmt_date(week_start, locale)
    end = _fmt_date(week_end, locale)
    zh = _resolve_locale(locale) == 'zh'
    daterange = (f'{start} 至 {end}' if zh else f'{start}–{end}') if start and end else ''

    total_books = totals.get('total_books')
    if total_books is None:
        head = L['no_books'].format(range=daterange) if daterange else L['books_unknown_no_range']
    else:
        head = (
            L['books'].format(range=daterange, count=total_books)
            if daterange
            else L['books_no_range'].format(count=total_books)
        )

    parts = [head]

    total_new = totals.get('total_new')
    if total_new is not None:
        parts.append(L['new'].format(count=total_new))
    else:
        parts.append(L['new_unknown'])

    total_rising = totals.get('total_rising')
    total_falling = totals.get('total_falling')
    if total_rising is not None and total_falling is not None:
        parts.append(L['rank_both'].format(rising=total_rising, falling=total_falling))
    elif total_rising is not None:
        parts.append(L['rank_rising'].format(count=total_rising))
    elif total_falling is not None:
        parts.append(L['rank_falling'].format(count=total_falling))
    else:
        parts.append(L['rank_unknown'])

    parts.append(L['scope'])
    # 片段本身不带句末标点，统一用 term 连接并在末尾补一个 term。
    return term.join(parts) + term


def unknown_total_label(locale: str | None = None) -> str:
    """缺失/未知权威值展示文案（按语言）。"""
    return _labels(locale)['unknown']


def scope_label(locale: str | None = None) -> str:
    """指标口径说明（按语言）。"""
    return _labels(locale)['scope']


# 图表不可用文案（缺失/非法 category_stats 时显式提示，绝不用 0 或猜测值顶替）。
_UNAVAILABLE_CHART_ZH = '数据待补全：缺少可用的分类统计，暂时无法绘制书籍类别分布图'
_UNAVAILABLE_CHART_EN = (
    'Data pending: a usable category breakdown is unavailable, so the category distribution chart cannot be drawn'
)


def _valid_category_count(value: Any) -> int | None:
    """分类计数必须是非负整数；缺省、None、字符串、负数、bool 都视为非法。"""
    return value if _is_valid_total(value) else None


def category_chart_distribution(
    content: dict[str, Any] | None,
    locale: str | None = None,
) -> dict[str, Any]:
    """从结构化 ``category_stats`` 构造类别分布图的标签/计数。

    只使用 ``category_stats[*].count``（每个分类的权威采集条目数），
    **绝不**把 ``top_changes`` / ``new_books`` / ``top_risers`` /
    ``longest_running`` / ``featured_books`` 这些被截断到 Top-N 且互相重叠的数组
    拼接起来统计——那样会重复计数：例如 total=15、只有一个分类且 count=15，
    而这些数组合计 24 本书时，图表必须画 15，而不是 24。

    ``category_stats`` 缺失、结构非法或含非法 count 时返回 ``available=False``
    并给出显式不可用文案，绝不用 0/猜测值顶替。

    Returns:
        {'available': bool, 'labels': list[str], 'counts': list[int], 'message': str}
    """
    unavailable = _UNAVAILABLE_CHART_ZH if _resolve_locale(locale) == 'zh' else _UNAVAILABLE_CHART_EN

    def _unavailable() -> dict[str, Any]:
        return {'available': False, 'labels': [], 'counts': [], 'message': unavailable}

    raw_stats = (content or {}).get('category_stats')
    if not isinstance(raw_stats, dict):
        return _unavailable()

    pairs: list[tuple[str, int]] = []
    for name, stats in raw_stats.items():
        if not isinstance(name, str) or not name.strip():
            return _unavailable()
        if not isinstance(stats, dict):
            return _unavailable()
        count = _valid_category_count(stats.get('count'))
        if count is None:
            return _unavailable()
        pairs.append((name, count))

    if not pairs:
        return _unavailable()

    return {
        'available': True,
        'labels': [name for name, _count in pairs],
        'counts': [count for _name, count in pairs],
        'message': '',
    }


def unknown_category_chart_message(locale: str | None = None) -> str:
    """类别分布图不可用时的显式提示文案（按语言）。"""
    return _UNAVAILABLE_CHART_ZH if _resolve_locale(locale) == 'zh' else _UNAVAILABLE_CHART_EN


def prepare_report_presentation(
    report: Any,
    content: dict[str, Any] | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """为单份周报准备展示数据（列表 / 详情 / 导出共用）。

    Args:
        report: 周报对象（提供 summary / week_start / week_end；当 ``content`` 缺省时
                也从它解析 content）。
        content: 可选，已解析的结构化 content；缺省时从 report 解析。
        locale: 可选，展示语言；缺省时经 get_locale() 解析。

    Returns:
        {
            'content': 经校验的结构化 content（复制品，绝不改原对象），
                       增补 total_*_known / total_*_display / scope_label /
                       category_chart；
            'summary': 确定性事实摘要（公共展示/导出统一使用，不来自存储叙述）；
            'summary_source': 恒为 'derived'；
            'totals': 校验后的权威总量 {key: int|None}。
        }
    """
    raw_content = content if content is not None else (parse_report_content(report) or {})
    prepared: dict[str, Any] = dict(raw_content)
    totals = extract_totals(raw_content)

    for key in _TOTAL_KEYS:
        value = totals.get(key)
        prepared[f'{key}_known'] = value is not None
        prepared[f'{key}_display'] = str(value) if value is not None else unknown_total_label(locale)
        prepared[key] = value

    prepared['totals_known'] = _all_totals_known(totals)
    prepared['scope_label'] = scope_label(locale)
    # 类别分布图数据：只用结构化 category_stats[*].count，避免重叠 Top-N 数组重复计数。
    prepared['category_chart'] = category_chart_distribution(raw_content, locale)

    week_start = getattr(report, 'week_start', None)
    week_end = getattr(report, 'week_end', None)
    summary = build_factual_summary(totals, week_start, week_end, locale)

    prepared['summary'] = summary
    prepared['summary_source'] = 'derived'

    # 头部展示用的本地化日期区间与标题：
    # - week_range 走语言感知格式（英文 ISO + en dash，中文「年月日 至 年月日」），
    #   不再由模板硬编码中文 strftime 与「至」连接词；
    # - title_display 只本地化**系统生成的标准标题**，任意 DB 标题原样透传，
    #   数据库里的 report.title 绝不被改写。
    prepared['week_range'] = format_week_range(week_start, week_end, locale)
    prepared['title_display'] = localize_report_title(getattr(report, 'title', None), locale)

    return {
        'content': prepared,
        'summary': summary,
        'summary_source': 'derived',
        'totals': totals,
    }
