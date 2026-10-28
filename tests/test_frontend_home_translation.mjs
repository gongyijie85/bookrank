import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const source = readFileSync(new URL('static/js/index.js', root), 'utf8');
const helperPath = new URL('static/js/home-translation.js', root);

function node(text = '') {
    const attrs = new Map();
    return {
        textContent: text,
        style: {},
        getAttribute: key => attrs.get(key) || null,
        setAttribute: (key, value) => attrs.set(key, String(value)),
        removeAttribute: key => attrs.delete(key),
        querySelector: () => null,
    };
}

function card(book, marked = true, mobile = false) {
    const element = node();
    element.setAttribute('data-isbn', book.isbn13);
    if (marked) element.setAttribute('data-needs-translation', '1');
    element.title = node(book.title_zh || book.title);
    element.description = node(book.description_zh || book.description || '');
    element.content = { appendChild(child) { element.description = child; } };
    element.querySelector = selector => {
        if (selector === '.card-content' || selector === '.m-book-info') return element.content;
        if (selector.includes(mobile ? '.m-book-title' : '.card-title')) return element.title;
        if (selector.includes(mobile ? '.m-book-card-desc' : '.card-desc')) return element.description;
        return null;
    };
    return element;
}

function book(id, overrides = {}) {
    return { isbn13: String(9780000000000 + id), title: `Book ${id}`, description: `Description ${id}`, ...overrides };
}

function response(translated, status = 200) {
    return { ok: status >= 200 && status < 300, status, json: async () => ({ success: true, data: { book: translated } }) };
}

function page(books, request = async () => response({}), options = {}) {
    const timers = [];
    const listeners = new Map();
    const calls = [];
    const container = { innerHTML: '', addEventListener() {} };
    const state = { cards: books.map(value => card(value, options.marked !== false)) };
    const initial = { textContent: JSON.stringify(books) };
    const context = vm.createContext({
        console,
        URLSearchParams,
        CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
        setTimeout(fn) { timers.push(fn); },
        localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
        window: {
            APP_CONFIG: {
                defaultCover: '/static/default-cover.png', currentCategory: 'hardcover-nonfiction',
                translationPlaceholders: ['暂无简介', 'No summary available.'],
            },
            location: { search: '?lang=zh', pathname: '/', href: '' },
            history: { pushState() {} },
            dispatchEvent() {},
            addEventListener(type, fn) { listeners.set(type, fn); },
        },
        document: {
            createElement: () => node(),
            documentElement: { lang: 'zh-CN', getAttribute: () => 'zh-CN' },
            addEventListener() {},
            getElementById: id => id === 'initial-books-data' ? initial : id === 'books-grid' ? container : null,
            querySelector: () => null,
            querySelectorAll(selector) {
                return selector.includes('data-needs-translation')
                    ? state.cards.filter(value => value.getAttribute('data-needs-translation') === '1')
                    : selector.includes('data-isbn') ? state.cards : [];
            },
        },
        esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;'),
        t: key => key,
        fetch: async (url, opts) => {
            calls.push({ url, opts });
            return request(url, opts);
        },
    });
    context.window.fetch = context.fetch;
    if (existsSync(helperPath)) vm.runInContext(readFileSync(helperPath, 'utf8'), context);
    if (options.realBookI18n) {
        vm.runInContext(readFileSync(new URL('static/js/book-i18n.js', root), 'utf8'), context);
        context.BookI18n.registerAll(books);
    }
    vm.runInContext(source, context);
    return {
        context, calls, state, container,
        async drain() {
            for (let i = 0; i < 60; i++) {
                while (timers.length) timers.shift()();
                await new Promise(resolve => setImmediate(resolve));
            }
        },
        language(lang) { listeners.get('languagechange')({ detail: { language: lang } }); },
        async category(name, values) {
            state.cards = values.map(value => card(value));
            context.__categoryBooks = values;
            context.__categoryName = name;
            vm.runInContext('categoryCache.set(__categoryName, __categoryBooks, null, null, null)', context);
            await context.changeCategory(name);
        },
    };
}

