import logging
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any, overload

from flask import current_app, jsonify, request
from werkzeug.wrappers import Response

from ..models.database import db
from ..models.schemas import CSRFToken
from .error_handler import ErrorCategory, log_error
from .exceptions import (
    APIRateLimitException,
    BookRankException,
    DataNotFoundError,
    ExternalAPIError,
    ValidationException,
)
from .rate_limiter import get_rate_limiter

_logger = logging.getLogger(__name__)

_CSRF_TOKEN_TTL = 3600


def _cleanup_expired_csrf_tokens() -> None:
    try:
        cutoff = datetime.now(UTC) - timedelta(seconds=_CSRF_TOKEN_TTL)
        CSRFToken.query.filter(CSRFToken.created_at < cutoff).delete()
        db.session.commit()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'清理过期CSRF token失败: {e}')
        db.session.rollback()


class APIResponse:
    """统一API响应格式"""

    @staticmethod
    def success(
        data: Any = None,
        message: str = 'Success',
        status_code: int = 200,
        include_timestamp: bool = False,
    ) -> tuple[Response, int]:
        response = {'success': True, 'data': data, 'message': message}
        if include_timestamp:
            response['timestamp'] = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
        return jsonify(response), status_code

    @staticmethod
    def error(
        message: str = 'Error',
        status_code: int = 400,
        errors: list | dict | None = None,
        include_timestamp: bool = False,
    ) -> tuple[Response, int]:
        response = {'success': False, 'message': message}
        if errors:
            response['errors'] = errors
        if include_timestamp:
            response['timestamp'] = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
        return jsonify(response), status_code


def handle_api_errors(f: Callable[..., Any]) -> Callable[..., Any]:
    """统一API异常处理装饰器：捕获自定义异常与常见异常并返回标准格式响应"""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return f(*args, **kwargs)
        except ValidationException as e:
            _logger.warning(f'验证错误 [{f.__name__}]: {e}')
            return APIResponse.error(str(e), 400)
        except DataNotFoundError as e:
            _logger.info(f'数据未找到 [{f.__name__}]: {e}')
            return APIResponse.error(str(e), 404)
        except APIRateLimitException as e:
            _logger.warning(f'限流 [{f.__name__}]: {e}')
            return APIResponse.error(str(e), 429)
        except ExternalAPIError as e:
            _logger.error(f'外部API错误 [{f.__name__}]: {e}')
            return APIResponse.error('外部服务暂时不可用', 503)
        except BookRankException as e:
            e.log()
            return APIResponse.error(str(e), 500)
        except ValueError as e:
            _logger.warning(f'参数错误 [{f.__name__}]: {e}')
            return APIResponse.error(str(e), 400)
        except KeyError as e:
            _logger.warning(f'字段缺失 [{f.__name__}]: {e}')
            return APIResponse.error(f'缺少必要字段: {e}', 400)
        except PermissionError as e:
            _logger.warning(f'权限不足 [{f.__name__}]: {e}')
            return APIResponse.error(str(e), 403)
        except FileNotFoundError as e:
            _logger.warning(f'文件未找到 [{f.__name__}]: {e}')
            return APIResponse.error(str(e), 404)
        except ConnectionError as e:
            _logger.error(f'外部服务连接失败 [{f.__name__}]: {e}')
            return APIResponse.error('外部服务暂时不可用，请稍后重试', 503)
        except TimeoutError as e:
            _logger.error(f'请求超时 [{f.__name__}]: {e}')
            return APIResponse.error('请求超时，请稍后重试', 504)
        except Exception as e:
            _logger.error(f'未预期的错误 [{f.__name__}]: {e}', exc_info=True)
            return APIResponse.error('服务器内部错误，请稍后重试', 500)

    return wrapped


def validate_isbn(value: str | None) -> bool:
    """验证ISBN格式（ISBN-10 或 ISBN-13，严格校验978/979前缀）"""
    if not value:
        return False
    clean = re.sub(r'[\s\-]', '', value)
    if len(clean) == 13 and clean.startswith(('978', '979')) and clean.isdigit():
        return True
    if len(clean) == 10:
        prefix = clean[:9]
        suffix = clean[9]
        if prefix.isdigit() and (suffix.isdigit() or suffix.upper() == 'X'):
            return True
    return False


def validate_pagination(page: int, limit: int, max_limit: int = 50) -> tuple[int, int]:
    """验证并规范化分页参数"""
    page = min(max(1, page), 10000)
    limit = min(max(1, limit), max_limit)
    return page, limit


