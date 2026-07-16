from unittest.mock import Mock

import requests

from app.config import Config
from scripts import check_nyt_category_frequencies as checker


def test_frequency_config_covers_every_supported_category():
    assert set(Config.NYT_CATEGORY_UPDATE_FREQUENCIES) == set(Config.CATEGORIES)


def test_find_frequency_drift_accepts_matching_metadata():
    actual = {category: frequency.upper() for category, frequency in Config.NYT_CATEGORY_UPDATE_FREQUENCIES.items()}

    assert checker.find_frequency_drift(Config.CATEGORIES, Config.NYT_CATEGORY_UPDATE_FREQUENCIES, actual) == []


def test_find_frequency_drift_reports_changed_missing_and_unconfigured_categories():
    categories = {'changed': 'Changed', 'missing': 'Missing', 'unconfigured': 'Unconfigured'}
    expected = {'changed': 'weekly', 'missing': 'monthly'}
    actual = {'changed': 'MONTHLY'}

    assert checker.find_frequency_drift(categories, expected, actual) == [
        '- `changed`: 预期 `WEEKLY`，NYT 返回 `MONTHLY`',
        '- `missing`: NYT 未返回该分类',
        '- `unconfigured`: 本地未配置预期频率',
    ]


def test_fetch_nyt_frequencies_uses_list_names_metadata(monkeypatch):
    response = Mock()
    response.json.return_value = {
        'status': 'OK',
        'results': [
            {'list_name_encoded': 'hardcover-fiction', 'updated': 'WEEKLY'},
            {'list_name_encoded': 'graphic-books-and-manga', 'updated': 'MONTHLY'},
        ],
    }
    monkeypatch.setattr(requests, 'get', Mock(return_value=response))

    result = checker.fetch_nyt_frequencies('secret', timeout=7)

    assert result == {'hardcover-fiction': 'WEEKLY', 'graphic-books-and-manga': 'MONTHLY'}
    requests.get.assert_called_once_with(
        Config.NYT_LIST_NAMES_URL,
        params={'api-key': 'secret'},
        timeout=7,
    )
    response.raise_for_status.assert_called_once_with()


def test_main_returns_operational_error_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv('NYT_API_KEY', raising=False)

    assert checker.main() == checker.EXIT_OPERATIONAL_ERROR
    assert 'NYT_API_KEY 未配置' in capsys.readouterr().out


def test_main_returns_operational_error_for_api_failure(monkeypatch, capsys):
    monkeypatch.setenv('NYT_API_KEY', 'secret')
    monkeypatch.setattr(checker, 'fetch_nyt_frequencies', Mock(side_effect=requests.Timeout('timeout')))

    assert checker.main() == checker.EXIT_OPERATIONAL_ERROR
    assert 'NYT 频率检查失败' in capsys.readouterr().out


def test_main_returns_drift_and_markdown_report(monkeypatch, capsys):
    monkeypatch.setenv('NYT_API_KEY', 'secret')
    actual = {category: frequency.upper() for category, frequency in Config.NYT_CATEGORY_UPDATE_FREQUENCIES.items()}
    actual['hardcover-fiction'] = 'MONTHLY'
    monkeypatch.setattr(checker, 'fetch_nyt_frequencies', Mock(return_value=actual))

    assert checker.main() == checker.EXIT_DRIFT
    output = capsys.readouterr().out
    assert '# NYT 分类更新频率发生漂移' in output
    assert '`hardcover-fiction`' in output


def test_main_returns_ok_when_frequencies_match(monkeypatch, capsys):
    monkeypatch.setenv('NYT_API_KEY', 'secret')
    actual = {category: frequency.upper() for category, frequency in Config.NYT_CATEGORY_UPDATE_FREQUENCIES.items()}
    monkeypatch.setattr(checker, 'fetch_nyt_frequencies', Mock(return_value=actual))

    assert checker.main() == checker.EXIT_OK
    assert 'NYT 分类更新频率一致' in capsys.readouterr().out