test('a translated title with missing Chinese description is still queued', async () => {
    const target = book(1, { title_zh: '已有书名' });
    const p = page([target], async () => response({ title_zh: '替代书名', description_zh: '补充中文简介' }), { marked: false });
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.equal(p.state.cards[0].title.textContent, '已有书名');
    assert.equal(p.state.cards[0].description.textContent, '补充中文简介');
});

test('HTTP 200 without translated content retains the missing marker', async () => {
    const p = page([book(1)]);
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
});

test('503 stops the rest of the page instead of requesting every card', async () => {
    const p = page([book(1), book(2)], async () => response(null, 503));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
});

test('category rendering marks description-only gaps for translation', () => {
    const p = page([]);
    p.context.updateBooksOnPage([book(1, { title_zh: '已译标题' })], 'hardcover-nonfiction', null);
    assert.match(p.container.innerHTML, /data-needs-translation="1"/);
});

test('a late Chinese result cannot overwrite the English view', async () => {
    let resolve;
    const p = page([book(1)], () => new Promise(done => { resolve = done; }));
    p.context.initOnDemandTranslation();
    await p.drain();
    p.language('en');
    p.state.cards[0].title.textContent = 'Book 1';
    p.state.cards[0].description.textContent = 'Description 1';
    resolve(response({ title_zh: '新译标题', description_zh: '新译简介' }));
    await p.drain();
    assert.equal(p.state.cards[0].title.textContent, 'Book 1');
    assert.equal(p.state.cards[0].description.textContent, 'Description 1');
});

for (const status of [401, 403, 429, 500, 503]) {
    test(`${status} halts the queue for the page, including subsequent refreshes`, async () => {
        const p = page([book(1), book(2)], async () => response(null, status));
        p.context.initOnDemandTranslation();
        await p.drain();
        p.context.initOnDemandTranslation();
        p.language('en');
        p.language('zh');
        await p.drain();
        assert.equal(p.calls.length, 1);
        assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
    });
}

test('network failure stops without replaying an outcome-unknown POST', async () => {
    const p = page([book(1), book(2)], async () => { throw new Error('connection lost'); });
    p.context.initOnDemandTranslation();
    await p.drain();
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
});

test('a single-book 404 continues with the next ISBN', async () => {
    const p = page([book(1), book(2)], async url => url.endsWith('1')
        ? response(null, 404) : response({ title_zh: '第二本', description_zh: '第二本简介' }));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 2);
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
    assert.equal(p.state.cards[1].getAttribute('data-needs-translation'), null);
});

test('partial translation keeps the missing marker without retrying the same ISBN', async () => {
    const p = page([book(1)], async () => response({ title_zh: '只有书名' }));
    p.context.initOnDemandTranslation();
    await p.drain();
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.equal(p.state.cards[0].title.textContent, '只有书名');
    assert.equal(p.state.cards[0].description.textContent, 'Description 1');
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
});

test('existing Chinese description survives a title-only repair', async () => {
    const p = page([book(1, { description_zh: '已审定的中文简介' })], async () => response({ title_zh: '新书名', description_zh: '替代简介' }));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.state.cards[0].title.textContent, '新书名');
    assert.equal(p.state.cards[0].description.textContent, '已审定的中文简介');
});

test('English text incorrectly cached in Chinese fields is repaired instead of treated as complete', async () => {
    const target = book(1, { title_zh: 'Book 1', description_zh: 'Description 1' });
    const p = page([target], async () => response({ title_zh: '实际中文书名', description_zh: '实际中文简介' }), { marked: false });
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.equal(p.state.cards[0].title.textContent, '实际中文书名');
    assert.equal(p.state.cards[0].description.textContent, '实际中文简介');
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), null);
});