def rate_limit(
    max_requests: int = 60,
    window: int = 60,
    response_cls: type[APIResponse] = APIResponse,
) -> Callable[..., Any]:
    """API限流装饰器"""

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if current_app.config.get('TESTING'):
                return f(*args, **kwargs)

            limiter = get_rate_limiter(max_requests, window)
            client_id = request.remote_addr or 'unknown'

            if not limiter.is_allowed(client_id):
                retry_after = limiter.get_retry_after(client_id)
                return response_cls.error(f'Rate limit exceeded. Retry after {retry_after}s.', 429)

            return f(*args, **kwargs)

        return wrapped

    return decorator


def get_csrf_token() -> str:
    token = secrets.token_hex(32)
    try:
        db.session.add(CSRFToken(token=token))
        db.session.commit()
        token_count = CSRFToken.query.count()
        if token_count % 100 == 0:
            _cleanup_expired_csrf_tokens()
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'CSRF token 创建失败: {e}')
        db.session.rollback()
    return token


def validate_csrf_token() -> bool:
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token:
        return False
    try:
        record = db.session.get(CSRFToken, token)
        if record is None:
            return False
        if record.created_at.tzinfo is None:
            created_at_utc = record.created_at.replace(tzinfo=UTC)
        else:
            created_at_utc = record.created_at
        if datetime.now(UTC) - created_at_utc > timedelta(seconds=_CSRF_TOKEN_TTL):
            db.session.delete(record)
            db.session.commit()
            return False
        return True
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'CSRF token 验证失败: {e}')
        db.session.rollback()
        return False


def csrf_protect(f: Callable[..., Any]) -> Callable[..., Any]:

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if current_app.config.get('TESTING'):
            return f(*args, **kwargs)

        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            if not validate_csrf_token():
                _logger.warning(f'CSRF验证失败: {request.remote_addr}')
                return APIResponse.error('CSRF token invalid', 403)
            if token:
                try:
                    record = db.session.get(CSRFToken, token)
                    if record:
                        db.session.delete(record)
                        db.session.commit()
                except Exception as e:
                    log_error(ErrorCategory.DB_QUERY, f'CSRF token 删除失败: {e}')
                    db.session.rollback()
        return f(*args, **kwargs)

    return wrapped


_DIRTY_MARKERS = (
    '书名：',
    '作者：',
    '简介：',
    '描述：',
    '详情：',
    '出版社：',
    'Title:',
    'Author:',
    'Description:',
    'Summary:',
    'Details:',
    'Publisher:',
    '翻译：',
    '译文：',
    '**',
    '__',
    '`',
)

_FIELD_LABELS_MAP = {
    'title': {
        'start': ['书名', 'Title', 'Book Title', 'Translated Title'],
        'end': ['作者', '简介', '描述', '详情', '出版社', 'Author', 'Description', 'Summary', 'Details', 'Publisher'],
    },
    'description': {
        'start': ['简介', '描述', 'Description', 'Summary'],
        'end': ['书名', '作者', '详情', '出版社', 'Title', 'Author', 'Details', 'Publisher'],
    },
    'details': {
        'start': ['详情', '描述', 'Details', 'Description'],
        'end': ['书名', '作者', '简介', '出版社', 'Title', 'Author', 'Summary', 'Publisher'],
    },
}

_FIELD_PREFIX_PATTERNS = [
    r'(?:^|\s)书名[：:]\s*',
    r'(?:^|\s)作者[：:]\s*',
    r'(?:^|\s)简介[：:]\s*',
    r'(?:^|\s)描述[：:]\s*',
    r'(?:^|\s)详情[：:]\s*',
    r'(?:^|\s)出版社[：:]\s*',
    r'(?:^|\s)Title[：:]\s*',
    r'(?:^|\s)Author[：:]\s*',
    r'(?:^|\s)Description[：:]\s*',
    r'(?:^|\s)Summary[：:]\s*',
    r'(?:^|\s)Details[：:]\s*',
    r'(?:^|\s)Publisher[：:]\s*',
    r'(?:^|\s)Book Title[：:]\s*',
    r'(?:^|\s)Translated Title[：:]\s*',
]


def _extract_field_content(text: str, field_type: str) -> str:
    """从多字段文本中提取指定字段内容（从起始标签到结束标签之间）"""
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


