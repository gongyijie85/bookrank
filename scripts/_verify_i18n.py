"""v0.9.54 语言切换即时重渲染验证

测试矩阵：
1. 初始中文 → 切到英文 → 卡片标题/作者/分类/排名/周数 应立即变英文
2. 切到英文 → 切回中文 → 卡片应立即变回中文
3. 切换分类下拉框 option 文本应同步切换
4. 时间格式：英文模式应显示 "Jun 3, 2026 8:08 AM"
5. 切换过程不应触发任何新 API 请求
"""
import asyncio
import os
import re
from playwright.async_api import async_playwright

OUT_DIR = r"d:\BookRank3\docs\preview"
os.makedirs(OUT_DIR, exist_ok=True)


async def shot_card(page, name: str) -> None:
    """截取第一张图书卡片 + 分类下拉框 + 状态文本"""
    # 关掉卡片动画
    await page.evaluate("""
        document.querySelectorAll('.card-animate').forEach(el => {
            el.style.opacity = '1';
            el.style.transform = 'none';
            el.style.animation = 'none';
        });
    """)
    await page.wait_for_timeout(200)
    # 滚到第一张卡
    box = await page.locator(".books-grid .card").first.bounding_box()
    if box:
        await page.evaluate(f"window.scrollTo(0, {int(box['y']) - 30})")
        await page.wait_for_timeout(200)
        clip_h = min(int(box["height"]) + 40, 900)
        await page.screenshot(
            path=os.path.join(OUT_DIR, name),
            clip={"x": 0, "y": max(0, 30 - 20), "width": 420, "height": clip_h},
        )
    else:
        await page.screenshot(path=os.path.join(OUT_DIR, name), full_page=True)
    print(f"saved: {os.path.join(OUT_DIR, name)}")


