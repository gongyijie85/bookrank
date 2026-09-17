"""CSRF 令牌「一次性」语义回归测试（安全审计 Medium #4 的 4b 面）。

服务端 `@csrf_protect` 在校验通过后立即删除令牌记录
（`app/utils/api_helpers.py:214-222`），即令牌为一次性。

这组测试锁定两件事：

1. **安全面**：同一令牌不能用于第二次变更请求（防重放，1 小时 TTL 内的
   重放窗口被消除）。
2. **契约面**：客户端必须在每次变更后重新获取令牌。移动端曾违反此契约
   （`static/mobile/js/mobile.js` 永久缓存令牌），导致「我的收藏」页
   删第一个成功、之后全部 403。该问题的根因即本文件所锁定的服务端语义。

注：`csrf_protect` 在 TESTING 下会被短路，因此测试需临时关闭 TESTING
才能走到真实校验路径（与 test_admin_csrf_regression.py 一致）。
"""

import pytest

from app.utils.api_helpers import get_csrf_token

CSRF_ENDPOINT = '/api/admin/reports/clean-brackets'


@pytest.fixture
def enforce_security(app):
    """临时关闭 TESTING，使 csrf_protect 走真实校验路径（autouse 会在测试后还原）。"""
    saved = app.config['TESTING']
    app.config['TESTING'] = False
    yield app
    app.config['TESTING'] = saved


def _new_token(target_app):
    with target_app.app_context():
        return get_csrf_token()


def _is_csrf_rejected(response) -> bool:
    return response.status_code == 403 and 'csrf' in response.get_data(as_text=True).lower()


def test_token_is_consumed_after_one_use(client, admin_headers, enforce_security, db):
    """同一令牌第二次用于变更请求必须被拒——一次性语义（防重放）。"""
    token = _new_token(enforce_security)
    headers = dict(admin_headers)
    headers['X-CSRF-Token'] = token

    first = client.post(CSRF_ENDPOINT, json={'dry_run': True}, headers=headers)
    assert not _is_csrf_rejected(first), '首次使用有效令牌不应被 CSRF 拒绝'

    second = client.post(CSRF_ENDPOINT, json={'dry_run': True}, headers=headers)
    assert _is_csrf_rejected(second), '同一令牌第二次使用必须被拒（令牌应已被消费）'


def test_fresh_token_per_request_keeps_working(client, admin_headers, enforce_security, db):
    """每次请求前重新获取令牌即可连续成功——即客户端应遵循的正确用法。"""
    for attempt in range(3):
        headers = dict(admin_headers)
        headers['X-CSRF-Token'] = _new_token(enforce_security)

        response = client.post(CSRF_ENDPOINT, json={'dry_run': True}, headers=headers)

        assert not _is_csrf_rejected(response), f'第 {attempt + 1} 次请求使用了新令牌，不应被拒'
