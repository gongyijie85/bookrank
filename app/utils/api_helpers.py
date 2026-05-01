import re
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, request, session, current_app

from .rate_limiter import get_rate_limiter

_logger = logging.getLogger(__name__)


class APIResponse:
    """统一API响应格式"""

    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message
        }
        return jsonify(response), status_code

    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


class PublicAPIResponse:
    """公开API响应格式（带时间戳）"""

    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        return jsonify(response), status_code

    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


def handle_api_errors(f):
    """统一API异常处理装饰器：捕获常见异常并返回标准格式响应"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            _logger.warning(f"参数错误 [{f.__name__}]: {e}")
            return APIResponse.error(str(e), 400)
        except KeyError as e:
            _logger.warning(f"字段缺失 [{f.__name__}]: {e}")
            return APIResponse.error(f'缺少必要字段: {e}', 400)
        except PermissionError as e:
            _logger.warning(f"权限不足 [{f.__name__}]: {e}")
            return APIResponse.error(str(e), 403)
        except FileNotFoundError as e:
            _logger.warning(f"文件未找到 [{f.__name__}]: {e}")
            return APIResponse.error(str(e), 404)
        except ConnectionError as e:
            _logger.error(f"外部服务连接失败 [{f.__name__}]: {e}")
            return APIResponse.error('外部服务暂时不可用，请稍后重试', 503)
        except TimeoutError as e:
            _logger.error(f"请求超时 [{f.__name__}]: {e}")
            return APIResponse.error('请求超时，请稍后重试', 504)
        except Exception as e:
            _logger.error(f"未预期的错误 [{f.__name__}]: {e}", exc_info=True)
            return APIResponse.error('服务器内部错误，请稍后重试', 500)
    return wrapped


def validate_isbn(isbn: str) -> bool:
    """验证ISBN格式（ISBN-10 或 ISBN-13）"""
    if not isbn:
        return False
    clean_isbn = re.sub(r'[^0-9X]', '', isbn.upper())
    if len(clean_isbn) == 10:
        return bool(re.match(r'^\d{9}[\dX]$', clean_isbn))
    elif len(clean_isbn) == 13:
        return bool(re.match(r'^\d{13}$', clean_isbn))
    return False


def validate_pagination(page: int, limit: int, max_limit: int = 50) -> tuple[int, int]:
    """验证并规范化分页参数"""
    page = min(max(1, page), 10000)
    limit = min(max(1, limit), max_limit)
    return page, limit


def api_rate_limit(max_requests: int = 60, window: int = 60):
    """API限流装饰器"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limiter = get_rate_limiter(max_requests, window)
            client_id = request.remote_addr or 'unknown'

            if not limiter.is_allowed(client_id):
                retry_after = limiter.get_retry_after(client_id)
                return APIResponse.error(
                    f'Rate limit exceeded. Retry after {retry_after}s.',
                    429
                )

            return f(*args, **kwargs)
        return wrapped
    return decorator


def public_rate_limit(max_requests: int = 60, window: int = 60):
    """公开API限流装饰器"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limiter = get_rate_limiter(max_requests, window)
            client_id = request.remote_addr or 'unknown'

            if not limiter.is_allowed(client_id):
                retry_after = limiter.get_retry_after(client_id)
                return PublicAPIResponse.error(
                    f'Rate limit exceeded. Retry after {retry_after}s.',
                    429
                )

            return f(*args, **kwargs)
        return wrapped
    return decorator


def get_csrf_token() -> str:
    """获取或生成CSRF令牌"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf_token() -> bool:
    """验证CSRF令牌"""
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token:
        return False
    return secrets.compare_digest(token, session.get('csrf_token', ''))


def csrf_protect(f):
    """CSRF保护装饰器"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if current_app.config.get('TESTING'):
            return f(*args, **kwargs)

        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if not validate_csrf_token():
                _logger.warning(f"CSRF验证失败: {request.remote_addr}")
                return APIResponse.error('CSRF token invalid', 403)
        return f(*args, **kwargs)
    return wrapped


_DIRTY_MARKERS = ('书名', '作者', '简介', '描述', '详情', '出版社',
                  'Title:', 'Author:', 'Description:', 'Summary:', 'Details:', 'Publisher:',
                  '翻译：', '译文：', '**', '__', '`')

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


def _clean_title_text(text: str) -> str:
    """清理书名中混入的作者名、描述等多余内容

    处理以下污染模式：
    - "作者名 · 《书名》" → "《书名》"
    - "书名 作者名译" → "《书名》"
    - "《书名》作者名 描述文本..." → "《书名》"
    - "书名\n作者名" → "《书名》"
    """
    if not text:
        return text
    text = text.strip()

    # 模式1：文本中已有《》，提取《》内容
    book_match = re.search(r'《([^》\n]+)》', text)
    if book_match:
        return f'《{book_match.group(1).strip()}》'

    # 模式2：多行文本，第一行是书名，后续行是作者/描述
    if '\n' in text:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) >= 2:
            first_line = lines[0]
            # 第一行较短（<20字符）且不含间隔号，大概率是书名
            if len(first_line) <= 20 and '·' not in first_line:
                return _add_book_title_marks(first_line)

    # 模式3：含间隔号 · 的作者名混入
    if '·' in text:
        # 先尝试在间隔号处分割
        parts = re.split(r'\s*·\s*', text.replace('\n', ' '))
        # 取不含间隔号且较短的部分作为书名
        candidates = [p.strip() for p in parts if '·' not in p and len(p.strip()) <= 20]
        if candidates:
            return _add_book_title_marks(candidates[0])

    # 模式4：末尾有中文名+可选"译"后缀
    text_flat = text.replace('\n', ' ').strip()
    text_flat = re.sub(r'\s+[\u4e00-\u9fff]{1,4}(?:·[\u4e00-\u9fff]{1,4})*译?\s*$', '', text_flat).strip()

    # 模式5：书名后跟长描述
    desc_match = re.search(r'[。，；](?:这本书|作者|该书|本书)', text_flat)
    if desc_match and desc_match.start() > 2:
        text_flat = text_flat[:desc_match.start()].strip()

    return _add_book_title_marks(text_flat)


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


def clean_translation_text(text: str, field_type: str = 'text') -> str:
    """权威翻译文本后处理函数：去AI污染标记、清除Markdown、字段提取、统一引号、书名号"""
    if not text:
        return text
    text = text.strip()
    # 清除翻译前缀
    prefixes = ['翻译：', '译文：', '中文翻译：', '翻译结果：']
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
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
    # 统一引号
    text = text.replace('\u201c', '\u201c').replace('\u201d', '\u201d')
    text = text.replace('\u2018', '\u2018').replace('\u2019', '\u2019')
    if field_type == 'title':
        text = _clean_title_text(text)
    # 清除空行
    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text


def quick_clean_translation(text: str, field_type: str = 'text') -> str:
    """快速清理翻译文本（带脏数据检测，干净文本直接返回）"""
    if not text:
        return text
    if any(marker in text for marker in _DIRTY_MARKERS):
        return clean_translation_text(text, field_type)
    if re.search(r'[\s]*(?:译|\[译\]|\(译\))\s*$', text):
        return clean_translation_text(text, field_type)
    return text