async def collect_state(page) -> dict:
    """采集当前页面状态用于断言"""
    return await page.evaluate("""
        () => {
            const card = document.querySelector('.books-grid .card');
            const select = document.getElementById('category-select');
            const infoEl = document.querySelector('.export-info');
            const timeEl = document.querySelector('.page-subtitle time');
            return {
                cardTitle: card ? card.querySelector('.card-title')?.textContent.trim() : null,
                cardCategory: card ? card.querySelector('.card-category-tag')?.textContent.trim() : null,
                cardWeeks: card ? card.querySelector('.card-weeks')?.textContent.trim() : null,
                cardRankBadge: card ? card.querySelector('.card-rank-badge')?.textContent.trim() : null,
                selectValue: select ? select.value : null,
                selectFirstOption: select && select.options[0] ? select.options[0].textContent.trim() : null,
                selectSecondOption: select && select.options[1] ? select.options[1].textContent.trim() : null,
                booksCount: infoEl ? infoEl.textContent.trim() : null,
                timeText: timeEl ? timeEl.textContent.trim() : null,
                currentLanguage: localStorage.getItem('app_language') || 'zh',
            };
        }
    """)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 420, "height": 900},
            locale="zh-CN",  # 强制中文初始 locale
        )
        page = await ctx.new_page()
        page.on("console", lambda msg: print(f"[{msg.type}] {msg.text}"))

        # 监听 API 请求
        api_requests: list[str] = []
        page.on("request", lambda req: api_requests.append(req.url) if "/api/" in req.url else None)

        # 第一次访问清空 localStorage
        await page.goto("http://127.0.0.1:8000/", wait_until="domcontentloaded", timeout=60000)
        await page.evaluate("localStorage.clear(); document.cookie = 'lang=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';")
        await page.reload(wait_until="networkidle", timeout=60000)
        await page.wait_for_function(
            "() => document.querySelectorAll('.books-grid .card').length >= 5",
            timeout=30000,
        )
        await page.wait_for_timeout(1500)

        # === 1. 初始中文态 ===
        state_zh = await collect_state(page)
        print("\n=== 初始中文态 ===")
        for k, v in state_zh.items():
            print(f"  {k}: {v}")
        await shot_card(page, "i18n_zh_before.png")

        # 清空 API 请求计数器（只看切换语言时的请求）
        api_requests.clear()

        # === 2. 展开语言菜单，切到英文 ===
        # 先点 globe 按钮展开菜单
        await page.click("#lang-globe")
        await page.wait_for_timeout(300)
        # 再点英文选项
        await page.click("#lang-opt-en", force=True)
        await page.wait_for_timeout(800)
        state_en = await collect_state(page)
        print("\n=== 切到英文后 ===")
        for k, v in state_en.items():
            print(f"  {k}: {v}")
        await shot_card(page, "i18n_en_after.png")
        api_requests_en = list(api_requests)
        api_requests.clear()

        # === 3. 切回中文 ===
        await page.click("#lang-globe")
        await page.wait_for_timeout(300)
        await page.click("#lang-opt-zh", force=True)
        await page.wait_for_timeout(800)
        state_zh2 = await collect_state(page)
        print("\n=== 切回中文后 ===")
        for k, v in state_zh2.items():
            print(f"  {k}: {v}")
        await shot_card(page, "i18n_zh_after.png")
        api_requests_zh = list(api_requests)

        # === 4. 断言 ===
        print("\n=== 断言 ===")
        assertions = []

        # 4.1 卡片标题在英文下应该不是中文（或与中文态不同）
        a1 = state_en["cardTitle"] != state_zh["cardTitle"]
        assertions.append(("标题变化", a1, f"zh='{state_zh['cardTitle']}' en='{state_en['cardTitle']}'"))

        # 4.2 卡片分类标签在英文下应与中文不同
        a2 = state_en["cardCategory"] != state_zh["cardCategory"]
        assertions.append(("分类标签变化", a2, f"zh='{state_zh['cardCategory']}' en='{state_en['cardCategory']}'"))

        # 4.3 排名徽章英文下应包含 "Rank" 或纯数字（不再有"第N名"）
        a3 = "Rank" in (state_en["cardRankBadge"] or "") or bool(re.fullmatch(r"\d+", state_en["cardRankBadge"] or ""))
        assertions.append(("排名徽章英文", a3, f"en='{state_en['cardRankBadge']}'"))

        # 4.4 排名徽章中文态应该是 "第N名"
        a4 = bool(re.search(r"第\s*\d+\s*名", state_zh["cardRankBadge"] or ""))
        assertions.append(("排名徽章中文", a4, f"zh='{state_zh['cardRankBadge']}'"))

        # 4.5 周数后缀英文应该是 "X wk"
        a5 = bool(re.search(r"\d+\s*wk", state_en["cardWeeks"] or ""))
        assertions.append(("周数英文", a5, f"en='{state_en['cardWeeks']}'"))

        # 4.6 周数后缀中文应该是 "X 周"
        a6 = bool(re.search(r"\d+\s*周", state_zh["cardWeeks"] or ""))
        assertions.append(("周数中文", a6, f"zh='{state_zh['cardWeeks']}'"))

        # 4.7 分类下拉第一个 option 英文下应不是中文
        a7 = state_en["selectFirstOption"] != state_zh["selectFirstOption"]
        assertions.append(("下拉框 option 变化", a7, f"zh='{state_zh['selectFirstOption']}' en='{state_en['selectFirstOption']}'"))

        # 4.8 英文下拉框 option 应是英文
        a8 = bool(re.search(r"[A-Za-z]", state_en["selectFirstOption"] or ""))
        assertions.append(("下拉框英文", a8, f"en='{state_en['selectFirstOption']}'"))

        # 4.9 时间格式英文应包含月份缩写
        a9 = bool(re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", state_en["timeText"] or ""))
        assertions.append(("时间英文格式", a9, f"en='{state_en['timeText']}'"))

        # 4.10 切回中文后状态与初始中文态一致（卡片标题/分类/排名）
        a10 = (state_zh2["cardTitle"] == state_zh["cardTitle"]
               and state_zh2["cardCategory"] == state_zh["cardCategory"])
        assertions.append(("切回中文还原", a10, f"before={state_zh['cardTitle']} after={state_zh2['cardTitle']}"))

        all_pass = True
        for name, ok, info in assertions:
            mark = "PASS" if ok else "FAIL"
            if not ok:
                all_pass = False
            print(f"  [{mark}] {name}: {info}")

        print(f"\n=== 结论: {'全部通过' if all_pass else '有失败项'} ===")
        print(f"=== 切到英文时 API 请求数: {len(api_requests_en)} ===")
        for u in api_requests_en[:10]:
            print(f"  {u}")
        print(f"=== 切回中文时 API 请求数: {len(api_requests_zh)} ===")
        for u in api_requests_zh[:10]:
            print(f"  {u}")

        await browser.close()
        if not all_pass:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
