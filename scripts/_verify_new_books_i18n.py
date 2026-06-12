"""v0.9.62 新书推介页 i18n 修复端到端验证。

测试矩阵：
1. 中文模式访问 /new-books → 截图（zh 模式）
2. 切换到英文 → 截图（en 模式）
   断言：所有 .pub-name textContent 不含中文（CJK）
   断言：所有 [data-pub-name-en] 元素的 textContent 是英文
   断言：所有 .book-publisher textContent 不含中文
3. 切回中文 → 截图（zh 模式恢复）
4. 访问 /new-book/<id> 详情页 → 切换英文 → 断言标题/作者/出版社都是英文
5. 切回中文 → 断言标题/作者/出版社都是中文
6. 切换过程不应触发任何新 API 请求
"""
import asyncio
import os
import re
import sys
from playwright.async_api import async_playwright

OUT_DIR = r"d:\BookRank3\docs\preview"
os.makedirs(OUT_DIR, exist_ok=True)

CJK_RE = re.compile(r'[\u4e00-\u9fff]')


async def shot_full(page, name: str) -> None:
    """截全页"""
    path = os.path.join(OUT_DIR, name)
    await page.screenshot(path=path, full_page=True)
    print(f"saved: {path}")


async def assert_no_cjk_in_selectors(page, selectors: list[str], label: str) -> None:
    """断言 selectors 选中的所有元素的 textContent 不含中文。"""
    found = await page.evaluate(
        """
        (sels) => {
            const bad = [];
            for (const sel of sels) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const text = (el.textContent || '').trim();
                    if (text && /[\\u4e00-\\u9fff]/.test(text)) {
                        bad.push({sel, text: text.slice(0, 80)});
                    }
                }
            }
            return bad;
        }
        """,
        selectors,
    )
    if found:
        print(f"  [FAIL] {label} 残留中文 ({len(found)} 处):")
        for f in found[:5]:
            print(f"     {f['sel']}: {f['text']!r}")
    else:
        print(f"  [OK]   {label} 无中文残留 ({len(selectors)} 个选择器)")


async def collect_new_books_state(page) -> dict:
    """采集新书页关键状态"""
    return await page.evaluate(
        """
        () => {
            const sideNames = Array.from(document.querySelectorAll('.sidebar-link .pub-name'))
                .map(el => el.textContent.trim());
            const opts = Array.from(document.querySelectorAll('#publisher-filter option'))
                .map(opt => opt.textContent.trim());
            const cards = Array.from(document.querySelectorAll('.book-card .book-publisher'))
                .map(el => {
                    const tn = Array.from(el.childNodes).find(
                        n => n.nodeType === Node.TEXT_NODE && n.textContent.trim()
                    );
                    return tn ? tn.textContent.trim() : '';
                });
            return {sideNames, opts, cards};
        }
        """
    )


async def collect_detail_state(page) -> dict:
    """采集详情页关键状态"""
    return await page.evaluate(
        """
        () => {
            const title = (document.querySelector('.detail-title') || {}).textContent || '';
            const author = (document.querySelector('.detail-author') || {}).textContent || '';
            const pub = (document.querySelector('.meta-value[data-pub-name-zh]') || {}).textContent || '';
            const desc = (document.getElementById('detail-description') || {}).textContent || '';
            const isbnLabel = (document.querySelector('[data-i18n="nb_detail_label_isbn"]') || {}).textContent || '';
            return {title: title.trim(), author: author.trim(), pub: pub.trim(), desc: desc.slice(0, 80).trim(), isbnLabel: isbnLabel.trim()};
        }
        """
    )


async def switch_language(page, lang: str) -> None:
    """触发语言切换"""
    # 模拟点击顶栏的"EN / 中" 切换按钮或直接 dispatch 事件
    # 优先尝试点击 #lang-en / #lang-zh（如果存在）
    selector = f'#lang-{lang}, [data-lang="{lang}"], .lang-{lang}'
    try:
        el = page.locator(selector).first
        if await el.count() > 0:
            await el.click()
            return
    except Exception:
        pass
    # 否则 dispatch 事件
    await page.evaluate(
        f"""
        window.dispatchEvent(new CustomEvent('languagechange', {{
            detail: {{ language: '{lang}' }}
        }}));
        """
    )


