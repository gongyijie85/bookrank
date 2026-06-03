"""单卡近景截图：切换到网格视图，单独截第一张图书卡"""
import asyncio
import os
from playwright.async_api import async_playwright

OUT_DIR = r"d:\BookRank3\docs\preview"
os.makedirs(OUT_DIR, exist_ok=True)


async def shot(page, theme: str, name: str) -> None:
    """切换主题并截图"""
    await page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    await page.wait_for_timeout(600)
    # 关闭动画
    await page.evaluate("""
        document.querySelectorAll('.card-animate').forEach(el => {
            el.style.opacity = '1';
            el.style.transform = 'none';
            el.style.animation = 'none';
        });
    """)
    await page.wait_for_timeout(300)
    # 滚到第一张卡
    box = await page.locator(".books-grid .card").first.bounding_box()
    if box is None:
        await page.screenshot(path=os.path.join(OUT_DIR, name), full_page=True)
    else:
        await page.evaluate(f"window.scrollTo(0, {int(box['y']) - 30})")
        await page.wait_for_timeout(300)
        # 用 element 截图（强制 force 避免稳定性检查）
        card = page.locator(".books-grid .card").first
        await card.screenshot(path=os.path.join(OUT_DIR, name), timeout=15000, animations="disabled")
    print(f"saved: {os.path.join(OUT_DIR, name)}")


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 420, "height": 900})
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:8000/", wait_until="networkidle", timeout=60000)
        # 等卡片
        await page.wait_for_function(
            "() => document.querySelectorAll('.books-grid .card').length >= 5",
            timeout=30000,
        )
        await page.wait_for_timeout(2000)
        # 切换到 grid 视图
        await page.evaluate("""
            const btn = document.getElementById('view-grid');
            if (btn) btn.click();
        """)
        await page.wait_for_timeout(800)

        await shot(page, "dark", "card_dark_fixed.png")
        await shot(page, "light", "card_light_fixed.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
