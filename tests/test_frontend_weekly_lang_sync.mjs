// 周报页 SSR 语言修正的**事件级**测试：用真实 Jinja 渲染 templates/_weekly_lang_sync.html，
// 再执行渲染结果里的 <script>，断言它在各种 URL / SSR 语言组合下的真实导航行为。
//
// 关键点（历史 bug）：SSR 语言必须以宏参数 ssr_locale 内联进脚本，测试绝不能自己在
// <html> 上"发明" data-ssr-lang 属性——那会在测试里掩盖生产上的失效。
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const templateUrl = new URL('../templates/_weekly_lang_sync.html', import.meta.url);
const template = readFileSync(templateUrl, 'utf8');

/**
 * 用真实 Jinja2 渲染宏：`viaJinja()` → 浏览器里真正收到的 HTML 片段（按语言分页）。
 * 一次性把整个用例的语言列表交给 python（每次调用重新 import Jinja 太慢）。
 */
const RENDER_SCRIPT = String.raw`
import json, sys
from jinja2 import Environment, FileSystemLoader, StrictUndefined

env = Environment(loader=FileSystemLoader(sys.argv[1]), undefined=StrictUndefined)
env.globals['csp_nonce'] = lambda: 'TESTNONCE'
template = env.get_template('_weekly_lang_sync.html')
out = {}
for name in json.loads(sys.argv[2]):
    macro = template.module.weekly_lang_sync
    out[name] = macro(name, 'TESTNONCE')
print(json.dumps(out))
`;

const LOCALES = ['en', 'zh', 'en-US', 'zh-CN', 'zh_Hans'];

