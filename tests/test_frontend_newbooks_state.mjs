// 新书速递页筛选状态机的**行为级**测试。
//
// 做法：用真实 Jinja2 渲染 templates/new_books.html（拿到浏览器真正收到的内联脚本 +
// 真实 HTML 结构），再在 node:vm 里用一个最小 DOM / fetch / history 桩执行它，然后
// 断言真实的 DOM 变化与导航调用。被测的是生产脚本本身，不是抄一份逻辑过来重写，
// 也不是对源码字符串做断言 —— 后者在函数体里加一行注释也能变红/变绿。
//
// 覆盖的历史 bug：
//   1. BookI18n 切语言时把标题容器 textContent 整体覆盖，内层 <a>（详情路由）与卷号
//      兄弟节点一起被抹掉 —— 书名变死文本、卡片不可点。
//   2. 选中筛选后只有下拉框变化：没有 chip、不更新 URL —— 页面与地址栏各说各话。
//   3. chip 移除顺手把其它条件一起清掉。
//   4. Back/Forward 恢复时又 pushState，历史被撑爆；语言重绘也写历史。
//   5. 加载 A 时改选 B，B 的请求被 `if (isLoading) return` 丢弃；A 稍后返回，用旧结果
//      覆盖 B 的 UI（卡片是 A、chips 是 B）。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import vm from 'node:vm';

const BOOK_I18N_PATH = new URL('../static/js/book-i18n.js', import.meta.url);
const BASE_JS_PATH = new URL('../static/js/base.js', import.meta.url);

// ---------------------------------------------------------------------------
// 1) 真实页面：现渲染的 Jinja 输出（tests/fixtures/render_new_books.py）
// ---------------------------------------------------------------------------

/**
 * 页面 HTML 来自**真实模板的当场渲染**：`tests/fixtures/render_new_books.py` 用与
 * `app/routes/main.py:_load_new_books_data` 同一批变量渲染 `templates/new_books.html`，
 * 渲染结果直接走 stdout 交给本测试消费。
 *
 * 为什么不是快照文件：快照 + mtime 新鲜度检查在 Git checkout 上不可靠（checkout 会给
 * 所有文件同一个时间戳），而且会在模板已改、快照未重生成时**静默测旧代码**。
 * 现渲染没有这个失效模式：跑的一定是工作区当前的模板。
 *
 * renderer 只依赖 Jinja2，不 import Flask / 应用代码；CI 侧由独立的 Python/Jinja
 * 环境提供解释器（`PYTHON` 环境变量可覆盖 `python`）。
 *
 * fixture 的分类实体数据与生产同源头：生产 `CATEGORY_EN_TO_ZH` 里
 * Business→商业、Fiction→小说 都在，夹具也按同一对应项提供，
 * 免得拿"生产有、夹具没有"的假分类去断言。
 */
const RENDERER_PATH = new URL('./fixtures/render_new_books.py', import.meta.url);
const pythonExe = process.env.PYTHON || 'python';

/**
 * Windows 盘符路径（`D:\...`）在 URL 里是 `/D:/...`，spawn 不认这种写法；
 * `fileURLToPath` 是标准做法，但这里只需剥掉前导斜杠即可跨平台可用。
 */
const RENDERER_FILE = decodeURIComponent(RENDERER_PATH.pathname).replace(/^\/([A-Za-z]:)/, '$1');

function renderTemplate() {
    const result = spawnSync(pythonExe, [RENDERER_FILE], {
        cwd: new URL('..', import.meta.url),
        encoding: 'utf8',
        maxBuffer: 32 * 1024 * 1024,
    });
    // 渲染失败（解释器缺失 / Jinja 报错 / 模板语法错误）一律直接失败：
    // 不做兜底、不回退到快照 —— 否则又会回到"测试通过但测的是旧代码"。
    assert.equal(
        result.error,
        undefined,
        `无法启动模板渲染器（${pythonExe} ${RENDERER_FILE}）：${result.error && result.error.message}`,
    );
    assert.equal(
        result.status,
        0,
        `模板渲染器失败（exit ${result.status}）：\n${result.stderr || ''}`,
    );
    assert.ok(result.stdout && result.stdout.trim(), '模板渲染器没有输出 HTML（stdout 为空）');
    return result.stdout;
}

const renderedHtml = renderTemplate();

/** 抽出模板里唯一的内联脚本主体；模板文件本身不是 JS，只有脚本会进浏览器。 */
function extractScripts(html) {
    // 结束标签必须是 `</script\s*[^>]*>`：HTML5 里 `</SCRIPT >`、`</script\t\n bar>`
    // 都算合法结束标签（属性被忽略），只写 `</script>` 会让抽取结果跨块吞掉后续标记。
    const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*[^>]*>/gi)].map((m) => m[1]);
    assert.ok(scripts.length > 0, '渲染结果未包含内联脚本');
    return scripts;
}

const pageScript = extractScripts(renderedHtml).find((s) => s.includes('function loadBooks('));
assert.ok(pageScript, '未找到 new_books.html 的筛选状态脚本');

// ---------------------------------------------------------------------------
// 2) 最小 DOM 桩：只实现被测脚本真正用到的那一小撮 API
// ---------------------------------------------------------------------------

/**
 * 极简 Element。选择器只支持本脚本用到的形式：
 *   #id、.class、tag、[attr]、[attr="值"]、a[href]、以及用空格/`>` 组合的后代选择器。
 * 属性选择器的值可以含空格/&，所以取到 `=` 之后一直匹配到 `]`。
 */