test('Chinese sources and server-provided placeholders do not trigger translation requests', async () => {
    const p = page([
        book(1, { title: '原本就是中文的书名', description: '原本就是中文的简介' }),
        book(2, { title_zh: '已有标题', description: '暂无简介' }),
        book(3, { title_zh: '已有标题', description: 'No summary available.' }),
    ]);
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 0);
    assert.ok(p.state.cards.every(value => value.getAttribute('data-needs-translation') === null));
});

test('English or ISBN-only translation responses cannot clear missing markers', async () => {
    const p = page([book(1), book(2)], async () => response({ title_zh: '9780000000001', description_zh: 'Description 1' }));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
    assert.equal(p.state.cards[0].title.textContent, 'Book 1');
});

test('an existing valid Chinese field returned without new fields does not halt other ISBNs', async () => {
    const p = page([book(1, { title_zh: '已有效的书名' }), book(2)], async url => url.endsWith('1')
        ? response({ title_zh: '已有效的书名' }) : response({ title_zh: '第二本书名', description_zh: '第二本简介' }));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 2);
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
    assert.equal(p.state.cards[0].title.textContent, '已有效的书名');
    assert.equal(p.state.cards[1].description.textContent, '第二本简介');
});

test('the queue deduplicates repeated cards and caps the whole page at 15 ISBNs', async () => {
    const values = Array.from({ length: 21 }, (_, index) => book(index + 1));
    const p = page([values[0], values[0], ...values.slice(1)], async () => response({ title_zh: '已译书名', description_zh: '已译简介' }));
    p.context.initOnDemandTranslation();
    p.context.initOnDemandTranslation();
    await p.drain();
    await p.category('business-books', [book(25)]);
    await p.drain();
    assert.equal(p.calls.length, 15);
    assert.equal(new Set(p.calls.map(value => value.url)).size, 15);
});

test('requests stay serial during repeated refreshes and category changes', async () => {
    const resolvers = [];
    let active = 0;
    let peak = 0;
    const p = page([book(1), book(2)], () => {
        active++;
        peak = Math.max(peak, active);
        return new Promise(resolve => resolvers.push(value => { active--; resolve(value); }));
    });
    p.context.initOnDemandTranslation();
    await p.drain();
    p.context.initOnDemandTranslation();
    await p.category('business-books', [book(3), book(4)]);
    await p.drain();
    assert.equal(p.calls.length, 1);
    resolvers.shift()(response({ title_zh: '第一本', description_zh: '第一本简介' }));
    await p.drain();
    assert.equal(p.calls.length, 2);
    assert.match(p.calls[1].url, /3$/);
    resolvers.shift()(response({ title_zh: '第三本', description_zh: '第三本简介' }));
    await p.drain();
    assert.equal(p.calls.length, 3);
    resolvers.shift()(response({ title_zh: '第四本', description_zh: '第四本简介' }));
    await p.drain();
    assert.equal(peak, 1);
    assert.deepEqual(p.state.cards.map(value => value.title.textContent), ['第三本', '第四本']);
});

test('a category switched before startup does not translate detached cards', async () => {
    const p = page([book(1)], async () => response({ title_zh: '译文', description_zh: '简介' }));
    p.context.initOnDemandTranslation();
    await p.category('business-books', [book(2)]);
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.match(p.calls[0].url, /2$/);
});

test('a rapid zh/en/zh switch keeps the in-flight result and continues once', async () => {
    let resolve;
    const p = page([book(1), book(2)], url => url.endsWith('1')
        ? new Promise(done => { resolve = done; }) : response({ title_zh: '第二本', description_zh: '第二本简介' }));
    p.context.initOnDemandTranslation();
    await p.drain();
    p.language('en');
    p.language('zh');
    resolve(response({ title_zh: '第一本', description_zh: '第一本简介' }));
    await p.drain();
    assert.equal(p.calls.length, 2);
    assert.equal(p.state.cards[0].title.textContent, '第一本');
    assert.equal(p.state.cards[1].title.textContent, '第二本');
});

