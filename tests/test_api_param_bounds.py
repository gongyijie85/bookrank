"""参数下限与限流 key 的回归（对应代码审查里的 #3/#5/#7 三条）。

`min(request.args.get('limit', N, type=int), CAP)` 少了 `max(1, …)` 下限：
`?limit=-1` 会一路传到 `.limit(-1)` —— Postgres 直接报 "LIMIT must not be negative"
（匿名可达端点上的 500），SQLite 则把负数 LIMIT 当成"无上限"读全表。同仓的
api/cache.py、api/recommendations.py、api/translation.py 一直是对的，这几处是漏写。

导出冷却此前以原始 X-Forwarded-For 的第一段为 key，那是客户端可伪造的：每次换一个值
就是全新的一桶，10 秒冷却形同不存在。
"""

from app.routes import new_books


def test_negative_limit_is_clamped_to_one(client, monkeypatch):
    from app.services.user_service import UserService

    seen = {}

    def fake_history(self, session_id, limit):  # capturing stub
        seen['limit'] = limit
        return []

    monkeypatch.setattr(UserService, 'get_search_history', fake_history)
    resp = client.get('/api/search/history?limit=-1')
    assert resp.status_code == 200, resp.get_json()
    assert seen['limit'] == 1, f'?limit=-1 未被夹到下限：{seen["limit"]}'

    client.get('/api/search/history?limit=9999')
    assert seen['limit'] == 20, '上限仍在生效'


def test_export_csv_is_rate_limited_like_its_data_twin():
    """/export/csv 与 /api/public 上是同一批数据、同样匿名可达，必须挂同一道限流。

    `rate_limit` 用 `functools.wraps`，会在被包装函数上留下 `__wrapped__`；该路由此前
    除路由装饰器外没有任何包装，所以据此可钉住"限流挂上了"。对照一个本就无限流的页面端点，
    避免这个断言变成恒真。
    """
    assert hasattr(new_books.export_csv, '__wrapped__'), '/export/csv 未挂 rate_limit'
    assert not hasattr(new_books.get_new_books, '__wrapped__'), '对照端点意外被包装，判据失效'


def test_export_cooldown_key_ignores_forged_forwarded_header(app, monkeypatch):
    keys = []

    class _Gate:
        def export_cooldown_remaining(self, ip):
            keys.append(ip)
            return None

    monkeypatch.setattr(new_books, 'get_sync_request_gate', lambda: _Gate())
    with app.test_request_context(
        '/api/new-books/export/csv',
        environ_base={'REMOTE_ADDR': '203.0.113.7'},
        headers={'X-Forwarded-For': '1.1.1.1, 2.2.2.2', 'User-Agent': 'probe'},
    ):
        assert new_books._check_export_cooldown() is None

    assert keys == ['203.0.113.7'], f'冷却 key 应是 remote_addr（由 ProxyFix 改写），实际 {keys}'
    assert all('1.1.1.1' not in k for k in keys), '伪造的 X-Forwarded-For 又成了限流 key'