class El {
    constructor(tag, attrs = {}, text = '') {
        this.tagName = String(tag).toUpperCase();
        this.attributes = { ...attrs };
        this.childNodes = [];
        this.parentNode = null;
        this.style = {};
        this.listeners = new Map();
        this._value = attrs.value !== undefined ? String(attrs.value) : '';
        this._text = text;
        this.hidden = false;
        // document.documentElement.style.getPropertyValue/setPropertyValue（base.js 用）
        this.style = {
            _props: new Map(),
            getPropertyValue(name) { return this._props.get(name) || ''; },
            setProperty(name, value) { this._props.set(name, String(value)); },
        };
        const self = this;
        this.classList = {
            _set: new Set(String(attrs.class || '').split(/\s+/).filter(Boolean)),
            add(...names) { names.forEach((n) => this._set.add(n)); },
            remove(...names) { names.forEach((n) => this._set.delete(n)); },
            contains(name) { return this._set.has(name); },
            toggle(name, force) {
                const on = force === undefined ? !this.contains(name) : !!force;
                if (on) this.add(name); else this.remove(name);
                return on;
            },
            get value() { return [...this._set].join(' '); },
            toString() { return [...this._set].join(' '); },
        };
        void self;
    }

    get textContent() {
        if (this.childNodes.length) return this.childNodes.map((n) => n.textContent).join('');
        return this._text;
    }

    set textContent(value) {
        // 与浏览器一致：整体替换会清空所有子节点。BookI18n 的标题覆盖 bug 正是靠这条语义暴露。
        this.childNodes.forEach((n) => { n.parentNode = null; });
        this.childNodes = [];
        this._text = value == null ? '' : String(value);
    }

    get value() { return this._value; }
    set value(v) { this._value = v == null ? '' : String(v); }

    get className() { return this.classList.value; }
    set className(v) {
        this.classList._set = new Set(String(v || '').split(/\s+/).filter(Boolean));
    }

    getAttribute(name) {
        if (name === 'class') return this.classList.value;
        const v = this.attributes[name];
        return v === undefined ? null : String(v);
    }

    setAttribute(name, value) {
        if (name === 'class') { this.className = value; return; }
        this.attributes[name] = String(value);
    }

    removeAttribute(name) { delete this.attributes[name]; }

    hasAttribute(name) { return this.attributes[name] !== undefined; }

    get innerHTML() { return this._innerHTML === undefined ? this.textContent : this._innerHTML; }

    set innerHTML(html) {
        // 真实浏览器会把 HTML 解析成子节点；chips / 卡片 / 错误态都是 innerHTML 注入的，
        // 必须真的建树，后续才能查询到 [data-chip-key]、.book-card 等。
        this._innerHTML = String(html);
        this.childNodes.forEach((n) => { n.parentNode = null; });
        this.childNodes = [];
        this._text = '';
        const parsed = parseHtml(this._innerHTML, this.ownerDocument);
        for (const child of [...parsed.childNodes]) {
            this.appendChild(child);
            tagOwner(child, this.ownerDocument);
        }
    }

    /** 把一段真实 HTML 片段解析成轻量节点树（仅覆盖模板/卡片 HTML 用到的写法）。 */
    appendChild(child) {
        child.parentNode = this;
        this.childNodes.push(child);
        return child;
    }

    append(...nodes) { nodes.forEach((n) => this.appendChild(n)); }

    matches(selector) { return matchSelector(this, selector); }

    getBoundingClientRect() {
        // 布局无关：base.js 只用它同步 --top-nav-height，给 0 即"不处理"。
        return { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 };
    }

    scrollBy() { /* no-op：rail 滚动与本套测试无关 */ }

    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }

    querySelectorAll(selector) {
        const out = [];
        const groups = selector.split(',').map((s) => s.trim()).filter(Boolean);
        for (const group of groups) {
            collectMatches(this, group.split(/\s+/).filter(Boolean), out);
        }
        return out;
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    contains(other) {
        if (!other) return false;
        let node = other;
        while (node) {
            if (node === this) return true;
            node = node.parentNode;
        }
        return false;
    }

    addEventListener(type, fn) {
        if (!this.listeners.has(type)) this.listeners.set(type, []);
        this.listeners.get(type).push(fn);
    }

    removeEventListener(type, fn) {
        const list = this.listeners.get(type) || [];
        const i = list.indexOf(fn);
        if (i >= 0) list.splice(i, 1);
    }

    dispatchEvent(event) {
        (this.listeners.get(event.type) || []).forEach((fn) => fn(event));
        // 冒泡到祖先（事件委托靠这个）
        let node = this.parentNode;
        while (node) {
            (node.listeners.get(event.type) || []).forEach((fn) => fn(event));
            node = node.parentNode;
        }
        return true;
    }
}

class TextNode {
    constructor(text) {
        this.nodeType = 3;
        this._text = String(text);
        this.parentNode = null;
        this.childNodes = [];
    }
    get textContent() { return this._text; }
    set textContent(v) { this._text = v == null ? '' : String(v); }
}

