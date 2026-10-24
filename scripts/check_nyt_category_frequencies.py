"""Compare configured NYT list frequencies with the official list metadata."""

import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_OPERATIONAL_ERROR = 2


def fetch_nyt_frequencies(api_key: str, timeout: int = 15) -> dict[str, str]:
    deadline = time.monotonic() + 60
    for attempt in range(3):
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise requests.Timeout('NYT metadata request budget exhausted')
            response = requests.get(
                Config.NYT_LIST_NAMES_URL,
                params={'api-key': api_key},
                timeout=min(timeout, remaining),
            )
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                break
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
        delay = 2**attempt
        if delay >= deadline - time.monotonic():
            raise requests.Timeout('NYT metadata retry budget exhausted')
        time.sleep(delay)
    response.raise_for_status()
    payload = response.json()
    if payload.get('status') != 'OK' or not isinstance(payload.get('results'), list):
        raise ValueError('NYT lists/names 返回格式无效')

    return {
        item['list_name_encoded']: str(item.get('updated') or 'UNKNOWN').upper()
        for item in payload['results']
        if item.get('list_name_encoded')
    }


def find_frequency_drift(
    categories: dict[str, str],
    expected: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    problems = []
    for category in sorted(categories):
        if category not in expected:
            problems.append(f'- `{category}`: 本地未配置预期频率')
        elif category not in actual:
            problems.append(f'- `{category}`: NYT 未返回该分类')
        elif expected[category].upper() != actual[category].upper():
            problems.append(
                f'- `{category}`: 预期 `{expected[category].upper()}`，NYT 返回 `{actual[category].upper()}`'
            )
    return problems


def main() -> int:
    api_key = os.environ.get('NYT_API_KEY', '').strip()
    if not api_key:
        print('NYT 频率检查失败：NYT_API_KEY 未配置')
        return EXIT_OPERATIONAL_ERROR

    try:
        actual = fetch_nyt_frequencies(api_key, timeout=Config.API_TIMEOUT)
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        status = (
            error.response.status_code if isinstance(error, requests.HTTPError) and error.response is not None else None
        )
        print(f'NYT 频率检查失败：{type(error).__name__}' + (f' (HTTP {status})' if status is not None else ''))
        if status == 404:
            print('官方规格仍列出 lists/names.json；本次结果待核实，不将其认定为分类漂移或自动换用其他接口。')
        return EXIT_OPERATIONAL_ERROR

    problems = find_frequency_drift(
        Config.CATEGORIES,
        Config.NYT_CATEGORY_UPDATE_FREQUENCIES,
        actual,
    )
    if not problems:
        print('NYT 分类更新频率一致')
        return EXIT_OK

    checked_at = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
    print('# NYT 分类更新频率发生漂移')
    print(f'\n检查时间：{checked_at}\n')
    print('\n'.join(problems))
    return EXIT_DRIFT


if __name__ == '__main__':
    raise SystemExit(main())
