import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const source = readFileSync(new URL('../static/js/cover.js', import.meta.url), 'utf8');

function loadCover(overrides = {}) {
    const root = {
        location: { origin: 'http://local.test' },
        Date,
        setTimeout,
        URL,
        URLSearchParams,
        ...overrides,
    };
    const context = vm.createContext({
        window: root,
        globalThis: root,
        URL,
        URLSearchParams,
    });
    vm.runInContext(source, context);
    return root.BookRankCover;
}

const NYT = 'https://static01.nyt.com/bestsellers/images/9780316608329.jpg';
const PROXIED = '/cover?src=' + encodeURIComponent(NYT);

test('toSrc rewrites overseas cover hosts onto the same-origin proxy', () => {
    const cover = loadCover();
    assert.equal(cover.toSrc(NYT), PROXIED);
    assert.equal(cover.toSrc('  ' + NYT + '  '), PROXIED);
});

test('toSrc leaves local cover paths unwrapped', () => {
    const cover = loadCover();
    assert.equal(cover.toSrc('/static/default-cover.png'), '/static/default-cover.png');
    assert.equal(cover.toSrc('/cache/images/abc.jpg'), '/cache/images/abc.jpg');
    assert.equal(cover.toSrc(PROXIED), PROXIED);
    assert.equal(cover.toSrc(''), '');
    assert.equal(cover.toSrc(null), '');
});

test('scheduleRetry no-ops when the image was already the default cover', () => {
    const cover = loadCover();
    const img = {
        src: '/static/default-cover.png',
        currentSrc: 'http://local.test/static/default-cover.png',
        dataset: {},
        getAttribute: () => '/static/default-cover.png',
    };
    const scheduled = cover.scheduleRetry(img, { setTimeout: (fn) => fn() });
    assert.equal(scheduled, false);
    assert.equal(img.src, '/static/default-cover.png');
});

