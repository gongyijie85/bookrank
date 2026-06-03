"""v0.9.55 详情页分类 i18n 一致性验证

测试：进入某本书的详情页，切换语言，分类字段应与首页保持一致
"""
import asyncio
import os
from playwright.async_api import async_playwright

OUT_DIR = r"d:\BookRank3\docs\preview"
os.makedirs(OUT_DIR, exist_ok=True)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await ctx.new_page()
        page.on("console", lambda msg: print(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

        # 监听 API 请求
        api_requests: list[str] = []
        page.on("request", lambda req: api_requests.append(req.url) if "/api/" in req.url else None)

        # 清空 localStorage + 访问首页
        await page.goto("http://127.0.0.1:8000/", wait_until="domcontentloaded", timeout=60000)
        await page.evaluate("localStorage.clear();")
        await page.reload(wait_until="networkidle", timeout=60000)
        await page.wait_for_function(
            "() => document.querySelectorAll('.books-grid .card').length >= 5",
            timeout=30000,
        )
        await page.wait_for_timeout(1500)

        # 拿到第一本书的 ISBN
        first_isbn = await page.evaluate("""
            () => {
                const card = document.querySelector('.books-grid .card[data-isbn]');
                return card ? card.getAttribute('data-isbn') : null;
            }
        """)
        if not first_isbn:
            print("[FAIL] 没找到第一本书的 ISBN")
            await browser.close()
            raise SystemExit(1)
        print(f"第一本书 ISBN: {first_isbn}")

        # 直接构造 URL 进入详情页（用 index=0 即可）
        await page.goto(f"http://127.0.0.1:8000/book/0?category=hardcover-fiction", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        # 采集详情页状态
        async def get_state():
            return await page.evaluate("""
                () => {
                    const result = {};
                    // 详情页分类元素（data-cat-zh / data-cat-en 属性）
                    const catEl = document.querySelector('.meta-card .meta-value[data-cat-zh][data-cat-en]')
                              || document.querySelector('.detail-meta-grid .meta-value[data-cat-zh]');
                    if (catEl) {
                        result['categoryText'] = catEl.textContent.trim();
                        result['categoryZh'] = catEl.getAttribute('data-cat-zh');
                        result['categoryEn'] = catEl.getAttribute('data-cat-en');
                    }
                    return result;
                }
            """)

        # 中文态
        state_zh = await get_state()
        # 也取 innerHTML 看看实际渲染
        cat_html_zh = await page.evaluate("""
            () => {
                const el = document.querySelector('.meta-card .meta-value[data-cat-zh]');
                return el ? el.outerHTML : null;
            }
        """)
        print(f"\n=== 详情页 中文态 ===\n  {state_zh}\n  元素 HTML: {cat_html_zh}")
        await page.screenshot(path=os.path.join(OUT_DIR, "detail_zh.png"), full_page=True)

        # 切到英文
        api_requests.clear()
        await page.click("#lang-globe")
        await page.wait_for_timeout(300)
        await page.click("#lang-opt-en", force=True)
        await page.wait_for_timeout(1500)
        state_en = await get_state()
        print(f"\n=== 详情页 英文态 ===\n  {state_en}")
        await page.screenshot(path=os.path.join(OUT_DIR, "detail_en.png"), full_page=True)
        api_call_count = len(api_requests)
        print(f"\n=== 详情页切换语言时的 API 请求数: {api_call_count} (期望: 0) ===")

        # 切回中文
        await page.click("#lang-globe")
        await page.wait_for_timeout(300)
        await page.click("#lang-opt-zh", force=True)
        await page.wait_for_timeout(1500)
        state_zh2 = await get_state()
        print(f"\n=== 详情页 切回中文 ===\n  {state_zh2}")

        # 断言
        print("\n=== 断言 ===")
        cat_zh = state_zh.get('categoryText', '')
        cat_en = state_en.get('categoryText', '')
        cat_zh2 = state_zh2.get('categoryText', '')
        print(f"  data-cat-zh: {state_zh.get('categoryZh', '')!r}")
        print(f"  data-cat-en: {state_zh.get('categoryEn', '')!r}")

        a1 = "精装" in cat_zh
        print(f"  [{'PASS' if a1 else 'FAIL'}] 中文分类含'精装': {cat_zh!r}")
        a2 = "Hardcover" in cat_en or "Fiction" in cat_en
        print(f"  [{'PASS' if a2 else 'FAIL'}] 英文分类含'Hardcover/Fiction': {cat_en!r}")
        a3 = cat_zh == cat_zh2
        print(f"  [{'PASS' if a3 else 'FAIL'}] 切回中文还原: {cat_zh2!r}")
        a4 = api_call_count == 0
        print(f"  [{'PASS' if a4 else 'FAIL'}] 详情页切换语言 0 API")

        await browser.close()
        if not all([a1, a2, a3, a4]):
            raise SystemExit(1)
        print("\n=== v0.9.55 详情页分类一致性验证通过 ===")


if __name__ == "__main__":
    asyncio.run(main())
