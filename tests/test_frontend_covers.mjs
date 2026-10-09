import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

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