test('returning from English renders the saved late translation without another POST', async () => {
    let resolve;
    const p = page([book(1)], () => new Promise(done => { resolve = done; }));
    p.context.initOnDemandTranslation();
    await p.drain();
    p.language('en');
    resolve(response({ title_zh: '迟到的书名', description_zh: '迟到的简介' }));
    await p.drain();
    p.language('zh');
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.match(p.container.innerHTML, /迟到的书名/);
    assert.equal(p.state.cards[0].description.textContent, '迟到的简介');
});

test('fresh translations survive real BookI18n language and category rerenders', async () => {
    const p = page([book(1)], async () => response({ title_zh: '真实语言包译文', description_zh: '真实语言包简介' }), { realBookI18n: true });
    p.context.initOnDemandTranslation();
    await p.drain();
    p.language('en');
    p.language('zh');
    assert.equal(p.state.cards[0].title.textContent, '真实语言包译文');
    await p.category('business-books', [book(1)]);
    await p.drain();
    assert.match(p.container.innerHTML, /真实语言包译文/);
    assert.equal(p.state.cards[0].description.textContent, '真实语言包简介');
    assert.equal(p.calls.length, 1);
});

test('late translation for an older description never fills a changed source', async () => {
    let resolve;
    const p = page([book(1)], () => new Promise(done => { resolve = done; }));
    p.context.initOnDemandTranslation();
    await p.drain();
    await p.category('business-books', [book(1, { description: 'An updated English description' })]);
    resolve(response({ title_zh: '相同书名', description_zh: '已过时的简介' }));
    await p.drain();
    assert.equal(p.state.cards[0].description.textContent, 'An updated English description');
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
});

test('a response for newer server source text cannot be attached to an older cached source', async () => {
    const p = page([book(1)], async () => response({
        title: 'A newer server title', description: 'A newer server description',
        title_zh: '服务端新版本书名', description_zh: '服务端新版本简介',
    }));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.state.cards[0].title.textContent, 'Book 1');
    assert.equal(p.state.cards[0].description.textContent, 'Description 1');
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
    p.language('en');
    p.language('zh');
    assert.doesNotMatch(p.container.innerHTML, /服务端新版本/);
    assert.equal(p.calls.length, 1);
});

test('source version checks apply separately to title and description', async () => {
    const p = page([book(1)], async () => response({
        title: 'Book 1', description: 'A newer description',
        title_zh: '源版本匹配的书名', description_zh: '源版本不匹配的简介',
    }));
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.state.cards[0].title.textContent, '源版本匹配的书名');
    assert.equal(p.state.cards[0].description.textContent, 'Description 1');
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), '1');
});

test('independent duplicate-ISBN snapshots keep each card’s reviewed Chinese through real language rerenders', async () => {
    const values = [
        book(1, { title_zh: '快照甲书名', description_zh: '快照甲审定简介' }),
        book(1, { title: 'Other source title', description: 'Other source description', title_zh: '快照乙书名', description_zh: '快照乙审定简介' }),
    ];
    const p = page(values, undefined, { realBookI18n: true });
    p.context.initOnDemandTranslation();
    assert.deepEqual(p.state.cards.map(value => value.title.textContent), ['快照甲书名', '快照乙书名']);
    assert.deepEqual(p.state.cards.map(value => value.description.textContent), ['快照甲审定简介', '快照乙审定简介']);
    p.language('en');
    p.language('zh');
    await p.drain();
    assert.deepEqual(p.state.cards.map(value => value.title.textContent), ['快照甲书名', '快照乙书名']);
    assert.deepEqual(p.state.cards.map(value => value.description.textContent), ['快照甲审定简介', '快照乙审定简介']);
    assert.equal(p.calls.length, 0);
});

