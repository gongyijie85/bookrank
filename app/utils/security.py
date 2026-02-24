import logging
from flask import request, g
from functools import wraps

logger = logging.getLogger(__name__)


def add_security_headers(response):
    """添加安全响应头"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


def security_headers(f):
    """添加安全响应头的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        if hasattr(response, 'headers'):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    return decorated_function


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
        import re
        if not re.match(pattern, value):
            return False, value, f'{field_name} contains invalid characters'
    
    return True, value, None


def sanitize_filename(filename):
    """
    安全地处理文件名
    
    Args:
        filename: 原始文件名
    
    Returns:
        str: 安全的文件名
    """
    import re
    from werkzeug.utils import secure_filename as werkzeug_secure_filename
    
    safe_name = werkzeug_secure_filename(filename)
    
    if not safe_name:
        safe_name = 'unnamed'
    
    return safe_name


def generate_secure_token(length=32):
    """
    生成安全的随机令牌
    
    Args:
        length: 令牌长度
    
    Returns:
        str: 十六进制令牌
    """
    import secrets
    return secrets.token_hex(length)


def mask_sensitive_data(data, visible_chars=4):
    """
    遮蔽敏感数据（如 API 密钥）
    
    Args:
        data: 原始数据
        visible_chars: 可见字符数
    
    Returns:
        str: 遮蔽后的数据
    """
    if not data or len(data) <= visible_chars:
        return '****'
    
    return data[:visible_chars] + '*' * (len(data) - visible_chars)


def is_safe_redirect_url(url, allowed_hosts=None):
    """
    检查重定向 URL 是否安全
    
    Args:
        url: 要检查的 URL
        allowed_hosts: 允许的主机列表
    
    Returns:
        bool: 是否安全
    """
    if not url:
        return False
    
    from urllib.parse import urlparse
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