test('scheduleRetry re-requests /cover after a placeholder 302', () => {
    const cover = loadCover();
    const timers = [];
    const img = {
        src: PROXIED,
        currentSrc: 'http://local.test/static/default-cover.png',
        dataset: {},
        getAttribute: (key) => (key === 'src' ? PROXIED : ''),
    };
    const scheduled = cover.scheduleRetry(img, {
        delays: [25],
        now: () => 1700000000000,
        setTimeout: (fn, ms) => {
            timers.push(ms);
            fn();
            return 1;
        },
    });
    assert.equal(scheduled, true);
    assert.deepEqual(timers, [25]);
    assert.match(img.src, /^\/cover\?src=/);
    assert.match(img.src, /_r=0/);
    assert.match(img.src, /_t=1700000000000/);
    assert.doesNotMatch(img.src, /src="https:/);
});

test('isPlaceholderSrc matches only the local default-cover path', () => {
    const cover = loadCover();
    assert.equal(cover.isPlaceholderSrc('http://local.test/static/default-cover.png'), true);
    assert.equal(cover.isPlaceholderSrc('/static/default-cover.png'), true);
    assert.equal(
        cover.isPlaceholderSrc('/cover?src=' + encodeURIComponent('https://cdn.example/default-cover.png')),
        false,
    );
    assert.equal(cover.isPlaceholderSrc('https://evil.example/static/default-cover.png'), false);
});

test('isProxySrc requires same-origin /cover', () => {
    const cover = loadCover();
    assert.equal(cover.isProxySrc(PROXIED), true);
    assert.equal(cover.isProxySrc('http://local.test/cover?src=x'), true);
    assert.equal(cover.isProxySrc('https://static01.nyt.com/cover?src=x'), false);
});

test('scheduleRetry does not overwrite a successful /cover whose src mentions default-cover.png', () => {
    const cover = loadCover();
    const src = '/cover?src=' + encodeURIComponent('https://cdn.example/default-cover.png');
    const img = {
        src,
        currentSrc: 'http://local.test' + src,
        dataset: {},
        getAttribute: (key) => (key === 'src' ? src : ''),
    };
    assert.equal(cover.scheduleRetry(img, { setTimeout: (fn) => fn() }), false);
    assert.equal(img.src, src);
});

test('new_books filter redraw fallback still proxies overseas covers', () => {
    const html = readFileSync(new URL('../templates/new_books.html', import.meta.url), 'utf8');
    assert.doesNotMatch(html, /function\s*\(\s*raw\s*\)\s*\{\s*return raw\s*\|\|\s*''/);
    assert.match(html, /\/cover\?src=' \+ encodeURIComponent\(value\)/);
});

test('scheduleRetry stops after the delay list is exhausted', () => {
    const cover = loadCover();
    const img = {
        src: PROXIED,
        currentSrc: 'http://local.test/static/default-cover.png',
        dataset: { coverRetryCount: '1' },
        getAttribute: (key) => (key === 'src' ? PROXIED : ''),
    };
    const scheduled = cover.scheduleRetry(img, {
        delays: [10],
        setTimeout: (fn) => fn(),
    });
    assert.equal(scheduled, false);
    assert.equal(img.src, PROXIED);
});

function retryFromDOM(candidate, boundary = 'data-original', now = () => 123) {
    const cover = loadCover();
    const timers = [];
    const writes = [];
    let attribute = '/static/default-cover.png';
    const img = {
        tagName: 'IMG',
        dataset: boundary === 'coverProxy' ? { coverProxy: candidate } : {},
        currentSrc: 'http://local.test/static/default-cover.png',
        get src() { return new URL(attribute, 'http://local.test').href; },
        set src(value) { attribute = value; writes.push(value); },
        getAttribute(key) {
            if (key === 'src') return attribute;
            return key === 'data-original' && boundary === 'data-original' ? candidate : '';
        },
    };
    const scheduled = cover.scheduleRetry(img, {
        now,
        setTimeout(callback, delay) { timers.push({ callback, delay }); },
    });
    return { img, timers, writes, scheduled };
}

test('actual data-original retry emits canonical relative owned routes without source userinfo or fragment', () => {
    for (const pathname of ['/cover', '/award-book/42/cover']) {
        const input = 'http://alice:password@local.test' + pathname + '?key=one&key=two&empty=#fragment';
        const f = retryFromDOM(input);
        assert.equal(f.scheduled, true); assert.equal(f.timers.length, 1); f.timers[0].callback();
        assert.ok(f.writes[0].startsWith(pathname + '?'), f.writes[0]);
        assert.equal(f.img.getAttribute('src'), f.writes[0], 'native-style src getter is absolute, raw attribute holds the canonical relative value');
        const assigned = new URL(f.img.src);
        assert.equal(assigned.origin, 'http://local.test'); assert.equal(assigned.pathname, pathname);
        assert.equal(assigned.username, ''); assert.equal(assigned.password, ''); assert.equal(assigned.hash, '');
        assert.deepEqual(assigned.searchParams.getAll('key'), ['one', 'two']);
        assert.equal(assigned.searchParams.get('empty'), ''); assert.equal(assigned.searchParams.get('_r'), '0');
        assert.equal(assigned.searchParams.get('_t'), '123');
    }
});

const unsafeProxyInputs = [
    'javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,<script>alert(1)</script>',
    'data:image/svg+xml,<svg onload=alert(1)>', 'vbscript:msgbox(1)', 'file:///cover',
    'blob:http://local.test/cover', 'https://local.test/cover', 'http://foreign.test/cover',
    '//foreign.test/cover', '///foreign.test/cover', '/\\foreign.test/cover',
    'http://local.test@foreign.test/cover', '/cover-other', '/cover/else',
    '/award-book/nope/cover', '/award-book/-1/cover', '/award-book/1/cover/extra', 'http://[bad/cover',
];

test('actual DOM boundaries reject unsafe schemes, external origins and invalid routes without timers or src assignment', () => {
    for (const boundary of ['data-original', 'coverProxy']) for (const input of unsafeProxyInputs) {
        const f = retryFromDOM(input, boundary);
        assert.equal(f.scheduled, false, boundary + ': ' + input);
        assert.equal(f.timers.length, 0); assert.deepEqual(f.writes, []);
    }
});

test('actual canonical retry preserves nested URL, Unicode, percent, quote, duplicate and empty query semantics', () => {
    const nested = 'https://books.test/image?a=1&name=书 空&percent=%2F&plus=+&quoted="<x>"';
    const query = 'src=' + encodeURIComponent(nested) + '&token=%25+%2B&repeat=one&repeat=two&empty=&%3Ckey%3E=%22%3Cimg%3E%27&_r=9&_r=8&_t=7';
    for (const boundary of ['data-original', 'coverProxy']) for (const prefix of ['/cover?', 'http://local.test/cover?', '//local.test/award-book/42/cover?']) {
        const input = prefix + query;
        const f = retryFromDOM(input, boundary); assert.equal(f.scheduled, true); f.timers[0].callback();
        const original = new URL(input, 'http://local.test'); const assigned = new URL(f.img.src);
        const pairs = url => [...url.searchParams].filter(([key]) => key !== '_r' && key !== '_t');
        assert.deepEqual(pairs(assigned), pairs(original), boundary + ': ' + prefix);
        assert.equal(assigned.searchParams.get('src'), nested); assert.equal(assigned.origin, 'http://local.test');
        assert.equal(assigned.pathname, original.pathname); assert.equal(assigned.searchParams.getAll('_r').length, 1);
        assert.equal(assigned.searchParams.getAll('_t').length, 1); assert.equal(assigned.searchParams.get('_r'), '0');
        assert.equal(assigned.searchParams.get('_t'), '123');
    }
});

test('private serializers independently fail closed; this strengthens their contract without claiming a public guard bypass', () => {
    const root = { location: { origin: 'http://local.test' } };
    const seam = source.replace('    root.BookRankCover = {', '    root.__testOnlySerializers = { cleanProxySrc, withRetryQuery };\n    root.BookRankCover = {');
    assert.notEqual(seam, source);
    vm.runInNewContext(seam, { window: root, URL, URLSearchParams });
    for (const input of ['', ...unsafeProxyInputs]) {
        assert.doesNotThrow(() => assert.equal(root.__testOnlySerializers.cleanProxySrc(input), '', input));
        assert.doesNotThrow(() => assert.equal(root.__testOnlySerializers.withRetryQuery(input, 0, () => 123), '', input));
    }
    assert.equal(Object.hasOwn(root.BookRankCover, 'cleanProxySrc'), false);
    assert.equal(Object.hasOwn(root.BookRankCover, 'withRetryQuery'), false);
});

test('failed safe serialization leaves the current image intact instead of assigning an empty src', () => {
    const f = retryFromDOM('/cover?src=image', 'data-original', () => { throw new Error('clock unavailable'); });
    assert.equal(f.scheduled, true);
    assert.doesNotThrow(() => f.timers[0].callback()); assert.deepEqual(f.writes, []);
    assert.equal(f.img.getAttribute('src'), '/static/default-cover.png'); assert.equal(f.img.dataset.coverRetrying, '');
});

const listCoverBook = {
    id: 42, title: 'Neutral list cover fixture', title_en: 'Neutral list cover fixture', title_zh: '',
    author: 'Author', award_name: 'Award', award_name_en: 'Award', award_wikidata_id: null,
    category: 'Fiction', year: 2026, isbn13: '9780306406157', isbn10: '', publisher: '',
    description: '', description_zh: '', cover_local_path: '', cover_original_url: '/award-book/42/cover',
};

function renderAwardList(name, locale) {
    const books = [listCoverBook, { ...listCoverBook, id: 43, cover_local_path: '/cache/images/' + 'a'.repeat(32) + '.jpg' }];
    const result = spawnSync(process.env.PYTHON || 'python', [fileURLToPath(new URL('fixtures/render_ux_round3.py', import.meta.url))], {
        input: JSON.stringify({
            root: fileURLToPath(new URL('../', import.meta.url)), name, locale, actual_display_labels: true,
            url: '/awards?lang=' + locale,
            context: {
                books, total_books: 2, total_pages: 1, page: 1, has_prev: false, has_next: false,
                data_load_failed: false, awards_unavailable: false, awards: [{ name: 'Award', name_en: 'Award' }],
                years: [2026], categories: ['Fiction'], selected_award: '', selected_year: '',
                selected_category: '', search_query: '', award_sections: [{ award: { name: 'Award', name_en: 'Award' }, books }],
            },
        }), encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
        env: { ...process.env, FLASK_ENV: 'testing' },
    });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
}

for (const name of ['awards.html', 'mobile/awards.html']) for (const locale of ['zh', 'en']) {
    test(`${name} ${locale} actual list markup opts into neutral feedback without hiding native lazy images`, () => {
        const rendered = renderAwardList(name, locale);
        const images = rendered.nodes.filter(node => node.tag === 'img' && (node.attrs.alt || '').includes(listCoverBook.title));
        assert.equal(images.length, name === 'awards.html' ? 4 : 2, 'desktop main list and award rail must both be covered');
        for (const img of images) {
            assert.equal(img.attrs['data-neutral-cover-feedback'], 'list');
            assert.equal(img.attrs.loading, 'lazy');
            assert.equal(Object.hasOwn(img.attrs, 'hidden'), false, 'display:none blocks native lazy loading and collapses the cover');
            assert.doesNotMatch(img.attrs.style || '', /visibility\s*:\s*hidden/i, 'no-JavaScript genuine covers must remain visible');
            assert.ok(Number(img.attrs.width) > 0 && Number(img.attrs.height) > 0, 'native cover dimensions remain defined');
            const parent = img.ancestors.at(-1);
            const siblings = rendered.nodes.filter(node => node.ancestors.at(-1) === parent);
            const neighbor = siblings[siblings.indexOf(img) + 1];
            assert.equal(neighbor?.tag, 'span', 'cover feedback must be the actual adjacent sibling, not elsewhere on the page');
            assert.match(neighbor.attrs.class || '', /(?:^|\s)(?:m-)?neutral-cover-placeholder(?:\s|$)/);
            assert.ok(neighbor.text.includes(locale === 'zh' ? '暂无封面' : 'No cover'), 'neutral feedback must contain readable localized text');
            assert.equal(Object.hasOwn(neighbor.attrs, 'hidden'), true, 'without JS the fallback overlay must not obscure a genuine cover');
            assert.notEqual(neighbor.attrs['aria-hidden'], 'true');
        }
    });
}

const flushCoverTasks = () => new Promise(resolve => setImmediate(resolve));
const safeListCache = '/cache/images/' + 'b'.repeat(32) + '.jpg';
const coverHeadResponse = (url, status = 200, headers = {}) => ({
    url, status, ok: status >= 200 && status < 300,
    headers: { get: name => Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] || null },
});

function boundListCover(responder, options = {}) {
    const calls = []; const timers = []; const listeners = new Map(); const writes = [];
    let attribute = options.src || '/award-book/42/cover';
    const placeholder = { hidden: true, classList: { contains: value => value === (options.placeholderClass || 'neutral-cover-placeholder') } };
    const img = {
        tagName: 'IMG', hidden: false, complete: false, naturalWidth: 0, naturalHeight: 0,
        dataset: { neutralCoverFeedback: 'list', ...options.dataset }, style: {}, nextElementSibling: placeholder,
        currentSrc: new URL(attribute, 'http://local.test').href,
        get src() { return new URL(attribute, 'http://local.test').href; },
        set src(value) { attribute = value; writes.push(value); },
        getAttribute(name) { return name === 'src' ? attribute : name === 'data-original' ? '/award-book/42/cover' : ''; },
    };
    for (const key of ['complete', 'currentSrc', 'naturalWidth', 'naturalHeight']) if (Object.hasOwn(options, key)) img[key] = options[key];
    const document = {
        addEventListener(type, callback, capture) { assert.equal(capture, true); listeners.set(type, callback); },
        querySelectorAll: () => [img],
    };
    const api = loadCover({
        AbortController,
        fetch(url, settings) { calls.push({ url, settings }); return responder(url, settings); },
        setTimeout(callback, delay) { const task = { callback, delay, cancelled: false }; timers.push(task); return task; },
        clearTimeout(task) { if (task) task.cancelled = true; },
    });
    api.bind(document);
    function fire(type) { listeners.get(type)({ target: img }); }
    function load(currentSrc = img.src, width = 280) {
        img.currentSrc = currentSrc; img.complete = true; img.naturalWidth = width; img.naturalHeight = width ? 420 : 0; fire('load');
    }
    function run(task) { assert.ok(task); task.cancelled = true; task.callback(); }
    return { api, img, placeholder, calls, timers, writes, fire, load, run };
}

function assertListNeutral(f) {
    assert.equal(f.img.hidden, false, 'list feedback must preserve native lazy layout, unlike detail hidden mode');
    assert.equal(f.img.style.visibility, 'hidden', 'do not show the bookstore-photo placeholder as a book cover');
    assert.equal(f.placeholder.hidden, false, 'readable neutral text stays visible');
}

test('actual list bind initializes an incomplete lazy proxy cover without hiding its layout or fetching HEAD', () => {
    const f = boundListCover(() => { throw new Error('an unloaded lazy image must not issue HEAD'); });
    assertListNeutral(f); assert.equal(f.calls.length, 0); assert.equal(f.img.complete, false);
});

test('actual list default-cover load stays neutral while scheduling the existing bounded retry', () => {
    const f = boundListCover(() => { throw new Error('direct placeholder uses retry, not HEAD'); });
    f.load('http://local.test/static/default-cover.png');
    assertListNeutral(f); assert.equal(f.calls.length, 0); assert.equal(f.img.dataset.coverRetryCount, '1');
    assert.equal(f.timers.filter(task => !task.cancelled).length, 1);
});

test('actual list proxy load confirmed by default-cover HEAD never exposes the redirected photo', async () => {
    const f = boundListCover(async () => coverHeadResponse('http://local.test/static/default-cover.png'));
    f.load(); await flushCoverTasks();
    assert.equal(f.calls.length, 1); assert.equal(f.calls[0].settings.method, 'HEAD');
    assert.equal(f.img.dataset.coverRetryCount, '1'); assertListNeutral(f);
});

test('actual list HEAD timeout aborts while retaining neutral feedback and lazy geometry', async () => {
    const f = boundListCover((_url, settings) => new Promise((_resolve, reject) => settings.signal.addEventListener('abort', () => reject(new Error('aborted')))));
    f.load(); const timer = f.timers.find(task => !task.cancelled && task.delay === 8000); f.run(timer); await flushCoverTasks();
    assert.equal(f.calls[0].settings.signal.aborted, true); assert.equal(f.img.dataset.coverProbing, '');
    assert.equal(f.img.dataset.coverRetryCount, undefined); assertListNeutral(f);
});

test('actual list exhausted fourth retry and final HEAD retain neutral feedback with no fifth image request', async () => {
    const f = boundListCover(async () => coverHeadResponse('http://local.test/static/default-cover.png'));
    for (const delay of f.api.RETRY_DELAYS_MS) {
        f.load(); await flushCoverTasks(); f.run(f.timers.find(task => !task.cancelled && task.delay === delay));
    }
    f.load(); await flushCoverTasks(); f.load(); await flushCoverTasks();
    assert.equal(f.calls.length, 5); assert.equal(f.writes.length, 4); assert.equal(f.img.dataset.coverRetryCount, '4');
    assert.equal(f.timers.filter(task => !task.cancelled).length, 0); assertListNeutral(f);
});

test('actual list safe cache HEAD remains neutral until genuine cache load, then reveals and handles later failure', async () => {
    const f = boundListCover(async () => coverHeadResponse('http://local.test/award-book/42/cover', 200, { 'X-Cover-Source': 'cache', 'X-Cover-Path': safeListCache }));
    f.load(); await flushCoverTasks();
    assert.equal(f.img.getAttribute('src'), safeListCache);
    const beforeRealLoad = { visibility: f.img.style.visibility, placeholderHidden: f.placeholder.hidden, imgHidden: f.img.hidden };
    f.load('http://local.test' + safeListCache, 120); await flushCoverTasks();
    assert.deepEqual(beforeRealLoad, { visibility: 'hidden', placeholderHidden: false, imgHidden: false }, 'HEAD is metadata, not successful image decoding');
    assert.equal(f.img.style.visibility, 'visible'); assert.equal(f.img.hidden, false); assert.equal(f.placeholder.hidden, true);
    assert.equal(f.calls.length, 1);
    f.img.naturalWidth = 0; f.fire('error'); assertListNeutral(f);
});

for (const complete of [false, true]) test(`actual list direct cache ${complete ? 'already decoded' : 'load event'} stays visible without HEAD`, async () => {
    const f = boundListCover(() => { throw new Error('direct cache must not issue HEAD'); }, { src: safeListCache, complete, naturalWidth: complete ? 120 : 0 });
    if (!complete) f.load('http://local.test' + safeListCache, 120);
    await flushCoverTasks();
    assert.equal(f.img.hidden, false); assert.notEqual(f.img.style.visibility, 'hidden');
    assert.equal(f.placeholder.hidden, true); assert.equal(f.calls.length, 0); assert.deepEqual(f.writes, []);
});

test('actual mobile list feedback recognizes its adjacent mobile neutral placeholder on decode failure', () => {
    const f = boundListCover(() => { throw new Error('failed direct cache must not issue HEAD'); }, { src: safeListCache, placeholderClass: 'm-neutral-cover-placeholder' });
    f.fire('error'); assertListNeutral(f);
});

test('ordinary unmarked cached covers keep their layout and visibility unchanged', () => {
    const f = boundListCover(() => { throw new Error('ordinary direct cache must not issue HEAD'); }, { src: safeListCache, dataset: { neutralCoverFeedback: undefined } });
    f.load(); assert.equal(f.img.hidden, false); assert.equal(f.img.style.visibility, undefined); assert.equal(f.calls.length, 0);
});

test('actual mobile awards renders the new neutral-feedback CSS version and retains the existing script version', () => {
    for (const locale of ['zh', 'en']) {
        const rendered = renderAwardList('mobile/awards.html', locale);
        const urls = rendered.nodes.flatMap(node => {
            const raw = node.tag === 'link' ? node.attrs.href : node.tag === 'script' ? node.attrs.src : '';
            return raw ? [new URL(raw, 'http://local.test')] : [];
        });
        const styles = urls.filter(url => url.pathname === '/static/mobile/css/mobile.css');
        const scripts = urls.filter(url => url.pathname === '/static/mobile/js/mobile.js');
        assert.equal(styles.length, 1); assert.equal(scripts.length, 1);
        assert.equal(styles[0].searchParams.get('v'), 'awards-neutral-20261009');
        assert.equal(scripts[0].searchParams.get('v'), 'audit-followup-20261009', 'unchanged mobile.js must not be promoted to an invented source version');
    }
});