function viaJinja() {
    const python = process.env.PYTHON || 'python';
    const templateDir = new URL('../templates/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
    const result = spawnSync(python, ['-c', RENDER_SCRIPT, templateDir, JSON.stringify(LOCALES)], { encoding: 'utf8' });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(`Jinja 渲染失败：${result.stderr || result.stdout}`);
    return JSON.parse(result.stdout);
}

/**
 * 用真实 Jinja2 渲染宏。Python + Jinja2 是本项目的前置依赖（`PYTHON` 可覆盖解释器）：
 * 解释器缺失或渲染报错都直接抛错——不做占位符兜底，兜底会把真实的模板错误伪装成通过。
 */
const rendered = viaJinja();

/** 抽出渲染结果里的 <script> 主体：模板文件不是 JS，只有脚本会进浏览器。 */
function extractScript(html) {
    const match = html.match(/<script[^>]*>([\s\S]*?)<\/script>/);
    assert.ok(match, '渲染结果未包含内联脚本');
    return match[1];
}

const realScripts = Object.fromEntries(
    Object.entries(rendered).map(([locale, html]) => [locale, extractScript(html)]),
);

test('rendering harness uses the real Jinja template', () => {
    // 断言脚本里的 ssrLang 来自真实模板渲染，而不是测试注入的 DOM 属性。
    assert.match(realScripts.en, /var ssrLang = canonical\("en"\);/);
    assert.match(realScripts.zh, /var ssrLang = canonical\("zh"\);/);
});

// ---------------------------------------------------------------------------
// 渲染产物本身：SSR 语言来自宏参数，且不再有 HTML 标记承载它
// ---------------------------------------------------------------------------

/** 去掉 HTML 注释：Jinja `{# … #}` 注释不会进浏览器，脚本内 // 注释也不该被当成标记。 */
function withoutComments(html) {
    return html.replace(/<!--[\s\S]*?-->/g, '');
}

test('rendered partial embeds the SSR locale in the script, not in markup', () => {
    for (const locale of LOCALES) {
        const html = rendered[locale];
        assert.ok(
            html.includes(`canonical(${JSON.stringify(locale)})`),
            `渲染结果应把 ssr_locale 内联进脚本：${locale}`,
        );
        // 历史 bug：语言写在一个 <span data-ssr-lang> 上，脚本却去读 <html data-ssr-lang>。
        // 渲染产物里不能再有任何承载 SSR 语言的 HTML 标记。
        assert.ok(
            !/data-ssr-lang\s*=/.test(withoutComments(html)),
            '不应再有 data-ssr-lang 标记（脚本读 <html> 上不存在的属性会永远不生效）',
        );
    }
    assert.equal(extractScript(rendered.zh).includes('canonical("zh")'), true);
    assert.equal(extractScript(rendered.en).includes('canonical("en")'), true);
});

// ---------------------------------------------------------------------------
// 事件行为：用渲染出来的真实脚本
// ---------------------------------------------------------------------------

// 导航现在是同步发生的；留一点余量给任何微任务/定时器。
const FLUSH_MS = 20;

/**
 * 构造一个足够真实的页面环境（只有 base.html 真实拥有的标记），执行渲染出的脚本。
 *
 * @param {object} options
 * @param {string} options.ssrLocale 宏参数 get_locale() —— 服务端渲染语言
 * @param {string} options.htmlLang  <html lang>，base.html 页首脚本按 cookie/偏好改写
 * @param {string} options.href      当前地址（含查询串与 hash）
 */
function load(options) {
    const { ssrLocale, htmlLang, href } = options;
    // 真实 <html> 只有 lang（以及 base.html 页首脚本可能设置的属性），没有 data-ssr-lang。
    const documentElement = {
        _attrs: { lang: htmlLang },
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(this._attrs, name) ? this._attrs[name] : null;
        },
        setAttribute(name, value) { this._attrs[name] = value; },
    };

    const listeners = {};
    const replaced = [];
    const reloads = [];
    let currentHref = href;

    const location = {
        get href() { return currentHref; },
        replace(target) {
            replaced.push(target);
            // 真实浏览器里 replace() 会离开当前文档；这里保留改写后的地址，
            // 以便断言只导航一次时守卫确实没被重置（而不是给脚本留下重复排程的机会）。
            currentHref = new URL(String(target), currentHref).toString();
        },
        reload() { reloads.push(currentHref); },
        assign(target) { replaced.push(target); currentHref = new URL(String(target), currentHref).toString(); },
        // 与浏览器一致：读属性而不是方法。
        get pathname() { return new URL(currentHref).pathname; },
        get search() { return new URL(currentHref).search; },
        get hash() { return new URL(currentHref).hash; },
    };

    const window = {
        location,
        addEventListener(type, handler) { (listeners[type] ||= []).push(handler); },
        dispatchEvent(event) {
            (listeners[event.type] || []).forEach(handler => handler(event));
        },
    };

    const context = vm.createContext({
        window,
        document: { documentElement },
        URL,
        URLSearchParams,
        setTimeout,
        console,
    });
    vm.runInContext(realScripts[ssrLocale] || realScripts[ssrLocale.toLowerCase()], context);

    return {
        location,
        replaced,
        reloads,
        /** 派发一次 languagechange（base.js / mobile.js 就是这么发的）。 */
        languageChange(lang) {
            window.dispatchEvent({ type: 'languagechange', detail: { language: lang } });
        },
        /** 等潜在的异步导航落地（当前实现是同步的，断言只看最终结果）。 */
        flush: () => new Promise(resolve => setTimeout(resolve, FLUSH_MS)),
    };
}

// ---------------------------------------------------------------------------
// 同语言 / 未知语言：绝不导航
// ---------------------------------------------------------------------------

test('initial languagechange matching SSR locale does not navigate', async () => {
    const page = load({ ssrLocale: 'zh', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=zh' });
    page.languageChange('zh');
    await page.flush();
    assert.deepEqual(page.replaced, [], 'SSR 与偏好同为 zh 时不应导航');
    assert.deepEqual(page.reloads, [], '不得使用 location.reload()');
});

test('unknown locale never navigates even when it differs from SSR', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'en', href: 'https://x.test/reports/weekly' });
    page.languageChange('fr');
    await page.flush();
    assert.deepEqual(page.replaced, []);
});

test('missing locale in event falls back to <html lang> and stays put when it matches SSR', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'en', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange(null);
    await page.flush();
    assert.deepEqual(page.replaced, []);
});

