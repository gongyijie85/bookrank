"""Regression guard: the daily cron crawl must never write fixture samples.

Bug this locks down (Site Crawl #94 / #98): the scheduled run of
``site-crawl-pipeline.yml`` produced an observation-only batch draft
(``write_enabled=false``) and then unconditionally POSTed it to
``/api/new-books/import-batch``, creating pending_review rows for the two
HarperCollins fixture samples. The ``write_enabled`` flag was never a gate —
the import service does not read it — so the only thing that can stop the
write is the workflow not invoking the import step on a schedule event.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/site-crawl-pipeline.yml'


def _val(token: str, ctx: dict) -> object:
    token = token.strip()
    if token == 'true':
        return True
    if token == 'false':
        return False
    if len(token) >= 2 and token[0] in '\'"' and token[-1] == token[0]:
        return token[1:-1]
    if token in ctx:
        return ctx[token]
    if '.' in token:
        cur: object = ctx
        for part in token.split('.'):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
    return None


def _eval_term(term: str, ctx: dict) -> bool:
    match = re.fullmatch(r'(.+?)\s*(==|!=)\s*(.+)', term.strip())
    if match is None:
        raise AssertionError(f'unsupported if-expression term: {term!r}')
    left, op, right = (g.strip() for g in match.groups())
    lhs, rhs = _val(left, ctx), _val(right, ctx)
    return lhs == rhs if op == '==' else lhs != rhs


def _eval_if(expr: str, ctx: dict) -> bool:
    """Evaluate the small GHA ``if:`` grammar the workflow actually uses."""
    expr = expr.strip()
    if expr.startswith('${{') and expr.endswith('}}'):
        expr = expr[3:-2].strip()
    return any(all(_eval_term(term, ctx) for term in or_term.split('&&')) for or_term in expr.split('||'))


def test_scheduled_crawl_does_not_import_fixture_samples() -> None:
    """A cron-triggered run must build the draft but must NOT import it."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding='utf-8'))
    import_job = workflow['jobs']['import']
    condition = str(import_job.get('if', ''))

    schedule_ctx = {'github': {'event_name': 'schedule'}, 'inputs': {}}
    would_import = _eval_if(condition, schedule_ctx) if condition else True

    assert not would_import, (
        'cron site-crawl run would POST the observation-only fixture draft to '
        '/api/new-books/import-batch and create pending_review rows '
        '(Site Crawl #94 / #98); import must be gated to manual dispatch only'
    )


def test_manual_dispatch_can_still_import_when_not_skipped() -> None:
    """Keep the deliberate demo path: manual dispatch with import enabled."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding='utf-8'))
    import_job = workflow['jobs']['import']
    condition = str(import_job.get('if', ''))

    manual_ctx = {
        'github': {'event_name': 'workflow_dispatch'},
        'inputs': {'skip_import': False},
    }
    assert condition and _eval_if(condition, manual_ctx), (
        'manual dispatch with skip_import=false must still be able to import the fixture batch (the demo path)'
    )


def test_observe_job_has_no_import_secret() -> None:
    """The observe phase must stay write-free (no BATCH_IMPORT_SECRET)."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding='utf-8'))
    observe_env = workflow['jobs']['observe'].get('env', {})
    assert 'BATCH_IMPORT_SECRET' not in observe_env