/** 单个复合选择器（如 `a.browse-card-title-link` 或 `[data-chip-key="category"]`）。 */
function matchCompound(el, compound) {
    const attrRe = /\[([^\]=\s]+)(?:=("([^"]*)"|'([^']*)'|([^\]\s]+)))?\]/g;
    let rest = compound;
    let m;
    while ((m = attrRe.exec(compound))) {
        const name = m[1];
        const expected = m[3] !== undefined ? m[3] : (m[4] !== undefined ? m[4] : (m[5] !== undefined ? m[5] : null));
        if (!el.hasAttribute(name)) return false;
        if (expected !== null && el.getAttribute(name) !== expected) return false;
    }
    rest = rest.replace(attrRe, '');
    const classNames = (rest.match(/\.([A-Za-z0-9_-]+)/g) || []).map((c) => c.slice(1));
    const idMatch = rest.match(/#([A-Za-z0-9_-]+)/);
    const tagMatch = rest.match(/^[A-Za-z][A-Za-z0-9-]*/);
    if (idMatch && el.attributes.id !== idMatch[1]) return false;
    const classes = el.classList._set;
    if (!classNames.every((c) => classes.has(c))) return false;
    if (tagMatch && el.tagName !== tagMatch[0].toUpperCase()) return false;
    return true;
}

/** 递归标注 ownerDocument，供 innerHTML 解析出的子树使用。 */
function tagOwner(node, doc) {
    if (node instanceof El || node instanceof TextNode) node.ownerDocument = doc;
    if (node.childNodes) node.childNodes.forEach((c) => tagOwner(c, doc));
}

function matchSelector(el, selector) {
    // 组合选择器用最后一个 token 判定自身，其余交给后代匹配处理。
    const tokens = selector.trim().split(/\s+/);
    return matchCompound(el, tokens[tokens.length - 1]);
}

function descendantChainMatches(node, tokens) {
    // tokens 是祖先链（不含自身），要求从近到远依次匹配。
    let i = tokens.length - 1;
    let cur = node.parentNode;
    while (i >= 0) {
        if (!cur) return false;
        if (matchCompound(cur, tokens[i])) { i -= 1; cur = cur.parentNode; continue; }
        // `>` 组合符：父级必须严格匹配
        if (tokens[i] === '>') { i -= 1; continue; }
        cur = cur.parentNode;
    }
    return true;
}

function collectMatches(root, tokens, out) {    const last = tokens[tokens.length - 1];
    const ancestors = tokens.slice(0, -1).filter((t) => t !== '>');
    const walk = (node) => {
        for (const child of node.childNodes) {
            if (child instanceof El || child instanceof TextNode) {
                if (child instanceof El && matchCompound(child, last) && descendantChainMatches(child, ancestors)) {
                    out.push(child);
                }
                walk(child);
            }
        }
    };
    walk(root);
}

/** 把真实 HTML 片段解析为节点树（覆盖本模板产出的写法）。 */
function parseHtml(html, doc) {
    const root = new El('div');
    const stack = [root];
    // <script>/<style> 的内容是文本，不是标记：必须先剥离，否则脚本里字符串字面量中的
    // `data-isbn="..."` 会被解析成真实属性，把 BookI18n 的分支判断带偏。
    const cleaned = html
        .replace(/<script\b[^>]*>[\s\S]*?<\/script\s*[^>]*>/gi, '<script></script>')
        .replace(/<style\b[^>]*>[\s\S]*?<\/style\s*[^>]*>/gi, '<style></style>');
    // 分词只负责把标签**边界**切出来（属性文本交给下面的 attrRe 再解析），所以这里
    // 不需要 `name=value` 的结构语法。四个分支按首字符互斥（普通字符 / 不成对的 `/` /
    // 双引号 / 单引号），既不会把引号里的 `>` 当标签结束，也不存在嵌套量词导致的回溯。
    const tokenRe = /<!--[\s\S]*?-->|<\/([A-Za-z][A-Za-z0-9-]*)\s*>|<([A-Za-z][A-Za-z0-9-]*)((?:[^>"'/]|\/(?!>)|"[^"]*"|'[^']*')*)\/?>|([^<]+)/g;
    let m;
    while ((m = tokenRe.exec(cleaned))) {
        if (m[0].startsWith('<!--')) continue;
        if (m[1]) {
            if (stack.length > 1) stack.pop();
            continue;
        }
        if (m[2]) {
            const tag = m[2];
            const attrs = {};
            const attrRe = /([^\s=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
            let a;
            while ((a = attrRe.exec(m[3] || ''))) {
                attrs[a[1]] = a[2] !== undefined ? a[2] : (a[3] !== undefined ? a[3] : (a[4] !== undefined ? a[4] : ''));
            }
            const el = new El(tag, attrs);
            stack[stack.length - 1].appendChild(el);
            el.ownerDocument = doc;
            if (!/\/$/.test(m[0]) && !['BR', 'IMG', 'INPUT', 'HR', 'META', 'LINK', 'USE', 'PATH'].includes(el.tagName)) {
                stack.push(el);
            }
            continue;
        }
        if (m[4] && m[4].trim()) {
            const text = new TextNode(m[4]);
            stack[stack.length - 1].appendChild(text);
        }
    }
    return root;
}

// ---------------------------------------------------------------------------
// 3) 页面环境：history / fetch / 事件 / 真实渲染出的 DOM
// ---------------------------------------------------------------------------

function createPage() {
    const doc = new El('html');
    const body = new El('body');
    doc.appendChild(body);

    // 真实渲染出的页面结构（含 #books-container、四个筛选控件、#active-filters …）
    const parsed = parseHtml(renderedHtml, doc);
    for (const child of [...parsed.childNodes]) body.appendChild(child);

    const documentListeners = new Map();
    const historyCalls = [];
    const fetchCalls = [];

    doc.documentElement = doc;
    doc.body = body;
    doc.head = new El('head');
    doc.getElementById = (id) => doc.querySelector('#' + id);
    doc.createElement = (tag) => new El(tag);
    doc.createTextNode = (t) => new TextNode(t);
    doc.addEventListener = (type, fn) => {
        if (!documentListeners.has(type)) documentListeners.set(type, []);
        documentListeners.get(type).push(fn);
    };
    doc.removeEventListener = () => {};
    doc.dispatchEvent = (event) => {
        (documentListeners.get(event.type) || []).forEach((fn) => fn(event));
        return true;
    };
    doc.querySelectorAll = El.prototype.querySelectorAll.bind(doc);
    doc.querySelector = El.prototype.querySelector.bind(doc);

    const location = {
        href: 'http://local.test/new-books',
        search: '',
        origin: 'http://local.test',
        reload() { location._reloaded = true; },
    };

    const history = {
        pushState(_s, _t, url) {
            historyCalls.push({ kind: 'push', url });
            applyUrl(url);
        },
        replaceState(_s, _t, url) {
            historyCalls.push({ kind: 'replace', url });
            applyUrl(url);
        },
    };

    function applyUrl(url) {
        if (url == null) return;
        location.href = 'http://local.test' + url;
        const q = url.indexOf('?');
        location.search = q === -1 ? '' : url.slice(q);
    }

    const store = new Map();
    const localStorage = {
        getItem: (k) => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => store.set(k, String(v)),
        removeItem: (k) => store.delete(k),
    };

    const winListeners = new Map();
    const windowObj = {
        document: doc,
        location,
        history,
        localStorage,
        __APP_LANG__: 'en',
        URL,
        URLSearchParams,
        Date,
        setTimeout,
        clearTimeout,
        console,
        // base.js 初始化主题/导航高度时用到的浏览器 API（与本套断言无关，给安全默认值）
        matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
        requestAnimationFrame: (fn) => setTimeout(fn, 0),
        cancelAnimationFrame: (id) => clearTimeout(id),
        getComputedStyle: () => ({ getPropertyValue: () => '' }),
        innerWidth: 1280,
        innerHeight: 800,
        t: (key, lang, params) => `${key}:${lang}:${params ? params.days : ''}`,
        addEventListener: (type, fn) => {
            if (!winListeners.has(type)) winListeners.set(type, []);
            winListeners.get(type).push(fn);
        },
        removeEventListener: () => {},
        dispatchEvent: (event) => {
            (winListeners.get(event.type) || []).forEach((fn) => fn(event));
            return true;
        },
    };
    windowObj.window = windowObj;
    windowObj.globalThis = windowObj;
    windowObj.navigator = { language: 'en-US', userLanguage: '', languages: ['en-US'] };
    windowObj.CustomEvent = CustomEventShim;

    return {
        doc, windowObj, historyCalls, fetchCalls, location, localStorage,
        /** 触发 window 事件（languagechange / popstate）。 */
        emit(type, detail) {
            (winListeners.get(type) || []).forEach((fn) => fn({ type, detail }));
        },
        /** 填好四个筛选控件并派发 change（真实用户操作路径）。 */
        selectFilter(id, value) {
            const el = doc.getElementById(id);
            assert.ok(el, `缺少筛选控件 #${id}`);
            el.value = value;
            el.dispatchEvent({ type: 'change', target: el, preventDefault() {} });
        },
    };
}

/**
 * 排空微任务队列，让 `fetch(...).then(...).then(...)` 整条链跑完。
 * 固定次数的 `await Promise.resolve()` 很脆（链上任何一个 then 都会多消耗一轮），
 * 这里直接让事件循环转若干轮，且不允许吞掉链上的 rejection。
 */
async function flush(times = 12) {
    for (let i = 0; i < times; i += 1) await new Promise((r) => setImmediate(r));
}
/** 造一页可用的 API 响应。 */
function bookPayload(id, title, { pages = 1, page = 1, total = 1 } = {}) {    return {
        success: true,
        data: {
            books: [{
                id,
                title,
                title_zh: title + '·中',
                author: 'Author',
                isbn13: '978000000000' + id,
                category: 'Business',
                category_zh: '商业',
                category_en: 'Business',
                publisher_name: '出版社',
                publisher_name_en: 'Publisher',
                publication_date: '2020-01-01',
                cover_url: '',
            }],
            pagination: { page, pages, total, per_page: 20 },
        },
    };
}

/** CustomEvent 的最小实现（模板脚本用它派发 booklanguagechange）。 */
class CustomEventShim {
    constructor(type, init) {
        this.type = type;
        this.detail = (init || {}).detail;
    }
}

/**
 * 在 vm 里加载模板内联脚本。
 * `fetchImpl(url, init)` 返回一个 thenable/promise；测试据此控制响应先后。
 */
function bootPage({ fetchImpl, withBookI18n = true } = {}) {
    const page = createPage();
    const context = vm.createContext({
        window: page.windowObj,
        document: page.doc,
        location: page.location,
        navigator: page.windowObj.navigator,
        history: page.windowObj.history,
        localStorage: page.localStorage,
        console,
        Date,
        URL,
        URLSearchParams,
        Promise,
        Array,
        Object,
        String,
        Number,
        Boolean,
        Math,
        JSON,
        Error,
        isNaN,
        parseInt,
        encodeURIComponent,
        setTimeout,
        clearTimeout,
        Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
        AbortController,
        CustomEvent: CustomEventShim,
        fetch: (url, init) => {
            page.fetchCalls.push({ url, init });
            return fetchImpl(url, init);
        },
    });
    context.globalThis = context;

    if (withBookI18n) {
        // 页面脚本依赖 base.js 暴露的全局 esc（模板里直接调用 esc(...)），
        // 加载真实实现而不是在测试里另写一份转义函数。
        vm.runInContext(readFileSync(BASE_JS_PATH, 'utf8'), context);
        vm.runInContext(readFileSync(BOOK_I18N_PATH, 'utf8'), context);
        // 浏览器里 `window.foo = x` 会同时成为裸全局 `foo`；vm 上下文没有这条语法糖，
        // 这里显式把 base.js 挂到 window 上的工具（esc / escapeHtml …）映射成全局。
        for (const name of ['esc', 'escapeHtml', 'BookRankCover']) {
            if (name in page.windowObj && !(name in context)) {
                context[name] = page.windowObj[name];
            }
        }
    }
    vm.runInContext(pageScript, context);
    // 模板把筛选控件/按钮的事件绑定放在 DOMContentLoaded 里：真实浏览器解析完
    // 文档就会触发，测试里必须显式派发，否则控件上根本没有 change 监听。
    page.doc.dispatchEvent({ type: 'DOMContentLoaded' });
    // vm 里 `let isLoading` 是脚本作用域的词法绑定，不会成为 context 的属性；
    // 用 eval 在同一 context 里求值，读到的是被测脚本真正的变量本身。
    page.context_isLoading = () => vm.runInContext('isLoading', context);
    page.context_currentLanguage = () => vm.runInContext('currentLanguage', context);
    page.context_inFlight = () => vm.runInContext('inFlightController', context);
    return { page, context };
}

// ---------------------------------------------------------------------------
// 4) BookI18n：初始 apply 与切语言都不得破坏内层链接 / 卷号兄弟节点
// ---------------------------------------------------------------------------

/** 造一张与生产 SSR 结构一致的卡片（含内层书名链接 + 卷号兄弟节点）。 */
function seedSsrCard(page, { isbn = '9780000000001', href = '/new-book/7', volume = '第1卷' } = {}) {
    const container = page.doc.getElementById('books-container');
    container.innerHTML = '';
    const card = parseHtml(
        '<div class="book-card" data-book-id="7" data-isbn="' + isbn + '">' +
        '<a class="book-cover-link" href="' + href + '" tabindex="-1"><div class="book-cover-wrapper"></div></a>' +
        '<div class="book-info">' +
        '<div class="book-title" title="Volume One" data-en="Volume One" data-zh="第一卷" data-isbn="' + isbn + '">' +
        '<a class="browse-card-title-link" href="' + href + '">Volume One</a>' +
        '<span class="browse-card-volume">' + volume + '</span>' +
        '</div>' +
        '<div class="book-author" data-en="Author">Author</div>' +
        '</div></div>',
        page.doc,
    ).childNodes[0];
    card.ownerDocument = page.doc;
    container.appendChild(card);
    return card;
}

test('BookI18n：首次 apply 语言不破坏书名链接与卷号兄弟节点', () => {
    const { page, context } = bootPage({ fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({}) }) });
    const card = seedSsrCard(page);

    context.BookI18n.clear();
    context.BookI18n.register('9780000000001', {
        isbn13: '9780000000001', title: 'Volume One', title_zh: '第一卷', category: 'Business',
    });
    context.BookI18n.applyLanguage('zh');

    const titleEl = card.querySelector('.book-title');
    assert.equal(titleEl.textContent.includes('第一卷'), true, '中文标题未应用');
    const link = titleEl.querySelector('a');
    assert.ok(link, 'applyLanguage 把书名 <a> 抹掉了（卡片不再可点）');
    assert.equal(link.getAttribute('href'), '/new-book/7', '详情路由被破坏');
    assert.equal(link.textContent, '第一卷', '内层链接文本未更新');
    assert.ok(titleEl.querySelector('.browse-card-volume'), '卷号兄弟节点被覆盖掉了');
});

test('BookI18n：EN→ZH→EN 连续切语言仍保住链接 href 与卷号', () => {
    const { page, context } = bootPage({ fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({}) }) });
    const card = seedSsrCard(page, { href: '/new-book/42' });
    context.BookI18n.clear();
    context.BookI18n.register('9780000000001', {
        isbn13: '9780000000001', title: 'Volume One', title_zh: '第一卷', category: 'Business',
    });

    for (const lang of ['en', 'zh', 'en']) {
        context.BookI18n.applyLanguage(lang);
        const titleEl = card.querySelector('.book-title');
        const link = titleEl.querySelector('a');
        assert.ok(link, `${lang}: 书名 <a> 丢失`);
        assert.equal(link.getAttribute('href'), '/new-book/42', `${lang}: href 被改写`);
        assert.ok(titleEl.querySelector('.browse-card-volume'), `${lang}: 卷号丢失`);
    }
    assert.equal(card.querySelector('.book-title a').textContent, 'Volume One', '切回 EN 后标题未复原');
});

test('BookI18n：详情页新布局 .detail-meta / .detail-meta-row 也能按 label 找到分类值', () => {
    const { page, context } = bootPage({ fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({}) }) });
    const container = page.doc.getElementById('books-container');
    container.innerHTML = '';
    // 新版详情布局：.detail-meta > .detail-meta-row > dt.meta-label + dd.meta-value（无 data-cat-*）
    const detail = parseHtml(
        '<div class="detail-meta"><div class="detail-meta-row">' +
        '<dt class="meta-label" data-i18n="book_category">分类</dt>' +
        '<dd class="meta-value">商业</dd>' +
        '</div></div>',
        page.doc,
    ).childNodes[0];
    container.appendChild(detail);

    context.BookI18n.clear();
    context.BookI18n.register('9780000000001', {
        isbn13: '9780000000001', title: 'Volume One', title_zh: '第一卷',
        category_name: 'Business', category: 'Business',
    });
    context.BookI18n.applyLanguage('en');

    const value = container.querySelector('.detail-meta .meta-value');
    assert.ok(value, '未渲染出新布局的分类值');
    assert.equal(value.textContent, 'Business', '新布局 .detail-meta-row 的分类值未被 BookI18n 更新');
});

