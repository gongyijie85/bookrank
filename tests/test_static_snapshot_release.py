import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'validate_static_snapshot.py'
SOURCE_SLUGS = (
    'google_books',
    'open_library',
    'penguin_random_house',
    'simon_schuster',
    'hachette',
    'harpercollins',
    'macmillan',
)
OLD_SUCCESS = '2026-08-31T08:19:06.346180'
NEW_ATTEMPT = '2026-10-24T04:00:00+00:00'


@pytest.fixture
def validator():
    spec = importlib.util.spec_from_file_location('static_snapshot_release_validator', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def _snapshot(directory):
    rows = {slug: [] for slug in SOURCE_SLUGS}
    rows['hachette'] = [{'title': 'Retained book', 'author': 'Writer'}]
    for slug, books in rows.items():
        _write(directory / f'{slug}_books.json', books)
    _write(directory / 'all_books.json', rows)
    metadata = {'timestamp': OLD_SUCCESS, 'publishers': list(rows), 'total_books': 1}
    _write(directory / 'update_time.json', metadata)
    return rows, metadata


def _hashes(directory):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}


def _empty_snapshot(directory):
    # Preserve the shape of the repository's 2026-10-24 all-empty snapshot as a
    # regression fixture. Restoring real data must not require changing the test.
    rows = {slug: [] for slug in SOURCE_SLUGS}
    for slug in rows:
        _write(directory / f'{slug}_books.json', [])
    _write(directory / 'all_books.json', rows)
    _write(directory / 'update_time.json', {'timestamp': OLD_SUCCESS, 'publishers': list(rows), 'total_books': 0})


def test_declared_source_files_match_application_without_importing_app(validator):
    tree = ast.parse((ROOT / 'app/services/publisher_data.py').read_text(encoding='utf-8'))
    assignment = next(
        node for node in tree.body if isinstance(node, ast.AnnAssign) and node.target.id == 'STATIC_DATA_FILES'
    )
    expected = ast.literal_eval(assignment.value)
    assert set(validator.SOURCE_FILES.values()) == set(expected)
    assert set(validator.SOURCE_FILES) == set(SOURCE_SLUGS)


def test_repository_all_empty_snapshot_fixture_is_rejected_without_changes(validator, tmp_path):
    _empty_snapshot(tmp_path)
    before = _hashes(tmp_path)
    with pytest.raises(validator.SnapshotValidationError, match=r'all_books\.json'):
        validator.validate_snapshot(tmp_path)
    assert _hashes(tmp_path) == before


def test_nonempty_snapshot_allows_empty_sources_and_ignores_unrelated_json(validator, tmp_path):
    _snapshot(tmp_path)
    (tmp_path / 'book_language_pack.zh.json').write_text('not business JSON', encoding='utf-8')
    (tmp_path / 'manifest.json').write_text('{}', encoding='utf-8')
    before = _hashes(tmp_path)
    assert validator.validate_snapshot(tmp_path) == 1
    assert _hashes(tmp_path) == before


def test_failed_attempt_can_keep_valid_old_snapshot(validator, tmp_path):
    _snapshot(tmp_path)
    _write(
        tmp_path / 'sync_attempt.json',
        {
            'attempted_at': NEW_ATTEMPT,
            'sources': {slug: {'status': 'failed'} for slug in SOURCE_SLUGS},
            'complete': False,
            'published': False,
        },
    )
    assert validator.validate_snapshot(tmp_path) == 1


def test_partial_snapshot_keeps_old_complete_success_time(validator, tmp_path):
    rows, metadata = _snapshot(tmp_path)
    metadata.update(
        {
            'status': 'partial',
            'last_complete_success_at': None,
            'published_at': NEW_ATTEMPT,
            'source_success_at': {'hachette': OLD_SUCCESS},
        }
    )
    _write(tmp_path / 'update_time.json', metadata)
    _write(tmp_path / 'sync_attempt.json', {'sources': {'google_books': {'status': 'failed'}}})
    before = _hashes(tmp_path)
    assert validator.validate_snapshot(tmp_path) == sum(map(len, rows.values()))
    assert _hashes(tmp_path) == before


