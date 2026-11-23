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

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
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


@pytest.mark.parametrize('skip_import', [False, True], ids=['import', 'observe-only'])
def test_manual_dispatch_respects_skip_import(skip_import) -> None:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding='utf-8'))
    import_job = workflow['jobs']['import']
    condition = str(import_job.get('if', ''))

    manual_ctx = {
        'github': {'event_name': 'workflow_dispatch'},
        'inputs': {'skip_import': skip_import},
    }
    assert condition and _eval_if(condition, manual_ctx) is (not skip_import)


@pytest.mark.parametrize(('job', 'attempts'), [('wake-and-auto-sync', 2), ('import', 2), ('alert', 1)])
def test_curl_timeout_handling(job, attempts, tmp_path):
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding='utf-8'))
    script = workflow['jobs'][job]['steps'][-1]['run']
    # Windows CI/development uses Git Bash, not the WSL launcher in System32.
    git = shutil.which('git')
    bash = Path(git).resolve().parents[1] / 'bin/bash.exe' if os.name == 'nt' and git else shutil.which('bash')
    if not bash or not Path(bash).is_file():
        pytest.skip('Bash is required to execute the workflow step')
    (tmp_path / 'drafts').mkdir()
    (tmp_path / 'drafts/source-batch-draft.json').write_text('{}')
    stub = """
ADMIN_SECRET=test
curl() {
    echo attempt >> attempts
    if [ ! -f timed_out ]; then touch timed_out; return 28; fi
    printf 200
}
sleep() { :; }
cat() { :; }
"""
    result = subprocess.run(
        [str(bash), '--noprofile', '--norc', '-e', '-c', stub + script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'attempts').read_text().splitlines() == ['attempt'] * attempts


def test_observe_job_has_no_import_secret() -> None:
    """The observe phase must stay write-free (no BATCH_IMPORT_SECRET)."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding='utf-8'))
    observe_env = workflow['jobs']['observe'].get('env', {})
    assert 'BATCH_IMPORT_SECRET' not in observe_env