test('BookI18n：旧布局 .detail-meta-grid / .meta-card 行为不变', () => {
    const { page, context } = bootPage({ fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({}) }) });
    const container = page.doc.getElementById('books-container');
    container.innerHTML = '';
    const detail = parseHtml(
        '<div class="detail-meta-grid"><div class="meta-card">' +
        '<span class="meta-label" data-i18n="book_category">分类</span>' +
        '<span class="meta-value">商业</span>' +
        '</div></div>',
        page.doc,
    ).childNodes[0];
    container.appendChild(detail);

    context.BookI18n.clear();
    context.BookI18n.register('9780000000001', {
        isbn13: '9780000000001', title: 'Volume One', title_zh: '第一卷',
        category_name: 'Business', category: 'Business',
    });
    context.BookI18n.applyLanguage('en');

    const value = container.querySelector('.detail-meta-grid .meta-value');
    assert.ok(value, '旧布局分类值丢失');
    assert.equal(value.textContent, 'Business', '旧布局 .meta-card 行为被改坏');
});

// ---------------------------------------------------------------------------
// 5) 筛选状态机：选中 / chip / Back-Forward / 语言重绘
// ---------------------------------------------------------------------------

test('选中筛选：写 URL、加 chip、刷新计数与结果', async () => {
    const { page } = bootPage({
        fetchImpl: () => Promise.resolve({ json: () => Promise.resolve(bookPayload(1, 'Business Book')) }),
    });

    page.selectFilter('category-filter', '商业');
    await flush();
    assert.equal(page.historyCalls.filter((c) => c.kind === 'push').length, 1, '用户操作应 pushState 一次');

    const bar = page.doc.getElementById('active-filters');
    const chip = bar.querySelector('[data-chip-key="category"]');
    assert.ok(chip, '选中分类后没有渲染 chip');
    assert.equal(bar.hidden, false, 'chip 容器仍被隐藏');
    assert.ok(page.doc.getElementById('books-container').textContent.includes('Business Book'), '结果卡片未更新');
    assert.equal(page.doc.getElementById('result-summary-count').textContent, '1', '计数未更新');
});