test('repairing one duplicate-ISBN snapshot never replaces another snapshot’s reviewed translation', async () => {
    const values = [
        book(1, { title_zh: '已审定甲书名', description_zh: '已审定甲简介' }),
        book(1, { title: 'Second source', description: 'Second description', title_zh: '已审定乙书名' }),
    ];
    const p = page(values, async () => response({ title: 'Second source', description: 'Second description', title_zh: '替代乙书名', description_zh: '新增乙简介' }), { realBookI18n: true });
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.deepEqual(p.state.cards.map(value => value.title.textContent), ['已审定甲书名', '已审定乙书名']);
    assert.deepEqual(p.state.cards.map(value => value.description.textContent), ['已审定甲简介', '新增乙简介']);
});

test('a missing desktop description node is created inside card content after a successful repair', async () => {
    const p = page([book(1, { title_zh: '已有标题', description_zh: '暂无简介' })], async () => response({ description_zh: '现在可见的简介' }));
    p.state.cards[0].description = null;
    p.context.initOnDemandTranslation();
    await p.drain();
    assert.ok(p.state.cards[0].description, 'a successful translation must be visible even when SSR omitted the description node');
    assert.equal(p.state.cards[0].description.textContent, '现在可见的简介');
    assert.equal(p.state.cards[0].description.className, 'card-desc');
});

function mobilePage(values, request) {
    const p = page([]);
    p.state.cards = values.map(value => card(value, true, true));
    p.context.document.getElementById = id => id === 'initial-books-data' ? { textContent: JSON.stringify(values) } : null;
    p.context.window.MobileApp = { csrfFetch: async (url, opts) => { p.calls.push({ url, opts }); return request(url, opts); } };
    const template = readFileSync(new URL('templates/mobile/index.html', root), 'utf8');
    const script = [...template.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)]
        .map(value => value[1]).find(value => value.includes('BookRankHomeTranslation.create'));
    assert.ok(script, 'the real mobile template must initialize the shared queue');
    vm.runInContext(script.replace('{{ PLACEHOLDER_TEXTS|list|tojson }}', '["暂无简介", "No summary available."]'), p.context);
    return p;
}

test('mobile template uses the CSRF adapter and fills description-only gaps with an 80-character preview', async () => {
    const description = '中文简介'.repeat(30);
    const p = mobilePage([book(1, { title_zh: '已有移动书名' })], async () => response({ title_zh: '替代移动书名', description_zh: description }));
    await p.drain();
    assert.equal(p.calls.length, 1);
    assert.equal(p.calls[0].opts.method, 'POST');
    assert.equal(p.state.cards[0].title.textContent, '已有移动书名');
    assert.equal(p.state.cards[0].description.textContent, description.slice(0, 80) + '…');
    assert.equal(p.state.cards[0].getAttribute('data-needs-translation'), null);
});

test('mobile language switch keeps late results out of the English view', async () => {
    let resolve;
    const p = mobilePage([book(1)], () => new Promise(done => { resolve = done; }));
    await p.drain();
    p.language('en');
    resolve(response({ title_zh: '移动中文', description_zh: '移动简介' }));
    await p.drain();
    assert.equal(p.state.cards[0].title.textContent, 'Book 1');
    p.language('zh');
    await p.drain();
    assert.equal(p.state.cards[0].title.textContent, '移动中文');
    assert.equal(p.calls.length, 1);
});

test('a missing mobile description node becomes a visible translated preview', async () => {
    const p = mobilePage([book(1, { title_zh: '已有移动标题', description_zh: '暂无简介' })], async () => response({ description_zh: '移动端现在可见的简介' }));
    p.state.cards[0].description = null;
    await p.drain();
    assert.ok(p.state.cards[0].description);
    assert.equal(p.state.cards[0].description.textContent, '移动端现在可见的简介');
    assert.equal(p.state.cards[0].description.className, 'm-book-card-desc');
});
