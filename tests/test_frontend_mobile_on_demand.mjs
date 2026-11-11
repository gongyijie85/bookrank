import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/mobile/js/home-translation.js', import.meta.url), 'utf8');

function mobilePage({ lang = 'zh', responses = [] } = {}) {
    const calls = [];
    const retries = [];
    const cards = [makeCard('9781639739134'), makeCard('9780316563857')];
    function makeCard(isbn) {
        const attrs = new Map([['data-isbn', isbn], ['data-needs-translation', '1'], ['data-needs-title', '1'], ['data-needs-description', '1']]);
        const title = { textContent: 'ENGLISH TITLE', insertAdjacentElement(_where, value) { card.original = value; } };
        const desc = { textContent: 'ENGLISH SUMMARY' };
        const card = {
            title, desc, original: null,
            getAttribute(key) { return attrs.get(key) ?? null; },
            removeAttribute(key) { attrs.delete(key); },
            querySelector(selector) {
                if (selector === '.m-book-title') return title;
                if (selector === '.m-book-card-desc') return desc;
                if (selector === '.m-book-original-title') return this.original;
                return null;
            },
        };
        return card;
    }
    const document = {
        readyState: 'complete',
        documentElement: { getAttribute: key => key === 'data-lang' ? lang : '' },
        querySelectorAll: () => cards.filter(card => card.getAttribute('data-needs-translation')),
        createElement: () => ({ className: '', textContent: '' }),
    };
    const window = { MobileApp: { csrfFetch(url, options) {
        calls.push({ url, method: options.method });
        const response = responses[calls.length - 1] ?? { status: 200, book: { title_zh: '中文书名', description_zh: '中文简介' } };
        return Promise.resolve({ ok: response.status === 200, status: response.status, json: async () => ({ success: true, data: { book: response.book } }) });
    } } };
    vm.runInNewContext(source, {
        document, window, setTimeout: (fn, delay) => delay === 20000 ? retries.push(fn) : fn(),
        console, Array, encodeURIComponent,
    });
    return { cards, calls, retries };
}

test('mobile Chinese homepage translates missing cards in order and preserves the English title', async () => {
    const page = mobilePage();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(page.calls.map(item => item.url), ['/api/translate/book/9781639739134', '/api/translate/book/9780316563857']);
    assert.equal(page.cards[0].title.textContent, '中文书名');
    assert.equal(page.cards[0].desc.textContent, '中文简介');
    assert.equal(page.cards[0].original.textContent, 'ENGLISH TITLE');
    assert.equal(page.cards[0].getAttribute('data-needs-translation'), null);
});

test('mobile English homepage does not start translation', async () => {
    const page = mobilePage({ lang: 'en' });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.calls.length, 0);
});

test('mobile unavailable translation retries once after a delay and keeps pending markers', async () => {
    const page = mobilePage({ responses: [{ status: 503 }, { status: 503 }] });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.calls.length, 1);
    assert.equal(page.retries.length, 1);
    page.retries[0]();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.calls.length, 2);
    assert.equal(page.retries.length, 1);
    assert.equal(page.cards[0].getAttribute('data-needs-translation'), '1');
    assert.equal(page.cards[1].title.textContent, 'ENGLISH TITLE');
});

test('mobile translation resumes the queue when the delayed retry succeeds', async () => {
    const page = mobilePage({ responses: [
        { status: 503 },
        { status: 200, book: { title_zh: '恢复书名', description_zh: '恢复简介' } },
    ] });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.retries.length, 1);
    page.retries[0]();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.calls.length, 3);
    assert.equal(page.cards[0].desc.textContent, '恢复简介');
    assert.equal(page.cards[1].title.textContent, '中文书名');
});

test('mobile rate limiting stops without scheduling a delayed retry', async () => {
    const page = mobilePage({ responses: [{ status: 429 }] });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.calls.length, 1);
    assert.equal(page.retries.length, 0);
});

test('mobile partial results preserve untranslated description without retrying immediately', async () => {
    const page = mobilePage({ responses: [{ status: 200, book: { title_zh: '中文书名' } }] });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(page.cards[0].title.textContent, '中文书名');
    assert.equal(page.cards[0].desc.textContent, 'ENGLISH SUMMARY');
    assert.equal(page.cards[0].getAttribute('data-needs-translation'), '1');
    assert.equal(page.cards[0].getAttribute('data-needs-title'), null);
    assert.equal(page.cards[0].getAttribute('data-needs-description'), '1');
    assert.equal(page.calls.length, 2);
});