test('移除一个 chip 保留其余条件', async () => {
    const { page } = bootPage({
        fetchImpl: () => Promise.resolve({ json: () => Promise.resolve(bookPayload(1, 'Book')) }),
    });
    page.selectFilter('category-filter', '商业');
    page.selectFilter('search-input', 'Title');
    await flush();

    const bar = page.doc.getElementById('active-filters');
    assert.ok(bar.querySelector('[data-chip-key="category"]'), '缺分类 chip');
    assert.ok(bar.querySelector('[data-chip-key="search"]'), '缺搜索 chip');

    // 真实 chip 点击：事件委托读 data-chip-key 后只清自己
    const categoryChip = bar.querySelector('[data-chip-key="category"]');
    page.doc.dispatchEvent({
        type: 'click',
        target: {
            // `sel` 原样交给 matchCompound：它自己就认 `.class` / `#id` / `[attr]` 三种写法
            // （此前套了一层 `.replace(/^\./, '.')`，那是把 `.` 替换成 `.` 的空操作）。
            closest: (sel) => (matchCompound(categoryChip, sel) || sel === '[data-chip-key]' ? categoryChip : null),
        },
        preventDefault() {},
    });
    await flush();

    const after = page.doc.getElementById('active-filters');
    assert.equal(after.querySelector('[data-chip-key="category"]'), null, '分类 chip 未被移除');
    assert.ok(after.querySelector('[data-chip-key="search"]'), '移除分类时误删了搜索 chip');
    assert.equal(page.doc.getElementById('category-filter').value, '', '分类控件未清空');
    assert.equal(page.doc.getElementById('search-input').value, 'Title', '搜索控件被误清空');
    assert.ok(page.location.search.includes('search=Title'), '移除分类时丢了搜索条件');
    assert.ok(!page.location.search.includes('category='), 'URL 里仍有分类');
});

