from urllib.parse import unquote, urlparse, urlsplit


def is_safe_redirect_url(url: str | None, allowed_hosts: set[str] | None = None) -> bool:
    """检查重定向 URL 是否安全"""
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ('http', 'https'):
        return False
    if url.startswith('//') or '\\' in url:
        return False

    if parsed.netloc:
        return bool(allowed_hosts and parsed.netloc in allowed_hosts)

    return url.startswith('/')


def safe_return_path(value: object, default: str = '/') -> str:
    """Keep an original local path and query, or return default."""
    if not isinstance(value, str) or not value or value[:1].isspace():
        return default
    for char in value:
        code = ord(char)
        if char == '\\' or code < 0x20 or code == 0x7F:
            return default
    try:
        parsed = urlsplit(value)
    except ValueError:
        return default
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return default
    current = parsed.path
    for _ in range(5):
        if (
            not current.startswith('/')
            or current.startswith('//')
            or '\\' in current
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in current)
        ):
            return default
        try:
            examined = urlsplit(current)
        except ValueError:
            return default
        if examined.scheme or examined.netloc or not examined.path.startswith('/') or examined.path.startswith('//'):
            return default
        decoded = unquote(current)
        if decoded == current:
            return value
        current = decoded
    if unquote(current) != current:
        return default
    if (
        not current.startswith('/')
        or current.startswith('//')
        or '\\' in current
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in current)
    ):
        return default
    try:
        examined = urlsplit(current)
    except ValueError:
        return default
    if examined.scheme or examined.netloc or not examined.path.startswith('/') or examined.path.startswith('//'):
        return default
    return value
