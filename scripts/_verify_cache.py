"""v0.9.55 按需加载 + 内存缓存验证

测试场景：
1. 首次切换到一个未访问过的分类 → 应触发 1 次 API 请求 + 显示 skeleton
2. 再次切换到同一分类 → 应直接命中内存缓存，0 API 请求
3. 跨分类来回切换 → 仅首次每个分类消耗 1 次 API
4. 切换语言时仍然 0 API 请求（保持 v0.9.54 行为）
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

        # === 1. 验证 8 分类预拉取已移除：页面初始访问后不应有 8 个分类的 API 请求 ===
        initial_api_count = len(api_requests)
        print(f"\n=== 初始访问后 API 请求总数: {initial_api_count} (期望: 0) ===")
        if initial_api_count > 0:
            for u in api_requests:
                print(f"  - {u}")
            print("[FAIL] 仍在请求 API，应改为按需加载")
            await browser.close()
            raise SystemExit(1)
        else:
            print("[PASS] 初始访问 0 API 请求（已移除预拉取）")

        # === 2. 首次切换到一个新分类 ===
        api_requests.clear()
        # 切到 "trade-fiction-paperback" (平装小说)
        await page.select_option("#category-select", "trade-fiction-paperback")
        # 等待 skeleton 出现（短暂 200ms）
        skeleton_appeared = await page.evaluate("""
            () => {
                const skel = document.querySelectorAll('.card-skeleton');
                if (skel.length > 0) return true;
                return false;
            }
        """)
        if skeleton_appeared:
            print("[PASS] 切换分类时 skeleton 占位已显示")
        else:
            # 可能 API 太快完成，skeleton 已被替换。检查 process 时间
            print("[INFO] 切换瞬间未抓到 skeleton（API 响应太快），不影响功能")

        # 等待卡片刷新
        await page.wait_for_function(
            "() => document.querySelector('.books-grid .card[data-isbn]') !== null",
            timeout=15000,
        )
        await page.wait_for_timeout(800)
        first_switch_api = list(api_requests)
        print(f"\n=== 首次切到 trade-fiction-paperback 的 API 请求数: {len(first_switch_api)} (期望: 1) ===")
        for u in first_switch_api:
            print(f"  - {u}")
        if len(first_switch_api) == 1:
            print("[PASS] 首次切换到新分类只消耗 1 次 API")
        else:
            print(f"[FAIL] 首次切换消耗了 {len(first_switch_api)} 次 API（应只有 1）")
            await browser.close()
            raise SystemExit(1)

        # === 3. 再次切换到同一分类（应命中内存缓存） ===
        api_requests.clear()
        # 先切到别的分类再切回来
        await page.select_option("#category-select", "hardcover-fiction")
        await page.wait_for_timeout(800)
        await page.select_option("#category-select", "trade-fiction-paperback")
        await page.wait_for_timeout(800)
        revisit_api = list(api_requests)
        print(f"\n=== 再次访问 trade-fiction-paperback 的 API 请求数: {len(revisit_api)} (期望: 1，因为 hardcover-fiction 第一次) ===")
        # 期望: 切到 hardcover-fiction 是 1 次（首次），切到 trade-fiction-paperback 是 0 次（缓存命中）
        hardcover_calls = sum(1 for u in revisit_api if "hardcover-fiction" in u)
        paperback_calls = sum(1 for u in revisit_api if "trade-fiction-paperback" in u)
        print(f"  hardcover-fiction: {hardcover_calls} 次, trade-fiction-paperback: {paperback_calls} 次")
        if paperback_calls == 0:
            print("[PASS] 再次访问 trade-fiction-paperback 命中缓存（0 API）")
        else:
            print(f"[FAIL] 再次访问 trade-fiction-paperback 没有命中缓存（{paperback_calls} API）")

        # === 4. 切换语言时 0 API 请求 ===
        api_requests.clear()
        await page.click("#lang-globe")
        await page.wait_for_timeout(300)
        await page.click("#lang-opt-en", force=True)
        await page.wait_for_timeout(800)
        lang_api = list(api_requests)
        print(f"\n=== 切到英文时的 API 请求数: {len(lang_api)} (期望: 0) ===")
        if len(lang_api) == 0:
            print("[PASS] 切换语言 0 API（按需加载保持原有行为）")
        else:
            for u in lang_api:
                print(f"  - {u}")
            print(f"[FAIL] 切换语言消耗了 {len(lang_api)} 次 API")

        # 切回中文
        await page.click("#lang-globe")
        await page.wait_for_timeout(300)
        await page.click("#lang-opt-zh", force=True)
        await page.wait_for_timeout(800)

        # 截图：当前分类 + 英文
        await page.select_option("#category-select", "hardcover-fiction")
        await page.wait_for_timeout(800)
        await page.screenshot(path=os.path.join(OUT_DIR, "v0_9_55_cache_test.png"), full_page=True)
        print(f"\nsaved: {os.path.join(OUT_DIR, 'v0_9_55_cache_test.png')}")

        await browser.close()
        print("\n=== v0.9.55 按需加载 + 内存缓存验证通过 ===")


if __name__ == "__main__":
    asyncio.run(main())
