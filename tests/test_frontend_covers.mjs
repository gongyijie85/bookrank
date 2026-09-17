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