@pytest.mark.parametrize(
    'success_fields',
    [
        {'timestamp': OLD_SUCCESS},
        {'last_complete_success_at': NEW_ATTEMPT},
        {'timestamp': None, 'source_success_at': {'hachette': NEW_ATTEMPT}},
    ],
)
def test_each_supported_success_marker_is_accepted(validator, tmp_path, success_fields):
    _, metadata = _snapshot(tmp_path)
    metadata.pop('timestamp')
    metadata.update(success_fields)
    _write(tmp_path / 'update_time.json', metadata)
    assert validator.validate_snapshot(tmp_path) == 1


def test_empty_source_success_cannot_validate_nonempty_source_without_success_evidence(validator, tmp_path):
    _, metadata = _snapshot(tmp_path)
    metadata.pop('timestamp')
    metadata['source_success_at'] = {'google_books': NEW_ATTEMPT}
    _write(tmp_path / 'update_time.json', metadata)
    with pytest.raises(validator.SnapshotValidationError, match=r'update_time\.json'):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize('constant', ['NaN', 'Infinity', '-Infinity'])
def test_nonstandard_json_constants_are_rejected(validator, tmp_path, constant):
    rows, _ = _snapshot(tmp_path)
    rows['hachette'][0]['rating'] = float(constant)
    _write(tmp_path / 'hachette_books.json', rows['hachette'])
    _write(tmp_path / 'all_books.json', rows)
    with pytest.raises(validator.SnapshotValidationError, match=r'\.json'):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize('count', [True, False, '1', 1.0, None, 0, 2])
def test_invalid_or_mismatched_count_is_rejected(validator, tmp_path, count):
    _, metadata = _snapshot(tmp_path)
    metadata['total_books'] = count
    _write(tmp_path / 'update_time.json', metadata)
    with pytest.raises(validator.SnapshotValidationError, match=r'update_time\.json: total_books'):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize('filename', ['all_books.json', 'update_time.json', 'google_books_books.json'])
@pytest.mark.parametrize('problem', ['missing', 'invalid_json', 'invalid_encoding'])
def test_missing_or_unreadable_file_is_rejected(validator, tmp_path, filename, problem):
    _snapshot(tmp_path)
    path = tmp_path / filename
    if problem == 'missing':
        path.unlink()
    elif problem == 'invalid_json':
        path.write_text('{bad JSON', encoding='utf-8')
    else:
        path.write_bytes(b'\xff\xfe\xff')
    with pytest.raises(validator.SnapshotValidationError, match=filename):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize(
    'filename,value',
    [
        ('all_books.json', []),
        ('all_books.json', {'hachette': []}),
        ('update_time.json', []),
        ('google_books_books.json', {}),
        ('sync_attempt.json', []),
        ('sync_attempt.json', {}),
        ('sync_attempt.json', {'sources': []}),
        ('sync_attempt.json', {'sources': {}, 'attempted_at': 'bad-time'}),
    ],
)
def test_invalid_document_structure_is_rejected(validator, tmp_path, filename, value):
    _snapshot(tmp_path)
    _write(tmp_path / filename, value)
    with pytest.raises(validator.SnapshotValidationError, match=filename):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize('field,value', [('title', ''), ('author', ' '), ('title', True), ('author', ['Writer'])])
def test_invalid_book_identity_is_rejected_without_echoing_content(validator, tmp_path, field, value):
    rows, _ = _snapshot(tmp_path)
    book = {'title': 'PRIVATE BOOK CONTENT', 'author': 'PRIVATE AUTHOR', field: value}
    rows['hachette'] = [book]
    _write(tmp_path / 'hachette_books.json', [book])
    _write(tmp_path / 'all_books.json', rows)
    with pytest.raises(validator.SnapshotValidationError) as error:
        validator.validate_snapshot(tmp_path)
    assert field in str(error.value)
    assert 'PRIVATE' not in str(error.value)


