import re
import secrets
import logging
from urllib.parse import urlparse

from werkzeug.utils import secure_filename as werkzeug_secure_filename

logger = logging.getLogger(__name__)


def validate_input(value, max_length=None, pattern=None, field_name='input'):
    """
    输入验证工具函数

    Args:
        value: 要验证的值
        max_length: 最大长度
        pattern: 正则表达式模式
        field_name: 字段名称（用于错误消息）

    Returns:
        tuple: (is_valid, sanitized_value, error_message)
    """
    if value is None:
        return False, None, f'{field_name} is required'

    value = str(value).strip()

    if not value:
        return False, None, f'{field_name} is required'

    if max_length and len(value) > max_length:
        return False, None, f'{field_name} must be at most {max_length} characters'

    if pattern:
        if not re.match(pattern, value):
            return False, value, f'{field_name} contains invalid characters'

    return True, value, None


def sanitize_filename(filename):
    """安全地处理文件名"""
    safe_name = werkzeug_secure_filename(filename)
    return safe_name or 'unnamed'


def generate_secure_token(length=32):
    """生成安全的随机令牌"""
    return secrets.token_hex(length)


def mask_sensitive_data(data, visible_chars=4):
    """遮蔽敏感数据（如 API 密钥）"""
    if not data or len(data) <= visible_chars:
        return '****'
    return data[:visible_chars] + '*' * (len(data) - visible_chars)


def is_safe_redirect_url(url, allowed_hosts=None):
    """检查重定向 URL 是否安全"""
    if not url:
        return False

    parsed = urlparse(url)

    if allowed_hosts:
        return parsed.netloc in allowed_hosts

    return parsed.scheme in ['http', 'https'] and parsed.netloc


def log_safe(message, **kwargs):
    """安全地记录日志，过滤敏感信息"""
    sensitive_keys = ['password', 'token', 'secret', 'key', 'auth']

    safe_kwargs = {}
    for k, v in kwargs.items():
        if any(s in k.lower() for s in sensitive_keys):
            safe_kwargs[k] = '****'
        else:
            safe_kwargs[k] = v

    logger.info(message, **safe_kwargs)