def _clean_title_text(text: str) -> str:
    """清理书名中混入的作者名、描述等多余内容

    处理以下污染模式：
    - "作者名 · 《书名》" → "《书名》"
    - "书名 作者名译" → 纯书名
    - "《书名》作者名 描述文本..." → "《书名》"
    - "书名\n作者名" → 纯书名
    注意：新提示词要求输出纯文字书名（不加《》），此处仅清理污染，不再自动添加《》
    """
    if not text:
        return text
    text = text.strip()

    book_match = re.search(r'《([^》\n]+)》', text)
    if book_match:
        return book_match.group(1).strip()

    if '\n' in text:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if len(lines) >= 2:
            first_line = lines[0]
            if len(first_line) <= 20 and '·' not in first_line:
                return first_line

    if '·' in text:
        parts = re.split(r'\s*·\s*', text.replace('\n', ' '))
        candidates = [p.strip() for p in parts if '·' not in p and len(p.strip()) <= 20]
        if candidates:
            return candidates[0]

    text_flat = text.replace('\n', ' ').strip()
    text_flat = re.sub(r'\s+[\u4e00-\u9fff]{1,4}(?:·[\u4e00-\u9fff]{1,4})*译?\s*$', '', text_flat).strip()

    desc_match = re.search(r'[。，；](?:这本书|作者|该书|本书)', text_flat)
    if desc_match and desc_match.start() > 2:
        text_flat = text_flat[: desc_match.start()].strip()

    return text_flat


