"""Compare configured NYT list frequencies with the official list metadata.

lists/names.json 已被 NYT 下线（带 key 返回 {"errors":["list not found"]}），
所以频率元数据从 lists/overview.json 的 results.lists[*].updated 读取。
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_OPERATIONAL_ERROR = 2


def fetch_nyt_frequencies(api_key: str, timeout: int = 15) -> dict[str, str]:
    """读当前所有榜单及其更新频率。

    lists/names.json 已下线，改用 lists/overview.json：results.lists[*] 里同时有
    list_name_encoded 和 updated；updated 缺失时记为 ''（调用方据此跳过比对）。
    """
    response = requests.get(
        Config.NYT_LISTS_OVERVIEW_URL,
        params={'api-key': api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get('results')
    if payload.get('status') != 'OK' or not isinstance(results, dict):
        raise ValueError('NYT lists/overview 返回格式无效')
    lists = results.get('lists')
    if not isinstance(lists, list):
        raise ValueError('NYT lists/overview 未返回榜单列表')

    return {
        item['list_name_encoded']: str(item.get('updated') or '').upper()
        for item in lists
        if isinstance(item, dict) and item.get('list_name_encoded')
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
        elif not actual[category]:
            # overview 不保证带 updated：没这个字段就不当作漂移（调用方会提示跳过）
            continue
        elif expected[category].upper() != actual[category].upper():
            problems.append(
                f'- `{category}`: 预期 `{expected[category].upper()}`，NYT 返回 `{actual[category].upper()}`'
            )
    return problems


def _redact(text: str, secret: str) -> str:
    """报告会进公开工单和 artifact 产物；GitHub 只对日志做密钥脱敏，这里自己擦。"""
    return text.replace(secret, '***') if secret else text


def main() -> int:
    api_key = os.environ.get('NYT_API_KEY', '').strip()
    if not api_key:
        print('NYT 频率检查失败：NYT_API_KEY 未配置')
        return EXIT_OPERATIONAL_ERROR

    try:
        actual = fetch_nyt_frequencies(api_key, timeout=Config.API_TIMEOUT)
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        # requests 的异常消息里带完整请求 URL（含 api-key）：原样打印会经 artifact
        # 泄漏密钥（公开仓库的 artifact 不走日志脱敏），所以先擦后印。
        print(f'NYT 频率检查失败：{_redact(str(error), api_key)}')
        response = getattr(error, 'response', None)
        if response is not None:
            detail = ' '.join(response.text.split())[:300]
            if detail:
                print(f'NYT 响应体：{_redact(detail, api_key)}')
        return EXIT_OPERATIONAL_ERROR

    problems = find_frequency_drift(
        Config.CATEGORIES,
        Config.NYT_CATEGORY_UPDATE_FREQUENCIES,
        actual,
    )
    if not problems:
        unverifiable = [category for category in Config.CATEGORIES if category in actual and not actual[category]]
        if unverifiable:
            print(
                f'NYT 未返回更新频率字段，跳过 {len(unverifiable)} 个分类的比对：'
                + ', '.join(f'`{category}`' for category in unverifiable)
            )
        else:
            print('NYT 分类更新频率一致')
        return EXIT_OK

    checked_at = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
    print('# NYT 分类更新频率发生漂移')
    print(f'\n检查时间：{checked_at}\n')
    print('\n'.join(problems))
    return EXIT_DRIFT


if __name__ == '__main__':
    raise SystemExit(main())
