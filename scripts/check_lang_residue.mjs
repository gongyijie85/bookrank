/**
 * 语言切换残留自检：用页面**自己的 UI** 把语言从 A 切到 B，然后列出所有仍含 CJK 的可见元素。
 *
 * ## 为什么需要它
 *
 * 语言偏好存在 localStorage，浏览器内切换语言时由 `applyPageTranslation()` **就地改写**
 * 带钩子的元素（不重新请求、不整页重渲染）。所以"切换后哪些文案没翻译"完全取决于
 * 运行时 DOM 与钩子覆盖面 —— 静态读模板只能看出"钩子写了没有"，看不出"客户端会不会用、
 * 有没有被别的重渲染覆盖回去"。
 *
 * 这类缺陷**极其安静**：SSR 永远按当次请求的语言渲染（curl 看是好的），切换动作也没报错，
 * 只有肉眼看页面才发现。2026-09-18 用户报的"切换语言后有一部分导航没有翻译"就是这个：
 * 面包屑三项 + 侧边栏「导航」整段共 48 处冻结在 SSR 语言。
 *
 * ## 用法
 *
 *   node scripts/check_lang_residue.mjs <url> [--from zh] [--to en]
 *   node scripts/check_lang_residue.mjs --list pages.txt --to en     # 每行一个 URL
 *
 * 退出码：0 = chrome 区域没有残留（GREEN）；1 = 有残留（RED）。
 *
 * ## 判定口径
 *
 * "残留" = 元素**自身文本**含中日韩字符。只统计 chrome 区域（顶栏 / 面包屑 / 侧边栏 /
 * 页脚 / 返回导航 / 跳过链接 / 移动端导航弹层）—— 正文里的中文可能是正当数据
 * （中文书名、奖项名、手工撰写的标题），不该判成故障。
 *
 * ## 需要 Chrome
 *
 * 用 CDP 驱动 headless Chrome。解释器按顺序找：环境变量 `CHROME`、常见安装路径、
 * PATH 上的 google-chrome/chromium。仅在 CI 里跑的话需要先装 Chrome。
 */

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME_CANDIDATES = [
    process.env.CHROME,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
].filter(Boolean);

function resolveChrome() {
    for (const candidate of CHROME_CANDIDATES) {
        try {
            if (fs.existsSync(candidate)) return candidate;
        } catch {
            /* 忽略权限等问题 */
        }
    }
    throw new Error(
        `找不到 Chrome，请用环境变量 CHROME 指定可执行文件。尝试过：${CHROME_CANDIDATES.join(', ')}`
    );
}

function parseArgs(argv) {
    const options = { from: 'zh', to: 'en', port: 9226, urls: [] };
    for (let i = 0; i < argv.length; i += 1) {
        const arg = argv[i];
        if (arg === '--from') options.from = argv[++i];
        else if (arg === '--to') options.to = argv[++i];
        else if (arg === '--port') options.port = Number(argv[++i]);
        else if (arg === '--list') {
            const file = argv[++i];
            options.urls.push(
                ...fs.readFileSync(file, 'utf8').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'))
            );
        } else if (!arg.startsWith('--')) options.urls.push(arg);
    }
    if (!options.urls.length) {
        throw new Error('用法: node scripts/check_lang_residue.mjs <url> [--from zh] [--to en] [--list pages.txt]');
    }
    return options;
}