test('an unknown event locale is ignored, never resolved via <html lang>', async () => {
    // SSR=en、<html lang>=zh-CN（页首脚本已按偏好改写）、事件语言 'fr'：三者互不相同。
    // 事件提供的语言无法识别时必须忽略它，不能退回 <html lang> 变成一次 zh 导航。
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('fr');
    await page.flush();
    assert.deepEqual(page.replaced, [], "显式提供的未知语言 'fr' 不得触发导航");
    assert.deepEqual(page.reloads, [], '不得使用 location.reload()');
});

test('SSR locale survives an html lang that the head script changed for the visitor', async () => {
    // 页首脚本把 <html lang> 改成了偏好语言，但本次响应仍是 ?lang=en 渲染的：
    // SSR 语言来自宏参数，必须仍然等于 en（历史 bug：ssrLang 恒为 '' → 永不导航）。
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('zh');
    await page.flush();
    assert.equal(page.replaced.length, 1, 'SSR=en 必须仍然被识别出来并导航');
    assert.equal(new URL(page.replaced[0]).searchParams.get('lang'), 'zh');
});

test('a valid event locale is authoritative even though the URL does not carry it yet', async () => {
    // 地址栏 ?lang=en、SSR=en，用户在页面上切到 zh —— 这正是必须导航的场景，
    // 不能因为「当前 URL 与目标不同」就拒绝。
    const page = load({ ssrLocale: 'en', htmlLang: 'en', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('zh');
    await page.flush();
    assert.equal(page.replaced.length, 1);
    assert.equal(new URL(page.replaced[0]).searchParams.get('lang'), 'zh');
});

test('a URL that already carries the target locale still navigates when SSR differs', async () => {
    // 旧测试的错误假设：地址栏已是 zh 不能证明这次响应就是 zh 渲染的。
    // 服务端 SSR 仍是 en → 必须用修正后的 URL 再请求一次。
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=zh' });
    page.languageChange('zh');
    await page.flush();
    assert.equal(page.replaced.length, 1, 'SSR 仍为 en 时必须导航（地址栏已是 zh 不构成豁免）');
    assert.equal(new URL(page.replaced[0]).searchParams.get('lang'), 'zh');
    assert.equal(new URL(page.replaced[0]).pathname, '/reports/weekly');
});

// ---------------------------------------------------------------------------
// 真实差异：EN 偏好 + ?lang=en 渲染 → 切到 ZH 必须用修正后的 URL 导航
// ---------------------------------------------------------------------------

test('EN page rendered from ?lang=en reconciles once when the user switches to ZH', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('zh');
    await page.flush();

    assert.equal(page.replaced.length, 1, 'EN→ZH 必须导航一次');
    const target = new URL(page.replaced[0]);
    assert.equal(target.searchParams.get('lang'), 'zh');
    assert.equal(target.pathname, '/reports/weekly');
    assert.deepEqual(page.reloads, [], '不得回退到 location.reload()（会对 ?lang=en 死循环）');
});

test('other query parameters and the hash survive the language navigation', async () => {
    const href = 'https://x.test/reports/weekly?lang=en&page=3&q=book#month-2024-01';
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href });
    page.languageChange('zh');
    await page.flush();

    assert.equal(page.replaced.length, 1);
    const target = new URL(page.replaced[0]);
    assert.equal(target.searchParams.get('lang'), 'zh');
    assert.equal(target.searchParams.get('page'), '3');
    assert.equal(target.searchParams.get('q'), 'book');
    assert.equal(target.hash, '#month-2024-01');
    assert.equal(target.origin, 'https://x.test');
});

test('language parameter is added when the URL has none', async () => {
    // 无 ?lang=：SSR 语言由 cookie 决定（这里 SSR=en），偏好是 zh 且 <html lang>
    // 已被页首脚本改成 zh-CN → 必须以事件语言为准补上 ?lang=zh。
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?page=2' });
    page.languageChange('zh');
    await page.flush();

    assert.equal(page.replaced.length, 1);
    const target = new URL(page.replaced[0]);
    assert.equal(target.searchParams.get('lang'), 'zh');
    assert.equal(target.searchParams.get('page'), '2');
});

