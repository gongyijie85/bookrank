"""移动设备检测工具

根据 HTTP 请求的 User-Agent 头判断是否为移动设备，
用于在视图层选择移动版或桌面版模板。
"""
import re

from flask import has_request_context, request

# 移动端 UA 关键词（覆盖主流手机浏览器与平板）
_MOBILE_PATTERN = re.compile(
    r'android|iphone|ipod|windows phone|mobile|blackberry|opera mini|mobile safari',
    re.IGNORECASE,
)


def is_mobile() -> bool:
    """检测当前请求是否来自移动设备。

    Returns:
        True 表示移动端；非请求上下文或桌面端返回 False。
    """
    if not has_request_context():
        return False
    ua = request.headers.get('User-Agent', '')
    return bool(_MOBILE_PATTERN.search(ua))
