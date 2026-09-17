"""CSRF 回归测试：确认 3 个管理员 POST 端点强制校验 CSRF 令牌（安全审计 High #1）。

覆盖端点：
- POST /api/admin/reports/clean-brackets
- POST /api/admin/reports/fix-truncated-titles
- POST /api/admin/translations/cleanup

csrf_protect 在 TESTING 模式下被短路，因此本测试临时关闭 TESTING 以验证真实行为，
防止 @csrf_protect 被意外移除（即便已通过 X-Admin-Secret 鉴权，无 CSRF 令牌仍须 403）。
"""

import pytest

# 安全审计 High #1 要求强制 CSRF 的管理员 POST 端点
CSRF_PROTECTED_ENDPOINTS = [
    '/api/admin/reports/clean-brackets',
    '/api/admin/reports/fix-truncated-titles',
    '/api/admin/translations/cleanup',
]


@pytest.fixture
def enforce_security(app):
    """临时关闭 TESTING，使 csrf_protect 走真实校验路径（autouse 会在测试后还原）。"""
    saved = app.config['TESTING']
    app.config['TESTING'] = False
    yield app
    app.config['TESTING'] = saved


@pytest.mark.parametrize('endpoint', CSRF_PROTECTED_ENDPOINTS)
def test_admin_post_rejects_without_csrf_token(client, admin_headers, enforce_security, endpoint):
    """无 CSRF 令牌的 POST 必须返回 403（CSRF token invalid），即便已通过 X-Admin-Secret 鉴权。"""
    response = client.post(endpoint, json={'dry_run': True}, headers=admin_headers)
    assert response.status_code == 403
    assert 'csrf' in response.get_data(as_text=True).lower()


@pytest.mark.parametrize('endpoint', CSRF_PROTECTED_ENDPOINTS)
def test_admin_post_accepts_valid_csrf_token(client, admin_headers, enforce_security, db, endpoint):
    """带有效 CSRF 令牌 + 管理员密钥的 POST 不应因 CSRF 被拒（放行至端点业务逻辑）。"""
    from app.utils.api_helpers import get_csrf_token

    with enforce_security.app_context():
        token = get_csrf_token()

    headers = dict(admin_headers)
    headers['X-CSRF-Token'] = token
    response = client.post(endpoint, json={'dry_run': True}, headers=headers)

    # 只断言 CSRF 层已放行：既非 403，也不含 CSRF 错误文案。
    body = response.get_data(as_text=True).lower()
    assert response.status_code != 403 or 'csrf' not in body
