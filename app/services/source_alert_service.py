"""GitHub issue alerts when a source is degraded (#139 / #121)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from ..models.database import db
from ..models.schemas import SystemConfig

logger = logging.getLogger(__name__)

_ISSUE_MAP_KEY = 'source_degraded_issue_map'


class GithubIssuesClient(Protocol):
    def find_open_by_title(self, title: str) -> dict[str, Any] | None: ...

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]: ...

    def update_issue(self, number: int, body: str) -> None: ...

    def add_comment(self, number: int, body: str) -> None: ...

    def close_issue(self, number: int, comment: str | None = None) -> None: ...


class NullGithubClient:
    """No-op client when GitHub token/repo is not configured."""

    def find_open_by_title(self, title: str) -> dict[str, Any] | None:
        return None

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        logger.info('GitHub alert skipped (not configured): %s', title)
        return {'number': 0, 'title': title, 'body': body, 'state': 'open'}

    def update_issue(self, number: int, body: str) -> None:
        return None

    def add_comment(self, number: int, body: str) -> None:
        return None

    def close_issue(self, number: int, comment: str | None = None) -> None:
        return None


class UrllibGithubClient:
    """Minimal Issues API client using GITHUB_TOKEN — never needs BATCH_IMPORT_SECRET."""

    def __init__(self, token: str, repository: str) -> None:
        self._token = token
        self._repo = repository
        self._api = f'https://api.github.com/repos/{repository}'

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f'{self._api}{path}',
            data=data,
            method=method,
            headers={
                'Authorization': f'Bearer {self._token}',
                'Accept': 'application/vnd.github+json',
                'Content-Type': 'application/json',
                'User-Agent': 'bookrank-source-alert',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode('utf-8')
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            logger.warning('GitHub API %s %s failed: %s %s', method, path, exc.code, detail[:300])
            raise

    def find_open_by_title(self, title: str) -> dict[str, Any] | None:
        issues = self._request('GET', '/issues?state=open&per_page=50')
        if not isinstance(issues, list):
            return None
        for issue in issues:
            if isinstance(issue, dict) and issue.get('title') == title and 'pull_request' not in issue:
                return issue
        return None

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {'title': title, 'body': body}
        if labels:
            payload['labels'] = labels
        created = self._request('POST', '/issues', payload)
        return created if isinstance(created, dict) else {'number': 0, 'title': title, 'body': body}

    def update_issue(self, number: int, body: str) -> None:
        self._request('PATCH', f'/issues/{number}', {'body': body})

    def add_comment(self, number: int, body: str) -> None:
        self._request('POST', f'/issues/{number}/comments', {'body': body})

    def close_issue(self, number: int, comment: str | None = None) -> None:
        if comment:
            self.add_comment(number, comment)
        self._request('PATCH', f'/issues/{number}', {'state': 'closed'})


def get_github_client() -> GithubIssuesClient:
    token = os.environ.get('GITHUB_ALERT_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    repo = os.environ.get('GITHUB_REPOSITORY') or ''
    if not token or not repo:
        return NullGithubClient()
    return UrllibGithubClient(token=token, repository=repo)


def alert_title(source_id: str) -> str:
    return f'[source-degraded] {source_id.lower()}'


def sync_degraded_alert(source_id: str, publisher: Any) -> dict[str, Any] | None:
    """Create or update the stable-title degraded issue (idempotent)."""
    if publisher.source_status != 'degraded':
        return None
    client = get_github_client()
    title = alert_title(source_id)
    body = _render_body(source_id, publisher)
    mapped = _load_issue_map()
    number = mapped.get(source_id.lower())

    existing = client.find_open_by_title(title)
    if existing is not None:
        number = int(existing['number'])
        client.update_issue(number, body)
        # throttle noise: one body update, no extra comment spam
        mapped[source_id.lower()] = number
        _save_issue_map(mapped)
        return existing

    if number:
        # try update known number; if missing, recreate
        try:
            client.update_issue(int(number), body)
            client.add_comment(int(number), '来源仍处于 degraded，已更新状态摘要。')
            return {'number': number, 'title': title, 'state': 'open'}
        except Exception:
            logger.info('previous alert issue %s missing; recreating', number)

    created = client.create_issue(title, body, labels=['source-health'])
    mapped[source_id.lower()] = int(created.get('number') or 0)
    _save_issue_map(mapped)
    return created


def close_degraded_alert(source_id: str, *, recovery_batch_id: str | None) -> None:
    """Close the degraded issue when source becomes healthy (not for disabled)."""
    client = get_github_client()
    title = alert_title(source_id)
    mapped = _load_issue_map()
    number = mapped.get(source_id.lower())
    comment = f'来源已恢复 healthy。{f" 最近成功 batch_id={recovery_batch_id}." if recovery_batch_id else ""}'
    existing = client.find_open_by_title(title)
    if existing is not None:
        client.close_issue(int(existing['number']), comment=comment)
        mapped.pop(source_id.lower(), None)
        _save_issue_map(mapped)
        return
    if number:
        try:
            client.close_issue(int(number), comment=comment)
        except Exception:
            logger.info('could not close alert issue %s', number)
        mapped.pop(source_id.lower(), None)
        _save_issue_map(mapped)


def _render_body(source_id: str, publisher: Any) -> str:
    return (
        f'## 来源降级告警\n\n'
        f'- **source_id**: `{source_id}`\n'
        f'- **status**: `{publisher.source_status}`\n'
        f'- **consecutive_failures**: {publisher.consecutive_failures}\n'
        f'- **last_error_code**: `{publisher.last_error_code or "-"}`\n'
        f'- **last_error_summary**: {publisher.last_error_summary or "-"}\n'
        f'- **last_success_batch_id**: `{publisher.last_success_batch_id or "-"}`（保留，未删除）\n'
        f'- **last_attempt_at**: {publisher.last_attempt_at.isoformat() if publisher.last_attempt_at else "-"}\n'
        f'- **flags**: crawl={publisher.site_crawl_enabled} import={publisher.site_import_enabled} '
        f'display_primary={publisher.site_display_primary} fallback_google={publisher.fallback_google_enabled}\n\n'
        f'### 数据策略\n'
        f'- 失败批次不覆盖上次成功数据。\n'
        f'- 展示回退：关闭 `site_display_primary` 时列表隐藏官网导入卡片；`fallback_google_enabled` 控制 Google 兜底。\n'
        f'- 本告警由 alert 相位 / 健康状态机触发，不持有批次导入密钥。\n'
    )


def _load_issue_map() -> dict[str, int]:
    raw = SystemConfig.get_value(_ISSUE_MAP_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in data.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _save_issue_map(mapping: dict[str, int]) -> None:
    SystemConfig.set_value(_ISSUE_MAP_KEY, json.dumps(mapping), description='source degraded github issue numbers')
    db.session.commit()