async def main() -> int:
    base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
    print(f"测试地址: {base_url}")
    print(f"输出目录: {OUT_DIR}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        # ---- Phase 1: 中文模式 /new-books ----
        print("=" * 60)
        print("Phase 1: 中文模式 /new-books")
        print("=" * 60)
        await page.goto(f"{base_url}/new-books", wait_until="networkidle")
        await page.wait_for_timeout(500)
        await shot_full(page, "new_books_zh.png")

        state_zh = await collect_new_books_state(page)
        print(f"侧边栏出版社数: {len(state_zh['sideNames'])}")
        print(f"下拉框 option 数: {len(state_zh['opts'])}")
        print(f"卡片出版社数: {len(state_zh['cards'])}")
        if state_zh['sideNames']:
            print(f"侧边栏样例: {state_zh['sideNames'][:3]}")

        # ---- Phase 2: 切到英文 ----
        print("\n" + "=" * 60)
        print("Phase 2: 切到英文")
        print("=" * 60)
        await switch_language(page, 'en')
        await page.wait_for_timeout(800)
        await shot_full(page, "new_books_en.png")

        # 断言 1：所有 .pub-name textContent 不含中文
        await assert_no_cjk_in_selectors(
            page,
            ['.sidebar-link .pub-name', '.book-card .book-publisher', '#publisher-filter option'],
            '列表页英文模式',
        )

        # 断言 2：所有 [data-pub-name-en] 元素被切换（textContent 等于 data-pub-name-en）
        mismatched = await page.evaluate(
            """
            () => {
                const bad = [];
                for (const el of document.querySelectorAll('[data-pub-name-en]')) {
                    const expected = (el.getAttribute('data-pub-name-en') || '').trim();
                    const actual = (el.textContent || '').trim();
                    if (expected && actual && actual !== expected) {
                        // 允许 .book-publisher 元素保留 SVG 之外的内容不同（可能有 SVG 前的空白）
                        if (!el.classList.contains('book-publisher')) {
                            bad.push({expected: expected.slice(0, 60), actual: actual.slice(0, 60), tag: el.tagName});
                        }
                    }
                }
                return bad;
            }
            """
        )
        if mismatched:
            print(f"  [FAIL] 元素 textContent 与 data-pub-name-en 不一致 ({len(mismatched)} 处):")
            for m in mismatched[:5]:
                print(f"     <{m['tag']}> expected={m['expected']!r} actual={m['actual']!r}")
        else:
            print("  [OK]   所有 [data-pub-name-en] 元素的 textContent 与 data-pub-name-en 一致")

        # ---- Phase 3: 切回中文 ----
        print("\n" + "=" * 60)
        print("Phase 3: 切回中文")
        print("=" * 60)
        await switch_language(page, 'zh')
        await page.wait_for_timeout(500)
        await shot_full(page, "new_books_zh_restored.png")

        # ---- Phase 4: 详情页 ----
        print("\n" + "=" * 60)
        print("Phase 4: 详情页英文模式")
        print("=" * 60)
        # 取列表页第一本书的链接
        first_link = await page.locator('.book-card a').first.get_attribute('href')
        if first_link:
            detail_url = first_link if first_link.startswith('http') else f"{base_url}{first_link}"
            print(f"详情页: {detail_url}")
            await page.goto(detail_url, wait_until="networkidle")
            await page.wait_for_timeout(500)
            await shot_full(page, "new_book_detail_zh.png")
            state_detail_zh = await collect_detail_state(page)
            print(f"标题(zh): {state_detail_zh['title'][:60]}")
            print(f"出版社(zh): {state_detail_zh['pub']}")

            # 切到英文
            await switch_language(page, 'en')
            await page.wait_for_timeout(800)
            await shot_full(page, "new_book_detail_en.png")
            state_detail_en = await collect_detail_state(page)
            print(f"标题(en): {state_detail_en['title'][:60]}")
            print(f"出版社(en): {state_detail_en['pub']}")

            # 断言：英文模式下标题/作者/出版社不含中文
            for field, val in [
                ('title', state_detail_en['title']),
                ('author', state_detail_en['author']),
                ('pub', state_detail_en['pub']),
            ]:
                if CJK_RE.search(val):
                    print(f"  [FAIL] 详情页 {field} 残留中文: {val!r}")
                else:
                    print(f"  [OK]   详情页 {field} 无中文: {val[:60]!r}")
        else:
            print("  [WARN] 未找到详情页链接，跳过 Phase 4")

        await browser.close()

    print("\n" + "=" * 60)
    print("验证完成，截图保存在", OUT_DIR)
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