test('repeated identical events schedule only one navigation', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('zh');
    page.languageChange('zh');
    page.languageChange('zh');
    await page.flush();

    assert.equal(page.replaced.length, 1, '重复事件不得排程多次导航');
    assert.equal(new URL(page.replaced[0]).searchParams.get('lang'), 'zh');
});

test('the guard is not reset before navigating (no second navigation from a later event)', async () => {
    // 守卫在导航前必须保持置位：即便页面因卸载延迟又派发一条事件，也不能再导航一次。
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('zh');
    await page.flush();
    page.languageChange('zh');
    await page.flush();

    assert.equal(page.replaced.length, 1, '排程后守卫被重置会导致重复导航');
});

test('a second page load with matching SSR does not navigate again', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en' });
    page.languageChange('zh');
    await page.flush();
    // 第二次页面加载：SSR 已按 ?lang=zh 渲染 → 同样的偏好不再触发任何导航。
    const second = load({ ssrLocale: 'zh', htmlLang: 'zh-CN', href: page.replaced[0] });
    second.languageChange('zh');
    await second.flush();

    assert.equal(page.replaced.length, 1);
    assert.deepEqual(second.replaced, [], 'SSR 已与偏好一致 → 无重载循环');
});

test('zh-CN renders en-US correctly: the language navigation lands on zh', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=en-US' });
    page.languageChange('zh-CN');
    await page.flush();

    assert.equal(page.replaced.length, 1);
    assert.equal(new URL(page.replaced[0]).searchParams.get('lang'), 'zh');
});

test('zh-CN renders en-US correctly: no navigation when the alias matches the SSR locale', async () => {
    const page = load({ ssrLocale: 'zh', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=zh-CN' });
    page.languageChange('zh-Hans');
    await page.flush();

    assert.deepEqual(page.replaced, [], 'zh-CN / zh-Hans 归一到同一语言，不应导航');
    assert.deepEqual(page.reloads, []);
});

test('en-US alias on an en page does not navigate', async () => {
    const page = load({ ssrLocale: 'en', htmlLang: 'en', href: 'https://x.test/reports/weekly?lang=en-US' });
    page.languageChange('en-US');
    await page.flush();

    assert.deepEqual(page.replaced, []);
});

test('zh-rendered page with an en visitor reconciles to en (both directions work)', async () => {
    const page = load({ ssrLocale: 'zh', htmlLang: 'en', href: 'https://x.test/reports/weekly?lang=zh' });
    page.languageChange('en');
    await page.flush();

    assert.equal(page.replaced.length, 1);
    assert.equal(new URL(page.replaced[0]).searchParams.get('lang'), 'en');
});

test('a rendered zh page recognizes zh-CN SSR correctly (no bogus navigation)', async () => {
    // 宏参数真实值可能是 'zh-CN'（get_locale() 的形态之一）：归一到 zh 后不应导航。
    const page = load({ ssrLocale: 'zh-CN', htmlLang: 'zh-CN', href: 'https://x.test/reports/weekly?lang=zh-CN' });
    page.languageChange('zh');
    await page.flush();
    assert.deepEqual(page.replaced, []);
});

test('rendered partial carries the caller-supplied CSP nonce', () => {
    // 导入的宏不共享调用方上下文：宏内直接调 csp_nonce() 会 UndefinedError（500）。
    // 真实路由测试已验证过这一点，这里锁住 nonce 由调用方传入 + 渲染出 nonce 属性。
    assert.match(template, /\{%\s*macro weekly_lang_sync\(ssr_locale,\s*nonce=''\)\s*%\}/);
    for (const locale of LOCALES) {
        assert.match(rendered[locale], /<script nonce="TESTNONCE">/);
    }
});

test('the weekly templates pass the nonce into the macro', () => {
    for (const name of ['weekly_reports.html', 'weekly_report_detail.html']) {
        const source = readFileSync(new URL(`../templates/${name}`, import.meta.url), 'utf8');
        assert.match(
            source,
            /weekly_lang_sync\(get_locale\(\),\s*csp_nonce\(\)\)/,
            `${name} 必须传入 csp_nonce()`,
        );
    }
});
