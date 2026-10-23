import json
from unittest.mock import Mock

import pytest

import update_books as updater


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'STATIC_DATA_DIR', str(tmp_path))
    books = {'hachette': [{'title': 'Last valid', 'author': 'Writer'}], 'google_books': []}
    for slug, rows in books.items():
        (tmp_path / f'{slug}_books.json').write_text(json.dumps(rows), encoding='utf-8')
    (tmp_path / 'all_books.json').write_text(json.dumps(books), encoding='utf-8')
    (tmp_path / 'update_time.json').write_text(json.dumps({'timestamp': 'old-success'}), encoding='utf-8')
    return {path.name: path.read_bytes() for path in tmp_path.iterdir()}


def test_empty_crawl_cannot_clear_valid_source_or_advance_success_time(tmp_path, monkeypatch):
    before = _seed(tmp_path, monkeypatch)
    updater.export_to_static_files({'hachette': [], 'google_books': []})
    for name, content in before.items():
        if name != 'update_time.json':
            assert (tmp_path / name).read_bytes() == content
    attempt = json.loads((tmp_path / 'sync_attempt.json').read_text(encoding='utf-8'))
    assert attempt['sources']['hachette']['status'] == 'empty_rejected'
    assert attempt['sources']['google_books']['status'] == 'success_empty'
    assert attempt['published'] is False
    metadata = json.loads((tmp_path / 'update_time.json').read_text(encoding='utf-8'))
    assert metadata['timestamp'] == 'old-success'
    assert metadata['source_success_at'] == {'google_books': attempt['attempted_at']}


def test_all_failures_keep_every_snapshot_and_success_timestamp(tmp_path, monkeypatch):
    before = _seed(tmp_path, monkeypatch)
    updater.export_to_static_files({'hachette': None, 'google_books': None})
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content
    attempt = json.loads((tmp_path / 'sync_attempt.json').read_text(encoding='utf-8'))
    assert all(source['status'] == 'failed' for source in attempt['sources'].values())
    assert attempt['attempted_at']
    assert attempt['published'] is False


def test_partial_failure_keeps_failed_source_and_records_source_freshness(tmp_path, monkeypatch):
    before = _seed(tmp_path, monkeypatch)
    updater.export_to_static_files({'hachette': None, 'google_books': [{'title': 'New', 'author': 'Writer'}]})
    assert (tmp_path / 'hachette_books.json').read_bytes() == before['hachette_books.json']
    merged = json.loads((tmp_path / 'all_books.json').read_text(encoding='utf-8'))
    assert merged['hachette'][0]['title'] == 'Last valid'
    assert merged['google_books'][0]['title'] == 'New'
    metadata = json.loads((tmp_path / 'update_time.json').read_text(encoding='utf-8'))
    assert metadata['status'] == 'partial'
    assert metadata['timestamp'] == 'old-success'
    assert metadata['last_complete_success_at'] is None
    assert metadata['source_success_at']['google_books'] == metadata['published_at']
    assert 'hachette' not in metadata['source_success_at']


def test_attempt_report_separates_stale_retained_source_and_successful_empty_source(tmp_path, monkeypatch):
    before = _seed(tmp_path, monkeypatch)
    metadata_path = tmp_path / 'update_time.json'
    metadata_path.write_text(
        json.dumps({'timestamp': 'old-success', 'source_success_at': {'hachette': 'old-source-success'}}),
        encoding='utf-8',
    )
    report = updater.export_to_static_files({'hachette': None, 'google_books': []})
    stale = report['sources']['hachette']
    assert stale['freshness'] == 'stale'
    assert stale['last_success_at'] == 'old-source-success'
    assert stale['retained_previous'] is True
    empty = report['sources']['google_books']
    assert empty['freshness'] == 'fresh'
    assert empty['last_success_at'] == report['attempted_at']
    assert empty['retained_previous'] is False
    assert (tmp_path / 'all_books.json').read_bytes() == before['all_books.json']


