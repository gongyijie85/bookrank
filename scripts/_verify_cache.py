"""首页 AJAX 分类缓存与月榜提示验证。

测试场景：
1. 初始访问不预拉取分类 API。
2. 缺少元数据的旧分类缓存会失效并重新请求。
3. 月榜 AJAX 响应同步更新缓存时间、榜单日期和中英文提示。
4. 周榜隐藏月榜提示，回切月榜命中缓存且恢复月榜自己的元数据。
"""

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Route, async_playwright

BASE_URL = os.environ.get('BOOKRANK_BASE_URL', 'http://127.0.0.1:8000')
OUT_DIR = Path(__file__).resolve().parents[1] / 'docs' / 'preview'
OUT_DIR.mkdir(parents=True, exist_ok=True)

MONTHLY_CATEGORY = 'graphic-books-and-manga'
WEEKLY_CATEGORY = 'hardcover-fiction'
MONTHLY_UPDATE_TIME = '2026-06-30 09:00:00'
WEEKLY_UPDATE_TIME = '2026-07-01 10:30:00'
MONTHLY_LIST_DATE = '2026-06-01'
WEEKLY_LIST_DATE = '2026-07-05'


def _book(category: str, published_date: str) -> dict:
    monthly = category == MONTHLY_CATEGORY
    return {
        'title': 'Monthly Test Book' if monthly else 'Weekly Test Book',
        'title_zh': '月榜测试图书' if monthly else '周榜测试图书',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'description': 'Browser test data',
        'description_zh': '浏览器测试数据',
        'category_name': '漫画与绘本' if monthly else '精装小说',
        'list_name': 'Graphic Books and Manga' if monthly else 'Hardcover Fiction',
        'published_date': published_date,
        'isbn13': '9780000000001' if monthly else '9780000000002',
        'rank': 1,
        'rank_last_week': '0',
        'weeks_on_list': 1,
        'cover': '',
    }


def _api_data(category: str) -> dict:
    monthly = category == MONTHLY_CATEGORY
    published_date = MONTHLY_LIST_DATE if monthly else WEEKLY_LIST_DATE
    return {
        'books': [_book(category, published_date)],
        'category': category,
        'update_time': MONTHLY_UPDATE_TIME if monthly else WEEKLY_UPDATE_TIME,
        'update_frequency': 'monthly' if monthly else 'weekly',
        'list_published_date': published_date,
    }


async def _mock_category_api(route: Route) -> None:
    category = parse_qs(urlparse(route.request.url).query).get('category', [WEEKLY_CATEGORY])[0]
    body = json.dumps({'success': True, 'data': _api_data(category)}, ensure_ascii=False)
    await route.fulfill(status=200, content_type='application/json', body=body)


async def _switch_language(page, lang: str) -> None:
    await page.evaluate('lang => window.setGlobalLanguage(lang)', lang)
    expected_label = '中' if lang == 'zh' else 'EN'
    for _ in range(100):
        if await page.locator('#lang-current').inner_text() == expected_label:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f'语言未切换到 {lang}')


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={'width': 1280, 'height': 800}, locale='zh-CN')
        page = await ctx.new_page()
        page.on('console', lambda msg: print(f'[{msg.type}] {msg.text}') if msg.type in ('error', 'warning') else None)

        api_requests: list[str] = []
        page.on('request', lambda req: api_requests.append(req.url) if '/api/category-books' in req.url else None)
        await page.route('**/api/category-books?*', _mock_category_api)

        await page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        await page.evaluate('localStorage.clear()')
        await page.reload(wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_selector('#category-select')

        assert not api_requests, f'初始访问不应请求分类 API: {api_requests}'
        print('[PASS] 初始访问 0 个分类 API 请求')

        legacy_cache = {
            'timestamp': 4102444800000,
            'books': [_book(MONTHLY_CATEGORY, MONTHLY_LIST_DATE)],
        }
        await page.evaluate(
            """([key, value]) => localStorage.setItem(key, JSON.stringify(value))""",
            [f'bookrank_category_{MONTHLY_CATEGORY}', legacy_cache],
        )

        api_requests.clear()
        await page.select_option('#category-select', MONTHLY_CATEGORY)
        await page.wait_for_timeout(600)
        monthly_calls = [url for url in api_requests if MONTHLY_CATEGORY in url]
        assert len(monthly_calls) == 1, f'旧缓存应失效并请求一次月榜 API: {monthly_calls}'
        assert await page.locator('#monthly-list-hint').inner_text() == (
            f'月榜 · 每月更新 · 榜单日期 {MONTHLY_LIST_DATE}'
        )
        assert await page.locator('.page-subtitle time').get_attribute('datetime') == MONTHLY_UPDATE_TIME
        print('[PASS] 旧缓存失效，中文月榜提示和更新时间来自 AJAX 响应')

        api_requests.clear()
        await _switch_language(page, 'en')
        english_hint = await page.locator('#monthly-list-hint').inner_text()
        assert english_hint == f'Monthly list · Updates monthly · List date {MONTHLY_LIST_DATE}', english_hint
        assert not api_requests, f'切换英文不应请求分类 API: {api_requests}'
        print('[PASS] 英文月榜提示正确，切语言 0 个分类 API 请求')

        api_requests.clear()
        await page.select_option('#category-select', WEEKLY_CATEGORY)
        for _ in range(100):
            if await page.locator('.page-subtitle time').get_attribute('datetime') == WEEKLY_UPDATE_TIME:
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError('周榜更新时间未写入 DOM')
        weekly_calls = [url for url in api_requests if WEEKLY_CATEGORY in url]
        assert len(weekly_calls) == 1, f'首次周榜切换应请求一次 API: {weekly_calls}'
        weekly_hint = await page.evaluate(
            """() => ({
                hidden: document.querySelector('#monthly-list-hint')?.hidden,
                text: document.querySelector('#monthly-list-hint')?.textContent,
                category: window.currentCategory
            })"""
        )
        assert weekly_hint['hidden'], weekly_hint
        assert await page.locator('.page-subtitle time').get_attribute('datetime') == WEEKLY_UPDATE_TIME
        print('[PASS] 周榜隐藏月榜提示并显示自己的更新时间')

        api_requests.clear()
        await page.select_option('#category-select', MONTHLY_CATEGORY)
        await page.wait_for_timeout(300)
        assert not api_requests, f'回切月榜应命中缓存: {api_requests}'
        assert await page.locator('.page-subtitle time').get_attribute('datetime') == MONTHLY_UPDATE_TIME
        assert await page.locator('#monthly-list-hint').inner_text() == (
            f'Monthly list · Updates monthly · List date {MONTHLY_LIST_DATE}'
        )

        await _switch_language(page, 'zh')
        assert await page.locator('#monthly-list-hint').inner_text() == (
            f'月榜 · 每月更新 · 榜单日期 {MONTHLY_LIST_DATE}'
        )
        print('[PASS] 回切月榜命中缓存并恢复自己的时间、榜单日期和中文提示')

        screenshot = OUT_DIR / 'category_cache_metadata_test.png'
        await page.screenshot(path=str(screenshot), full_page=True)
        await browser.close()
        print(f'saved: {screenshot}')


if __name__ == '__main__':
    asyncio.run(main())
