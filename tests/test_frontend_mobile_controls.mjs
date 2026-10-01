import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';
import { transformSync } from 'esbuild';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const rendered = spawnSync(process.env.PYTHON || 'python', [path.join(root, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root, name: 'mobile/base.html', url: '/?lang=en', locale: 'en' }),
    encoding: 'utf8', maxBuffer: 4 * 1024 * 1024,
});
assert.equal(rendered.error, undefined);
assert.equal(rendered.status, 0, rendered.stderr);
const html = JSON.parse(rendered.stdout).html;
const controlMarkup = html.match(/<button\b[^>]*\bid="m-theme-toggle"[^>]*>[\s\S]*?<\/button>/)?.[0];
assert.ok(controlMarkup, 'exercise the actual server-rendered theme button and SVG');

// Keep real SVG descendants: an aria-only button stub missed the original defect.
class Node {
    constructor(tag = 'div', attrs = {}) {
        this.tagName = tag;
        this.attrs = new Map(Object.entries(attrs));
        this.children = [];
        this.listeners = new Map();
        this.style = {};
        this.dataset = {};
    }
    getAttribute(name) { return this.attrs.get(name) ?? null; }
    setAttribute(name, value) { this.attrs.set(name, String(value)); }
    removeAttribute(name) { this.attrs.delete(name); }
    appendChild(node) { this.children.push(node); return node; }
    replaceChildren(...nodes) { this.children = nodes; }
    addEventListener(name, fn) {
        const callbacks = this.listeners.get(name) || [];
        callbacks.push(fn); this.listeners.set(name, callbacks);
    }
    fire(name, data = {}) {
        for (const fn of this.listeners.get(name) || []) fn({ target: this, preventDefault() {}, ...data });
    }
    querySelectorAll(selector) {
        const tags = selector.split(',').map(value => value.trim());
        const found = [];
        for (const child of this.children) {
            if (tags.includes(child.tagName)) found.push(child);
            found.push(...child.querySelectorAll(selector));
        }
        return found;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    set innerHTML(value) {
        assert.equal(String(value), '', 'construct icons with DOM APIs, not HTML writes');
        this.children = [];
    }
    get innerHTML() { return this.children.map(node => node.outerHTML).join(''); }
    get outerHTML() {
        const attrs = [...this.attrs].map(([key, value]) => ` ${key}="${value}"`).join('');
        return `<${this.tagName}${attrs}>${this.innerHTML}</${this.tagName}>`;
    }
}
function fragment(markup) {
    const parent = new Node('fragment');
    const stack = [parent];
    for (const match of markup.matchAll(/<\/?[a-z][^>]*>/gi)) {
        const token = match[0];
        if (token.startsWith('</')) { stack.pop(); continue; }
        const tag = token.match(/^<([\w-]+)/)[1];
        const attrs = Object.fromEntries([...token.matchAll(/([\w:-]+)="([^"]*)"/g)].map(item => [item[1], item[2]]));
        const node = new Node(tag, attrs);
        stack.at(-1).appendChild(node);
        if (!token.endsWith('/>')) stack.push(node);
    }
    return parent;
}
function scene(saved, systemDark, blockedStorage = false) {
    const button = fragment(controlMarkup).children[0];
    const document = new Node('document');
    document.documentElement = new Node('html', { 'data-lang': 'en' });
    document.body = new Node('body');
    document.cookie = '';
    document.readyState = 'loading';
    document.getElementById = id => id === 'm-theme-toggle' ? button : null;
    document.createElement = tag => new Node(tag);
    document.createElementNS = (namespace, tag) => {
        assert.equal(namespace, 'http://www.w3.org/2000/svg');
        return new Node(tag);
    };
    const values = new Map(saved ? [['theme', saved]] : []);
    const storage = {
        getItem(key) { if (blockedStorage) throw new Error('storage blocked'); return values.get(key) || null; },
        setItem(key, value) { if (blockedStorage) throw new Error('storage blocked'); values.set(key, value); },
    };
    const media = new Node(); media.matches = systemDark;
    media.addListener = fn => media.addEventListener('change', fn);
    const window = new Node();
    window.location = new URL('https://bookrank.test/?lang=en');
    window.matchMedia = () => media;
    window.localStorage = storage;
    window.dispatchEvent = event => window.fire(event.type, event);
    const context = vm.createContext({ document, window, localStorage: storage, URL, URLSearchParams,
        console, navigator: {}, CustomEvent: class { constructor(type) { this.type = type; } },
        fetch() { throw new Error('theme controls must not fetch'); }, setTimeout() {},
        setInterval() { throw new Error('theme controls must not poll'); },
    });
    vm.runInContext(read('static/mobile/js/mobile.js'), context);
    document.fire('DOMContentLoaded');
    return { document, button, values, media, window };
}
function assertGlyph(fixture, theme) {
    assert.equal(fixture.document.documentElement.getAttribute('data-theme'), theme);
    assert.equal(fixture.button.getAttribute('aria-pressed'), String(theme === 'dark'));
    const svgs = fixture.button.querySelectorAll('svg');
    assert.equal(svgs.length, 1, 'retain one visible icon, not an accumulation of old glyphs');
    const svg = svgs[0];
    assert.equal(svg.getAttribute('viewBox'), '0 0 24 24');
    assert.equal(svg.getAttribute('aria-hidden'), 'true');
    assert.equal(svg.getAttribute('stroke'), 'currentColor');
    if (theme === 'dark') {
        assert.ok(svg.querySelector('circle'), 'dark mode must show the sun action, not the retained moon');
        assert.ok(svg.querySelectorAll('line,path').length, 'sun needs visible rays');
    } else {
        assert.equal(svg.querySelector('circle'), null, 'light mode must show the existing moon action');
        assert.ok(svg.querySelector('path')?.getAttribute('d').includes('M21 12.79'));
    }
}

for (const theme of ['light', 'dark']) {
    test(`mobile rendered icon initializes from saved ${theme} over opposite system preference`, () => {
        assertGlyph(scene(theme, theme === 'light'), theme);
    });
}
test('mobile click chain changes the actual glyph and preserves the button and localized label', () => {
    const fixture = scene('light', true);
    const originalButton = fixture.button;
    for (const theme of ['dark', 'light', 'dark', 'light']) {
        fixture.button.fire('click');
        assertGlyph(fixture, theme);
        assert.equal(fixture.document.getElementById('m-theme-toggle'), originalButton);
        assert.equal(fixture.values.get('theme'), theme);
        assert.equal(fixture.button.getAttribute('aria-label'), 'Toggle theme');
    }
    fixture.window.location = new URL('https://bookrank.test/?lang=zh');
    fixture.window.fire('languagechange');
    assert.equal(fixture.button.getAttribute('aria-label'), '切换主题');
    assertGlyph(fixture, 'light');
});
test('mobile system preference changes update the visible glyph until the user chooses a theme', () => {
    const fixture = scene(null, false);
    assertGlyph(fixture, 'light');
    fixture.media.matches = true; fixture.media.fire('change');
    assertGlyph(fixture, 'dark');
    assert.equal(fixture.values.has('theme'), false);
    fixture.button.fire('click'); assertGlyph(fixture, 'light');
    fixture.media.fire('change'); assertGlyph(fixture, 'light');
});
test('blocked storage does not prevent mobile icon initialization or user switching', () => {
    const fixture = scene(null, true, true);
    assertGlyph(fixture, 'dark'); fixture.button.fire('click'); assertGlyph(fixture, 'light');
});
test('the actual mobile control selectors share the same flat frame and corner treatment', () => {
    assert.ok(html.includes('id="m-lang-globe"') && html.includes('class="m-lang-globe-btn"'));
    const css = transformSync(read('static/mobile/css/mobile.css'), { loader: 'css', minifyWhitespace: true }).code;
    const styles = selector => {
        const values = new Map();
        for (const rule of css.matchAll(/([^{}@]+)\{([^{}]*)\}/g)) {
            if (!rule[1].split(',').map(value => value.trim()).includes(selector)) continue;
            for (const declaration of rule[2].split(';')) {
                const colon = declaration.indexOf(':');
                if (colon >= 0) values.set(declaration.slice(0, colon).trim(), declaration.slice(colon + 1).trim());
            }
        }
        return values;
    };
    const theme = styles('.m-theme-toggle-btn'), language = styles('.m-lang-globe-btn');
    assert.ok(theme.get('border') && theme.get('border-radius'), 'read the actual theme frame declarations');
    assert.equal(language.get('border'), theme.get('border'), 'the language button must not be frameless next to a framed theme button');
    assert.equal(language.get('border-radius'), theme.get('border-radius'), 'paired controls must have the same corners');
    for (const values of [theme, language]) {
        assert.equal(values.get('width'), '44px'); assert.equal(values.get('height'), '44px');
    }
});

test('mobile controls load versioned assets so an existing one-hour cache cannot retain the old glyph', () => {
    for (const asset of ['mobile/css/mobile.css', 'mobile/js/mobile.js']) {
        const url = html.match(new RegExp(`(?:href|src)="([^"]*${asset.replaceAll('.', '\\.')}[^"]*)"`))?.[1];
        assert.ok(url, `render the actual ${asset} URL`);
        assert.ok(new URL(url.replaceAll('&amp;', '&'), 'https://bookrank.test').searchParams.get('v'),
            'this release must request a fresh asset URL');
    }
});