/** 在页面里收集"自身文本含 CJK"的可见元素（排除脚本/样式/注释），并标出是否在 chrome 区域。 */
const COLLECT = `(() => {
  const CJK = /[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff]/;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
  const CHROME_SELECTOR = '.top-nav, .breadcrumbs, .sidebar, .site-nav-dialog, footer, .detail-nav, .skip-link';
  const chromeOf = (el) => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.matches && n.matches(CHROME_SELECTOR)) {
        return (n.getAttribute('class') || n.tagName.toLowerCase()).split(' ')[0];
      }
    }
    return '';
  };
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (SKIP.has(el.tagName)) continue;
    const own = [...el.childNodes]
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join(' ')
      .replace(/\\s+/g, ' ')
      .trim();
    if (!own || !CJK.test(own)) continue;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    out.push({
      tag: el.tagName.toLowerCase(),
      cls: (el.getAttribute('class') || '').slice(0, 60),
      i18n: el.getAttribute('data-i18n') || '',
      hasBilingual: el.hasAttribute('data-zh') && el.hasAttribute('data-en'),
      text: own.slice(0, 90),
      chrome: chromeOf(el),
    });
  }
  return { lang: localStorage.getItem('app_language'), html: document.documentElement.lang, items: out };
})()`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function checkUrl(chromePath, url, { from, to, port }) {
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-lang-'));
    const chrome = spawn(
        chromePath,
        [
            '--headless=new',
            '--disable-gpu',
            '--no-sandbox',
            '--no-first-run',
            '--hide-scrollbars',
            `--remote-debugging-port=${port}`,
            `--user-data-dir=${profile}`,
            'about:blank',
        ],
        { stdio: 'ignore' }
    );

    let ws;
    try {
        let ready = null;
        for (let i = 0; i < 60; i += 1) {
            try {
                const r = await fetch(`http://127.0.0.1:${port}/json/version`);
                if (r.ok) {
                    ready = await r.json();
                    break;
                }
            } catch {
                /* 继续等 */
            }
            await sleep(250);
        }
        if (!ready) throw new Error('CDP 未就绪');

        const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        const page = targets.find((t) => t.type === 'page');
        ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((res, rej) => {
            ws.onopen = res;
            ws.onerror = () => rej(new Error('WS 连接失败'));
        });

        let msgId = 0;
        const pending = new Map();
        ws.onmessage = (ev) => {
            const m = JSON.parse(ev.data);
            const slot = pending.get(m.id);
            if (slot) {
                pending.delete(m.id);
                if (m.error) slot.reject(new Error(JSON.stringify(m.error)));
                else slot.resolve(m.result);
            }
        };
        const send = (method, params = {}) =>
            new Promise((resolve, reject) => {
                const id = ++msgId;
                pending.set(id, { resolve, reject });
                ws.send(JSON.stringify({ id, method, params }));
            });
        const evaluate = async (expression) => {
            const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
            if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
            return r.result.value;
        };

        await send('Page.enable');
        await send('Page.navigate', { url: url.includes('?') ? `${url}&lang=${from}` : `${url}?lang=${from}` });

        // 确定性就绪：页面自身的 on-load 脚本（读 localStorage 偏好 → applyPageTranslation）
        // 与我们的点击存在竞态，只靠固定 sleep 会得到不稳定的残留数（实测同页跑出 27 / 10 两种）。
        let state = null;
        for (let i = 0; i < 60; i += 1) {
            await sleep(500);
            try {
                state = await evaluate(
                    `({ ready: document.readyState, fn: typeof applyPageTranslation })`
                );
                if (state.ready === 'complete' && state.fn === 'function' && i >= 6) break;
            } catch {
                /* 导航中 */
            }
        }
        await sleep(1500);

        const clicked = await evaluate(
            `(() => { const b = document.getElementById('lang-opt-${to}'); if (!b) return 'no-button'; b.click(); return 'clicked'; })()`
        );
        await sleep(2500);

        const after = await evaluate(COLLECT);
        return { url, clicked, after };
    } finally {
        if (ws) ws.close();
        chrome.kill();
        await sleep(300);
        fs.rmSync(profile, { recursive: true, force: true });
    }
}

async function main() {
    const options = parseArgs(process.argv.slice(2));
    const chromePath = resolveChrome();
    let stuck = 0;

    for (const url of options.urls) {
        const { clicked, after } = await checkUrl(chromePath, url, options);
        const chromeItems = after.items.filter((x) => x.chrome);
        stuck += chromeItems.length;
        const mark = chromeItems.length ? '**残留**' : 'clean';
        console.log(`\n[${mark}] ${url}`);
        console.log(
            `  点击 #lang-opt-${options.to} → ${clicked}；html.lang=${after.html} localStorage=${after.lang}` +
                `；chrome 内残留 ${chromeItems.length} 个，正文内 ${after.items.length - chromeItems.length} 个`
        );
        for (const x of chromeItems) {
            console.log(
                `    [${x.chrome}] <${x.tag} class="${x.cls}" i18n="${x.i18n}" bilingual=${x.hasBilingual}> ${x.text}`
            );
        }
    }

    if (stuck) {
        console.log(
            `\nVERDICT: RED —— ${stuck} 处 chrome 文案在切换语言后仍是原语言。` +
                '\n  没有钩子的补 data-i18n（静态文案）或 data-zh/data-en（数据型文案）；' +
                '\n  有钩子却仍残留 → 检查是不是被别的重渲染覆盖回去了。'
        );
    } else {
        console.log('\nVERDICT: GREEN —— 所有 chrome 文案都随语言切换更新');
    }
    process.exitCode = stuck ? 1 : 0;
}

main().catch((error) => {
    console.error(`探针失败：${error.message}`);
    process.exit(2);
});