test('Back/Forward：恢复控件/卡片/chips，且不新增历史记录', async () => {
    const { page } = bootPage({
        fetchImpl: () => Promise.resolve({ json: () => Promise.resolve(bookPayload(2, 'Restored Book')) }),
    });

    // 模拟浏览器 Back 到 ?days=180
    page.location.href = 'http://local.test/new-books?days=180';
    page.location.search = '?days=180';
    page.emit('popstate');

    await flush();

    assert.equal(page.historyCalls.filter((c) => c.kind === 'push').length, 0, 'Back 恢复不得 pushState');
    const replaces = page.historyCalls.filter((c) => c.kind === 'replace');
    assert.equal(replaces.length, 1, 'Back 恢复应恰好 replaceState 一次');
    assert.equal(page.doc.getElementById('days-filter').value, '180', 'Back 后控件未恢复');
    assert.ok(page.doc.getElementById('books-container').textContent.includes('Restored Book'), 'Back 后卡片未刷新');
});

test('AJAX 渲染的卡片保留明文 ISBN（#248 曾移除，用户要求恢复）', async () => {
    // 回归锁：新书速递的卡片有 SSR 与 AJAX 两条渲染路径，这里跑的是真实内联脚本产出的
    // 那一份。bookPayload 的 isbn13 是 '978000000000' + id，故 id=1 → '9780000000001'。
    const { page } = bootPage({
        fetchImpl: () => Promise.resolve({ json: () => Promise.resolve(bookPayload(1, 'Business Book')) }),
    });

    page.selectFilter('category-filter', '商业');
    await flush();

    const container = page.doc.getElementById('books-container');
    assert.ok(
        container.textContent.includes('9780000000001'),
        'AJAX 卡片应渲染明文 ISBN，而不只是 data-isbn 属性（#248 曾整块删掉这段标记）',
    );
});