@pytest.mark.parametrize('existing_metadata', [False, True])
def test_empty_success_remains_known_after_repeated_failures(tmp_path, monkeypatch, existing_metadata):
    monkeypatch.setattr(updater, 'STATIC_DATA_DIR', str(tmp_path))
    previous = {'timestamp': 'old-success', 'published_at': 'old-publish', 'status': 'partial'}
    if existing_metadata:
        (tmp_path / 'update_time.json').write_text(json.dumps(previous), encoding='utf-8')
    success = updater.export_to_static_files({'empty': []})
    for _ in range(2):
        failure = updater.export_to_static_files({'empty': None})
        assert failure['sources']['empty']['last_success_at'] == success['attempted_at']
        assert failure['published'] is False
    assert not (tmp_path / 'all_books.json').exists()
    if existing_metadata:
        metadata = json.loads((tmp_path / 'update_time.json').read_text(encoding='utf-8'))
        assert all(metadata[field] == value for field, value in previous.items())


def test_complete_success_updates_global_and_source_timestamps(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    updater.export_to_static_files({'hachette': [{'title': 'New', 'author': 'Writer'}], 'google_books': []})
    metadata = json.loads((tmp_path / 'update_time.json').read_text(encoding='utf-8'))
    assert metadata['status'] == 'success'
    assert metadata['timestamp'] == metadata['published_at'] == metadata['last_complete_success_at']
    assert metadata['source_success_at']['hachette'] == metadata['timestamp']


def test_invalid_book_data_preserves_snapshot(tmp_path, monkeypatch):
    before = _seed(tmp_path, monkeypatch)
    updater.export_to_static_files({'hachette': [{'description': 'no title or author'}]})
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content


@pytest.mark.parametrize(
    'field,value',
    [('title', 7), ('title', True), ('title', ['Book']), ('author', 42), ('author', {'name': 'Writer'})],
)
def test_non_text_identity_fields_cannot_publish_a_snapshot(tmp_path, monkeypatch, field, value):
    before = _seed(tmp_path, monkeypatch)
    book = {'title': 'New', 'author': 'Writer', field: value}
    report = updater.export_to_static_files({'hachette': [book]})
    assert report['sources']['hachette']['status'] == 'invalid'
    assert report['published'] is False
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content


def test_atomic_replace_failure_rolls_back_published_files(tmp_path, monkeypatch):
    before = _seed(tmp_path, monkeypatch)
    replace = updater.os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('simulated write failure')
        return replace(source, target)

    monkeypatch.setattr(updater.os, 'replace', fail_second)
    with pytest.raises(OSError, match='simulated write failure'):
        updater.export_to_static_files({'hachette': [{'title': 'New', 'author': 'Writer'}]})
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content
    assert not list(tmp_path.glob('*.tmp'))


def test_sync_preserves_failure_distinction_and_injects_declared_key(monkeypatch):
    import app.services.publisher_crawler as registry
    from app.services.publisher_crawler.base_crawler import BookInfo, CrawlOutcome

    monkeypatch.setattr(updater, '_PUBLISHER_EXPORTS', [('Google Books', 'google_books')])
    monkeypatch.setenv('GOOGLE_API_KEY', 'local-test-key')
    crawler = Mock()
    crawler.get_new_books.return_value = CrawlOutcome(books=[BookInfo(title='New', author='Writer')])
    crawler_class = Mock(
        return_value=crawler, API_KEY_CONFIG='GOOGLE_API_KEY', REQUEST_DELAY=None, api_key_required=False
    )
    monkeypatch.setattr(registry, 'get_crawler_class', Mock(return_value=crawler_class))
    result = updater.sync_all_publishers()
    assert result['google_books'][0]['title'] == 'New'
    assert crawler_class.call_args.args[0].api_key == 'local-test-key'
    crawler.close.assert_called_once()

    crawler.get_new_books.side_effect = RuntimeError('upstream unavailable')
    assert updater.sync_all_publishers()['google_books'] is None


def test_crawler_cleanup_error_cannot_erase_the_source_failure_report(monkeypatch):
    import app.services.publisher_crawler as registry

    monkeypatch.setattr(updater, '_PUBLISHER_EXPORTS', [('Google Books', 'google_books')])
    crawler = Mock()
    crawler.get_new_books.side_effect = RuntimeError('upstream unavailable')
    crawler.close.side_effect = OSError('cleanup unavailable')
    crawler_class = Mock(return_value=crawler, API_KEY_CONFIG=None, REQUEST_DELAY=None, api_key_required=False)
    monkeypatch.setattr(registry, 'get_crawler_class', Mock(return_value=crawler_class))
    assert updater.sync_all_publishers() == {'google_books': None}
