// 提交进仓库的 static/dist 就是**生产实际运行**的 JS。
//
// Render 的 buildCommand 只有 `pip install -r requirements-prod.txt`（见 render.yaml），
// 不会跑 `npm run build`；CI 里那个 `node scripts/build_frontend.mjs` 只产出构建结果、
// 不回写仓库。所以「改了 static/js 却忘了重建 dist」在生产上的表现是**改了没用**，
// 而所有源码级测试照旧全绿 —— 这一类缝（SSR vs 客户端重渲染、源码 vs 构建产物）
// 在本项目已经栽过两次：首页卡片的明文 ISBN 就是先被 SSR 恢复、又被客户端模板抹掉。
//
// 因此这里不测源码，直接加载 manifest 指向的**已构建产物**来断言。
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const manifestUrl = new URL('../static/dist/manifest.json', import.meta.url);
const manifest = JSON.parse(readFileSync(manifestUrl, 'utf8'));

/** 解析 manifest 条目对应的 dist 文件路径（manifest 与产物同目录）。 */
function bundleUrl(key) {
    const name = manifest[key];
    assert.ok(name, `manifest.json 缺少 ${key} 条目`);
    return new URL(name, manifestUrl);
}

/** 用构建产物里的 index.js 渲染一张卡片，返回容器的 innerHTML。 */
function renderCardWithBuiltBundle(book) {
    const container = { innerHTML: '', addEventListener() {} };
    const context = vm.createContext({
        console,
        localStorage: { getItem: () => 'en' },
        window: {
            APP_CONFIG: {
                defaultCover: '/static/default-cover.png',
                currentCategory: 'hardcover-fiction',
            },
            addEventListener() {},
            location: { href: '', pathname: '/', reload() {} },
        },
        document: {
            getElementById: id => (id === 'books-grid' ? container : null),
            querySelector: () => null,
            addEventListener() {},
        },
        esc: value => String(value ?? ''),
        URLSearchParams,
        t: (key, lang, values = {}) => `${key} ${values.n ?? ''}`,
    });
    vm.runInContext(readFileSync(bundleUrl('index.js'), 'utf8'), context);
    context.updateBooksOnPage([book], 'hardcover-fiction', null);
    return container.innerHTML;
}

test('every manifest entry exists in static/dist', () => {
    for (const key of Object.keys(manifest)) {
        assert.ok(
            existsSync(bundleUrl(key)),
            `manifest 指向的 ${manifest[key]} 不在 static/dist 里（dist 与源码不同步？）`
        );
    }
});

test('the committed index.js bundle renders the plaintext ISBN on a card', () => {
    // 线上实测的载荷：publisher=Atria、isbn13=9781668200223（Penn Cole / BURN OF THE EVERFLAME）。
    const html = renderCardWithBuiltBundle({
        rank: 1,
        title: 'BURN OF THE EVERFLAME',
        author: 'Penn Cole',
        publisher: 'Atria',
        isbn13: '9781668200223',
        isbn10: '',
        weeks_on_list: 1,
    });
    assert.match(
        html,
        /class="card-pub-isbn-item isbn"/,
        '提交的 dist 产出的卡片没有明文 ISBN：static/js/index.js 改完要跑 `npm run build` 并把 static/dist 一起提交'
    );
    assert.match(html, /9781668200223/);
});