test('语言重绘不新增历史记录', async () => {
    const { page } = bootPage({
        fetchImpl: () => Promise.resolve({ json: () => Promise.resolve(bookPayload(3, 'Lang Book')) }),
    });
    const before = page.historyCalls.length;
    page.emit('languagechange', { language: 'zh' });
    await flush();

    const pushes = page.historyCalls.slice(before).filter((c) => c.kind === 'push');
    assert.equal(pushes.length, 0, '语言切换写入了新历史记录');
});

test('竞态：先发 A 后发 B 时，B 的状态胜出，A 的迟到响应不得覆盖', async () => {
    const pending = [];
    const { page } = bootPage({
        fetchImpl: (url, init) => new Promise((resolve) => {
            pending.push({ url, init, resolve });
        }),
    });

    // A：选中分类「商业」
    page.selectFilter('category-filter', '商业');
    assert.equal(pending.length, 1, 'A 请求未发出');

    // B：紧接着改选分类（不经 debounce，直接派发 change）——真实用户连续操作
    page.selectFilter('category-filter', '小说');
    assert.equal(pending.length, 2, 'B 请求被丢弃（仍是 if (isLoading) return 的旧行为）');
    // A 已被显式中止
    assert.ok(pending[0].init && pending[0].init.signal, 'A 请求没有携带 AbortSignal');
    assert.equal(pending[0].init.signal.aborted, true, '被取代的 A 请求未被 abort');

    /** 让一条挂起的 fetch 返回响应。 */
    const respond = (entry, payload) => {
        entry.resolve({ json: () => Promise.resolve(payload) });
    };

    // B 先返回：它是最新请求，应当胜出
    respond(pending[1], bookPayload(20, 'B Book'));
    await flush();

    // A 迟到返回（浏览器里 abort 后仍可能已收到响应）：必须是过期响应，不得覆盖 B
    respond(pending[0], bookPayload(10, 'A Book'));
    await flush();

    const container = page.doc.getElementById('books-container');
    assert.ok(container.textContent.includes('B Book'), '最新请求的结果未生效');
    assert.ok(!container.textContent.includes('A Book'), '过期响应覆盖了最新结果');
    assert.equal(page.doc.getElementById('result-summary-count').textContent, '1');

    // URL 与 chips 必须描述 B，而不是 A
    assert.ok(
        page.location.search.includes('category=%E5%B0%8F%E8%AF%B4'),
        `URL 未跟随最新请求：${page.location.search}`,
    );
    const bar = page.doc.getElementById('active-filters');
    const chips = bar.querySelectorAll('[data-chip-key]');
    assert.equal(chips.length, 1, 'chips 未反映最新请求的条件数');
    assert.equal(chips[0].getAttribute('data-chip-key'), 'category');
});

test('竞态：过期请求的失败不得覆盖最新 UI', async () => {
    const deferred = [];
    const { page } = bootPage({
        fetchImpl: () => new Promise((resolve, reject) => { deferred.push({ resolve, reject }); }),
    });

    page.selectFilter('category-filter', '商业');
    page.selectFilter('category-filter', '小说');
    assert.equal(deferred.length, 2, '第二个请求未发出');

    deferred[1].resolve({ json: () => Promise.resolve(bookPayload(30, 'Latest Book')) });
    await flush();

    // 旧请求失败（被 abort 或网络错误）：不得把最新卡片换成错误态
    deferred[0].reject(new Error('aborted'));
    await flush();

    const container = page.doc.getElementById('books-container');
    assert.ok(container.textContent.includes('Latest Book'), '过期请求的失败覆盖了最新结果');
    assert.equal(page.doc.querySelector('#btn-retry'), null, '错误态不应由过期请求写入');
});

test('真实失败：最新请求失败仍渲染错误态与重试按钮（保留原有行为）', async () => {
    const { page } = bootPage({
        fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ success: false, message: 'boom' }) }),
    });

    page.selectFilter('category-filter', '商业');
    await flush();

    assert.equal(page.doc.querySelector('#btn-retry') !== null, true, '最新请求失败未渲染重试按钮');
    assert.ok(page.doc.getElementById('books-container').textContent.includes('boom'), '错误信息未展示');
});

