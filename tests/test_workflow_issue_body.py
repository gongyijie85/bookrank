"""书榜更新工单正文：保留报告结尾，并守住 12000 字节预算。"""

from scripts.workflow_http import truncate_issue

RUN_LINK = 'https://github.com/gongyijie85/bookrank/actions/runs/1'


def test_truncate_issue_keeps_tail_where_failures_are_printed():
    noise = 'HEAD-ONLY-NOISE\n' + 'INFO sqlalchemy.engine.Engine INSERT INTO award_books ...\n' * 5000
    failure = 'NYT 频率检查失败：HTTPError (HTTP 404)\nNYT 响应体：{"status":"ERROR","errors":["list not found"]}\n'
    report = noise + failure
    body = truncate_issue(report, RUN_LINK)

    assert 'NYT 频率检查失败' in body
    assert 'list not found' in body
    assert 'HEAD-ONLY-NOISE' not in body
    assert '已省略' in body
    assert RUN_LINK in body
    assert len(body.encode('utf-8')) <= 12000
    assert len(body) < len(report)


def test_truncate_issue_keeps_whole_report_when_short():
    report = 'NYT 频率检查失败：HTTPError (HTTP 404)\n'
    body = truncate_issue(report, RUN_LINK)

    assert 'NYT 频率检查失败' in body
    assert RUN_LINK in body


def test_truncate_issue_handles_limit_below_footer():
    body = truncate_issue('x' * 50000, RUN_LINK, limit=60)

    assert RUN_LINK in body
