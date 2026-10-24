import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = 'scripts/validate_static_snapshot.py'
COMMAND = f'python3 {VALIDATOR} --data-dir static/data'


def _deploy_steps():
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'))
    return workflow['jobs']['deploy']['steps']


def test_snapshot_guard_precedes_both_provider_publish_steps():
    steps = _deploy_steps()
    guard_indices = [index for index, step in enumerate(steps) if step.get('run', '').strip() == COMMAND]
    assert len(guard_indices) == 1, 'Missing mandatory pre-publication snapshot guard'
    guard_index = guard_indices[0]
    assert steps[guard_index].get('continue-on-error', False) is False
    for name in ('Deploy and verify Render revision', 'Sync source to HuggingFace Space (backup)'):
        provider_index = next(index for index, step in enumerate(steps) if step.get('name') == name)
        assert guard_index < provider_index


def test_hf_stage_includes_validator_before_replacing_runtime_files():
    step = next(step for step in _deploy_steps() if step.get('name') == 'Sync source to HuggingFace Space (backup)')
    script = step['run']
    copy_command = f'cp {VALIDATOR} "${{STAGE}}/scripts/"'
    stage_guard = 'python3 "${STAGE}/scripts/validate_static_snapshot.py" --data-dir "${STAGE}/static/data"'
    assert copy_command in script, 'HF Docker build must receive the same validator'
    assert stage_guard in script, 'Validate the actual HF payload before replacing the remote clone'
    assert (
        script.index('mkdir -p "${STAGE}/scripts"')
        < script.index(copy_command)
        < script.index(stage_guard)
        < script.index('rsync -a --delete')
    )


def test_docker_validates_copied_snapshot_before_compiling_runtime_assets():
    dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    guard_command = f'RUN python {VALIDATOR} --data-dir static/data'
    assert guard_command in dockerfile, 'Direct image builds must reject empty snapshots'
    assert dockerfile.index('COPY . .') < dockerfile.index(guard_command) < dockerfile.index('RUN pybabel compile')


def test_native_render_build_validates_before_installing_dependencies():
    blueprint = yaml.safe_load((ROOT / 'render.yaml').read_text(encoding='utf-8'))
    service = next(service for service in blueprint['services'] if service['name'] == 'bookrank')
    command = service['buildCommand']
    guard_command = f'python {VALIDATOR} --data-dir static/data'
    assert command.startswith(f'{guard_command} && '), 'Native builds must stop when validation fails'
    assert command.endswith('pip install -r requirements-prod.txt')


@pytest.mark.parametrize('nonempty', [False, True])
def test_actual_actions_guard_command_validates_staged_snapshot(tmp_path, nonempty):
    from scripts.validate_static_snapshot import SOURCE_FILES

    guard_steps = [step for step in _deploy_steps() if step.get('run', '').strip() == COMMAND]
    assert len(guard_steps) == 1
    argv = shlex.split(guard_steps[0]['run'])
    assert argv == ['python3', VALIDATOR, '--data-dir', 'static/data']
    assert (ROOT / VALIDATOR).is_file()
    stage = tmp_path / 'stage'
    (stage / 'scripts').mkdir(parents=True)
    shutil.copyfile(ROOT / VALIDATOR, stage / VALIDATOR)
    data = stage / 'static/data'
    data.mkdir(parents=True)
    sources = dict.fromkeys(SOURCE_FILES)
    for index, (slug, filename) in enumerate(SOURCE_FILES.items()):
        rows = [{'title': 'Fixture book', 'author': 'Fixture author'}] if nonempty and index == 0 else []
        sources[slug] = rows
        (data / filename).write_text(json.dumps(rows), encoding='utf-8')
    (data / 'all_books.json').write_text(json.dumps(sources), encoding='utf-8')
    metadata = {'timestamp': '2026-10-23T00:00:00Z', 'total_books': int(nonempty), 'publishers': list(sources)}
    (data / 'update_time.json').write_text(json.dumps(metadata), encoding='utf-8')
    result = subprocess.run([sys.executable, *argv[1:]], cwd=stage, capture_output=True, text=True, timeout=10)
    assert result.returncode == (0 if nonempty else 1)
    if not nonempty:
        assert 'total_books' in result.stderr