def test_source_and_combined_snapshot_must_match(validator, tmp_path):
    _snapshot(tmp_path)
    _write(tmp_path / 'hachette_books.json', [{'title': 'Different', 'author': 'Writer'}])
    with pytest.raises(validator.SnapshotValidationError, match=r'all_books\.json: hachette'):
        validator.validate_snapshot(tmp_path)


def test_source_comparison_distinguishes_boolean_and_number(validator, tmp_path):
    rows, _ = _snapshot(tmp_path)
    rows['hachette'][0]['rank'] = 1
    _write(tmp_path / 'all_books.json', rows)
    rows['hachette'][0]['rank'] = True
    _write(tmp_path / 'hachette_books.json', rows['hachette'])
    with pytest.raises(validator.SnapshotValidationError, match=r'all_books\.json: hachette'):
        validator.validate_snapshot(tmp_path)


def test_source_comparison_ignores_object_key_order(validator, tmp_path):
    rows, _ = _snapshot(tmp_path)
    rows['hachette'][0] = {'author': 'Writer', 'title': 'Retained book'}
    _write(tmp_path / 'all_books.json', rows)
    assert validator.validate_snapshot(tmp_path) == 1


@pytest.mark.parametrize(
    'publishers',
    [[*SOURCE_SLUGS, 'hachette'], list(SOURCE_SLUGS[:-1]), ['unknown'], {}, [True]],
)
def test_publishers_must_be_unique_and_match_sources(validator, tmp_path, publishers):
    _, metadata = _snapshot(tmp_path)
    metadata['publishers'] = publishers
    _write(tmp_path / 'update_time.json', metadata)
    with pytest.raises(validator.SnapshotValidationError, match=r'update_time\.json: publishers'):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize('success_fields', [{}, {'published_at': NEW_ATTEMPT}, {'attempted_at': NEW_ATTEMPT}])
def test_attempt_or_publication_time_cannot_replace_crawl_success(validator, tmp_path, success_fields):
    _, metadata = _snapshot(tmp_path)
    metadata.pop('timestamp')
    metadata.update(success_fields)
    _write(tmp_path / 'update_time.json', metadata)
    _write(tmp_path / 'sync_attempt.json', {'attempted_at': NEW_ATTEMPT, 'sources': {}})
    with pytest.raises(validator.SnapshotValidationError, match=r'update_time\.json'):
        validator.validate_snapshot(tmp_path)


@pytest.mark.parametrize(
    'field,value',
    [
        ('timestamp', 'not a time'),
        ('last_complete_success_at', True),
        ('published_at', 'not a time'),
        ('source_success_at', []),
        ('source_success_at', {'hachette': 'not a time'}),
        ('source_success_at', {'unknown': NEW_ATTEMPT}),
    ],
)
def test_invalid_timestamp_metadata_is_rejected(validator, tmp_path, field, value):
    _, metadata = _snapshot(tmp_path)
    metadata[field] = value
    _write(tmp_path / 'update_time.json', metadata)
    with pytest.raises(validator.SnapshotValidationError, match=f'update_time.json: {field}'):
        validator.validate_snapshot(tmp_path)


def test_cli_accepts_explicit_data_directory_from_another_working_directory(tmp_path):
    directory = tmp_path / 'data'
    directory.mkdir()
    _snapshot(directory)
    before = _hashes(directory)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--data-dir', str(directory)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert 'PRIVATE' not in result.stdout + result.stderr
    assert _hashes(directory) == before


def test_cli_rejects_all_empty_repository_fixture(tmp_path):
    _empty_snapshot(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--data-dir', str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode != 0
    assert 'all_books.json' in result.stderr