def _strip_markdown(text: str) -> str:
    """清除Markdown格式标记（粗体、斜体、代码、标题、链接等）"""
    if not text:
        return text
    # 粗体 **text** 或 __text__
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    # 斜体 *text* 或 _text_（避免误删下划线命名）
    text = re.sub(r'(?<!\w)\*([^\*]+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'\1', text)
    # 行内代码 `text`
    text = re.sub(r'`([^`]+?)`', r'\1', text)
    # 标题 # text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 链接 [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 图片 ![text](url) -> 空
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
    # 水平线 --- 或 ***
    text = re.sub(r'^[\-\*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # 引用 > text
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    return text.strip()


@overload
def clean_translation_text(text: None, field_type: str = 'text') -> None: ...


@overload
def clean_translation_text(text: str, field_type: str = 'text') -> str: ...


def clean_translation_text(text: str | None, field_type: str = 'text') -> str | None:
    """权威翻译文本后处理函数：去AI污染标记、清除Markdown、字段提取、统一引号、书名号"""
    if not text:
        return text
    text = text.strip()
    # 清除翻译前缀
    prefixes = ['翻译：', '译文：', '中文翻译：', '翻译结果：']
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    # 清除Markdown格式
    text = _strip_markdown(text)
    # 清除残留的单个星号（兜底）
    text = text.replace('*', '')
    # 清除末尾的"译"字后缀（GLM模型翻译标记残留，如"希望升起译"）
    text = re.sub(r'[\s]*译$', '', text)
    text = re.sub(r'[\s]*\[译\]$', '', text)
    text = re.sub(r'[\s]*\(译\)$', '', text)
    # 提取字段内容
    if field_type in _FIELD_LABELS_MAP:
        text = _extract_field_content(text, field_type)
    for pattern in _FIELD_PREFIX_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    if field_type == 'title':
        text = _clean_title_text(text)
    # 清除空行
    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text


@overload
def quick_clean_translation(text: None, field_type: str = 'text') -> None: ...


@overload
def quick_clean_translation(text: str, field_type: str = 'text') -> str: ...


def quick_clean_translation(text: str | None, field_type: str = 'text') -> str | None:
    """快速清理翻译文本（带脏数据检测，干净文本直接返回）"""
    if not text:
        return text
    if any(marker in text for marker in _DIRTY_MARKERS):
        return clean_translation_text(text, field_type)
    if re.search(r'[\s]*(?:译|\[译\]|\(译\))\s*$', text):
        return clean_translation_text(text, field_type)
    return text


# 语言标记 / 占位符类噪音：这些取值没有内容信息，不应写入 details_zh。
# 实测语言包里 88 条 details_zh 就是「原文语言名」本身（'英文' 77 / '- 英文' 9 / '小说' 2），
# 占 details 有值条的 31%，其中 32 本当时正在榜上，页面会渲染出「详情: 英文」。
# 长度分布佐证：>30 字的 details_zh 全部正常，<=5 字的 88 条全部是噪音，
# 两者之间只有 2 条正常值 —— 因此用显式集合判定，不做长度裁剪。
#
# 边界说明：这里与 PLACEHOLDER_TEXTS 有 3 个取值重叠（'暂无详细描述' / '暂无简介' / 'N/A'），
# 但两者是**不同概念** —— 本集合是「无信息量的语言标记 + 噪音词」，PLACEHOLDER_TEXTS 是
# 「抓取侧『没有内容』的占位串」。刻意不合并，避免把两套语义揉成一个。
_NON_SUBSTANTIVE_DETAILS = frozenset(
    {
        '英文',
        '英语',
        '中文',
        '汉语',
        '- 英文',
        '-英文',
        '英文。',
        '英语。',
        '小说',
        '非虚构',
        '暂无详细描述',
        '暂无简介',
        '无',
        '-',
        '--',
        'N/A',
    }
)


def is_non_substantive_details(text: str | None) -> bool:
    """判断 details / details_zh 是否为无信息量的语言标记或占位符。

    已在两处写入路径生效：BookLanguagePack.translate_and_store_books 拒收
    details_zh，scripts/sync_book_language_pack._merge_book 拒收上游合并值。
    只匹配显式集合，正常详情（含短句「最初由Viking Penguin于2014年出版。」）不受影响。
    """
    if not text:
        return False
    return text.strip() in _NON_SUBSTANTIVE_DETAILS


# 占位串的**单一真相源** —— 全仓只此一份字面量清单。
#
# 这些取值语义上等于 NULL，不是数据。抓取侧（Google Books / Open Library）拿不到内容时会写回
# 它们，而写入边界若把「默认值」直接落库，就会出现两个后果：
#   1. 展示侧把占位串当正文渲染出来；
#   2. 更隐蔽的：**「有值即已补全」** —— 例如 book_detail_service 的
#      `needs_details = details 有值 and != 占位串` 会因此恒为假，该字段的补齐/翻译路径
#      被永久封死，页面表现为「内容整块消失」。
#
# 使用方式（新代码一律走这两个入口，不要再写第二份清单）：
#   - 写入边界归一化：`strip_placeholder(text)`
#   - 判定：`is_placeholder_text(text)`
#   - 模板：注入的 Jinja 全局 `PLACEHOLDER_TEXTS`（见 app/__init__.py 注册处）
#   - 前端 JS 无法 import Python：`static/mobile/js/mobile.js` 保留一份镜像，
#     由 `tests/test_placeholder_single_source.py` 断言与这里完全一致，漂移即红。
PLACEHOLDER_TEXTS = frozenset(
    {
        # 抓取侧英文
        'No summary available.',
        'No summary available',
        'No detailed description available.',
        'No description available.',
        # 抓取侧中文
        '暂无简介',
        '暂无详细介绍',
        '暂无详细描述',
        # 通用「无值」标记：语言包/元数据表在这三类字段上共用的取值
        'Unknown',
        'N/A',
        'None',
    }
)

#: 兼容旧名（模块内与历史引用）。
_PLACEHOLDER_TEXTS = PLACEHOLDER_TEXTS


def is_placeholder_text(text: str | None) -> bool:
    """文本是否为抓取侧的「没有内容」占位串（语义上等于 NULL）。"""
    if not isinstance(text, str):
        return False
    return text.strip() in PLACEHOLDER_TEXTS


def strip_placeholder(text: str | None) -> str:
    """把占位串归一化为空串，供写入边界使用（其它取值原样保留并去首尾空白）。

    非字符串输入一律归一化为空串：这两个字段（description/details）只接受文本，
    放行 None/数字只会把类型问题推迟到展示层。
    """
    if not isinstance(text, str):
        return ''
    value = text.strip()
    return '' if value in PLACEHOLDER_TEXTS else value


def target_lang_expects_cjk(target_lang: str) -> bool:
    """目标语言是否为中文（据此判断译文里是否应当出现汉字）。

    接受 'zh'、'zh-CN'、'zh-Hans' 等写法，与 translate 的调用方保持一致。
    """
    return (target_lang or '').strip().lower().split('-')[0] == 'zh'


def is_english_echo(source: str, translated: str, target_lang: str) -> bool:
    """判断译文是否是模型把原文原样回显。

    实测该模型会把个别短文本原样返回（SCION → "SCION"/"Scion"）。这类坏值若写入
    translation_cache 会自我固化：后续请求命中缓存直接拿到英文，书名永远补不上。
    只在「目标语言是中文、原文含拉丁字母、译文里一个汉字都没有」时判定为回显，
    因此不会误伤品牌名/数字/纯符号等本身无需翻译的文本。
    """
    if not target_lang_expects_cjk(target_lang):
        return False
    src = (source or '').strip()
    dst = (translated or '').strip()
    if not src or not dst:
        return False
    if not any('a' <= ch.lower() <= 'z' for ch in src):
        return False
    return not any('\u4e00' <= ch <= '\u9fff' for ch in dst)