test('用户筛选请求在途时切语言：同一次用户动作只发一次请求、只 push 一条历史，结果按新语言渲染', async () => {
    const pending = [];
    const { page } = bootPage({
        fetchImpl: (url, init) => new Promise((resolve, reject) => {
            pending.push({ url, init, resolve, reject });
        }),
    });

    // 用户动作：选中分类 → 立刻进入在途状态（isLoading 必须一直为真到最新请求落定）
    page.selectFilter('category-filter', '商业');
    assert.equal(pending.length, 1, '用户动作未发出请求');
    assert.equal(page.context_isLoading(), true, 'isLoading 在请求在途期间被提前复位');

    // 语言切换：只重绘标签，不得 abort / 替换这条在途请求
    page.emit('languagechange', { language: 'zh' });
    await flush();

    assert.equal(pending.length, 1, '语言切换重复发起了请求（应为同一次用户动作只发一次 API）');
    assert.equal(pending[0].init.signal.aborted, false, '语言切换中止了在途的用户筛选请求');
    assert.equal(page.context_currentLanguage(), 'zh', '语言切换未生效');
    assert.equal(page.historyCalls.filter((c) => c.kind === 'push').length, 0, '请求尚未落定就写了历史');

    // 控件上的标签已按新语言重绘（applyNewBooksLanguage 路径）。
    // 断言的是**实际选中项**（与用户选的「商业」同一项）的渲染文本 —— 不是下拉框的
    // 第一项（那是 value="" 的「全部分类」占位符），也不从实现用的映射反推期望值。
    // 期望值来自 fixture 渲染出的真实选项：`{{ cat.name|category_name }} ({{ cat.count }})`
    // → 分类「商业」、count 1 ⇒ '商业 (1)'，同时钉住计数没被语言重绘吃掉。
    const categorySelect = page.doc.getElementById('category-filter');
    assert.equal(categorySelect.value, '商业', '控件的选中值不是用户选的分类');
    assert.equal(
        categorySelect.querySelector('option[value="商业"]').textContent,
        '商业 (1)',
        '语言切换后选中项文案未重绘（或计数在重绘中丢失）',
    );

    // 请求返回：这是同一个用户动作的响应 —— 内容按**当前**语言渲染，并 push 一条历史
    pending[0].resolve({
        json: () => Promise.resolve({
            ...bookPayload(7, 'Volume One'),
            data: {
                books: [{
                    id: 7,
                    title: 'Volume One',
                    title_zh: '第一卷',
                    author: 'Author',
                    author_zh: '作者',
                    isbn13: '9780000000007',
                    category: 'Business',
                    category_zh: '商业',
                    category_en: 'Business',
                    publisher_name: '出版社',
                    publisher_name_en: 'Publisher',
                    publication_date: '2020-01-01',
                    cover_url: '',
                }],
                pagination: { page: 1, pages: 1, total: 1, per_page: 20 },
            },
        }),
    });
    await flush();

    const pushes = page.historyCalls.filter((c) => c.kind === 'push');
    assert.equal(pushes.length, 1, `同一次用户动作应恰好 push 一条历史，实际 ${pushes.length}`);
    assert.ok(
        pushes[0].url.includes('category=%E5%95%86%E4%B8%9A'),
        `push 的历史 URL 未保留用户选中的条件：${pushes[0].url}`,
    );
    assert.equal(page.historyCalls.filter((c) => c.kind === 'replace').length, 0, '语言切换写了 replace 历史');

    const container = page.doc.getElementById('books-container');
    assert.ok(container.textContent.includes('第一卷'), '响应未按切语言后的 currentLanguage 渲染中文标题');
    assert.ok(!container.textContent.includes('Volume One'), '响应仍渲染了旧语言标题');

    // 最新请求落定后才复位：迟到的 finally 不得清除更新的在途标志
    assert.equal(page.context_isLoading(), false, '最新请求落定后 isLoading 未复位');
    assert.equal(page.context_inFlight(), null, '最新请求落定后 inFlightController 未释放');

    // 旧请求（被中止的 A）完成/失败/finally 都不得清掉最新请求的旗标
    page.selectFilter('category-filter', '小说');
    assert.equal(pending.length, 2, '第二次用户动作被 isLoading 拦下');
    assert.equal(page.context_isLoading(), true, '最新请求在途时 isLoading 不为真');
    // 注意：这里**不能**断言 pending[0] 的 signal 已被 abort。上一次请求在上面的
    // flush() 里就已经完全落定，loadBooks 的 finally 已经把 inFlightController 置空；
    // 这次新建的 controller 取代的是一个已经结束的请求，没有任何信号需要中止。
    // 「被取代的在途请求必须被 abort」是下面那个真正重叠的 A/B 用例的职责。
    assert.notEqual(pending[1].init.signal, pending[0].init.signal, '两次请求复用了同一个 AbortSignal');

    pending[1].resolve({ json: () => Promise.resolve(bookPayload(8, 'Newest Book')) });
    await flush();
    assert.equal(page.context_isLoading(), false, '最新请求落定后 isLoading 未复位（被旧请求的 finally 抢先复位？）');
    assert.ok(
        page.doc.getElementById('books-container').textContent.includes('Newest Book'),
        '最新请求的结果未生效',
    );
});

test('过期请求的 finally 不得清掉更新请求的在途标志', async () => {
    const pending = [];
    const { page } = bootPage({
        fetchImpl: (url, init) => new Promise((resolve) => { pending.push({ url, init, resolve }); }),
    });

    page.selectFilter('category-filter', '商业');   // A（将被取代）
    page.selectFilter('category-filter', '小说');   // B（最新）
    assert.equal(pending.length, 2, '最新请求未发出');
    assert.equal(page.context_isLoading(), true, '最新请求在途时 isLoading 不为真');

    // A 迟到返回：它的完成与 finally 都不得复位 B 的旗标 / 释放 B 的 controller
    const bSignal = pending[1].init.signal;
    assert.ok(bSignal, 'B 请求没有携带 AbortSignal');
    pending[0].resolve({ json: () => Promise.resolve(bookPayload(10, 'A Book')) });
    await flush();
    assert.equal(page.context_isLoading(), true, '过期请求的 finally 清掉了最新请求的 isLoading');
    // context_inFlight() 返回的是 AbortController（不是 signal）：只有比 signal 才是在问
    // "B 的 controller 是否还在"。拿它直接和 bSignal 比会永远为假，等于没测。
    const bController = page.context_inFlight();
    assert.ok(bController, '最新请求在途时 inFlightController 已被释放');
    assert.equal(bController.signal, bSignal, '过期请求的 finally 释放了最新请求的 controller');

    pending[1].resolve({ json: () => Promise.resolve(bookPayload(20, 'B Book')) });
    await flush();
    assert.equal(page.context_isLoading(), false, '最新请求落定后 isLoading 未复位');
    const container = page.doc.getElementById('books-container');
    assert.ok(container.textContent.includes('B Book'), '最新请求的结果未生效');
    assert.ok(!container.textContent.includes('A Book'), '过期响应覆盖了最新结果');
});
