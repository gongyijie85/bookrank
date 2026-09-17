from urllib.parse import urlparse


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
