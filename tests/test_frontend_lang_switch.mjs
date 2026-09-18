// 语言切换的**客户端**翻译覆盖测试：直接执行真实的 static/js/translations.js。
//
// 为什么需要它：语言偏好存在 localStorage，浏览器内切换语言时由 applyPageTranslation()
// **就地改写**带钩子的元素（不重新请求）。所以"切换后有没有翻译"完全由这个函数的选择器
// 覆盖面决定，静态检查模板只能验证"钩子写了"，验证不了"客户端真的会用它"。
//
// 历史 bug（用户报"切换语言后有一部分导航没有翻译"）：
//   - 模板里 data-zh / data-en 双语文案存在 60+ 处，但**没有任何 JS 消费它** →
//     面包屑三项、侧边栏导航段等 48 处在切换后冻结在 SSR 语言；
//   - 侧边栏"导航"整段更是连 data-i18n 都没写。
// 本文件锁住修复后的两条支路（data-i18n 与 data-zh/data-en），并覆盖带图标子元素的替换路径。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/js/translations.js', import.meta.url), 'utf8');

const TEXT_NODE = 3;

class FakeTextNode {
    constructor(text) {
        this.nodeType = TEXT_NODE;
        this.textContent = text;
    }
}

class FakeElement {
    constructor(tagName, attrs = {}, childNodes = []) {
        this.tagName = tagName.toUpperCase();
        this._attrs = new Map(Object.entries(attrs));
        this.childNodes = childNodes;
    }

    get attributes() {
        return [...this._attrs].map(([name, value]) => ({ name, value }));
    }

    getAttribute(name) {
        return this._attrs.has(name) ? this._attrs.get(name) : null;
    }

    setAttribute(name, value) {
        this._attrs.set(name, String(value));
    }

    get textContent() {
        return this.childNodes.map((n) => n.textContent).join('');
    }

    set textContent(value) {
        this.childNodes = [new FakeTextNode(String(value))];
    }

    /** 只用得到 'svg, img, i'（setVisibleText 判断"有没有图标子元素"）。 */
    querySelector(selector) {
        const tags = selector.split(',').map((s) => s.trim().toUpperCase());
        return this.childNodes.some((n) => n.tagName && tags.includes(n.tagName)) ? this.childNodes[0] : null;
    }
}

/** 把 'tag?[attr][attr]' 解析成可匹配条件。 */
function parseSelector(selector) {
    const match = selector.match(/^([a-zA-Z]*)((\[[a-zA-Z0-9-]+\])*)$/);
    if (!match) throw new Error(`本测试的极简选择器不支持: ${selector}`);
    return {
        tag: match[1] ? match[1].toUpperCase() : null,
        attrs: [...match[2].matchAll(/\[([a-zA-Z0-9-]+)\]/g)].map((m) => m[1]),
    };
}

function buildPage(elements) {
    const all = [];
    const collect = (el) => {
        all.push(el);
        el.childNodes.forEach((n) => n.tagName && collect(n));
    };
    elements.forEach(collect);

    const document = {
        querySelectorAll(selector) {
            const { tag, attrs } = parseSelector(selector);
            return all.filter(
                (el) =>
                    (!tag || el.tagName === tag) &&
                    attrs.every((a) => el.getAttribute(a) !== null)
            );
        },
        // applyPageTranslation 末尾会单独找 `title[data-i18n]`
        querySelector(selector) {
            return this.querySelectorAll(selector)[0] || null;
        },
    };

    const window = {};
    const context = vm.createContext({ window, document, Node: { TEXT_NODE }, console });
    vm.runInContext(source, context);
    return context;
}

test('applyPageTranslation 仍处理 data-i18n（重构后行为不变）', () => {
    const label = new FakeElement('span', { 'data-i18n': 'nav_home' }, [new FakeTextNode('首页')]);
    const withIcon = new FakeElement('span', { 'data-i18n': 'nav_new_books' }, [
        new FakeElement('svg'),
        new FakeTextNode('新书速递'),
    ]);
    const ctx = buildPage([label, withIcon]);

    ctx.applyPageTranslation('en');
    assert.equal(label.textContent, 'Home');
    assert.equal(withIcon.textContent, 'New Books', '带图标时只应替换文本节点');

    ctx.applyPageTranslation('zh');
    assert.equal(label.textContent, '首页');
    assert.equal(withIcon.textContent, '新书速递');
});

test('applyPageTranslation 消费 data-zh / data-en（面包屑与数据型文案）', () => {
    // 真实形态：面包屑条目同时携带两侧文案，可见文本是 SSR 那一侧。
    const category = new FakeElement('a', {
        'data-zh': '精装小说',
        'data-en': 'Hardcover Fiction',
    }, [new FakeTextNode('精装小说')]);
    const title = new FakeElement('span', {
        'data-zh': '永恒之火的燃烧',
        'data-en': 'BURN OF THE EVERFLAME',
    }, [new FakeTextNode('永恒之火的燃烧')]);
    const ctx = buildPage([category, title]);

    ctx.applyPageTranslation('en');
    assert.equal(category.textContent, 'Hardcover Fiction');
    assert.equal(title.textContent, 'BURN OF THE EVERFLAME');

    // 往返：连续切换必须回到中文，不能在第二次切回时留下英文
    ctx.applyPageTranslation('zh');
    assert.equal(category.textContent, '精装小说');
    assert.equal(title.textContent, '永恒之火的燃烧');

    ctx.applyPageTranslation('en');
    assert.equal(category.textContent, 'Hardcover Fiction');
});

test('data-zh/data-en 与 data-i18n 同时存在时以 data-zh/data-en 为准', () => {
    // 断言必须**能判别**：字典键给的是另一串文本，只有走双语支路才会得到 Hardcover Fiction。
    // （早先写成 data-i18n='nav_home' 且双语也是'首页/Home'，两种实现都能通过 —— 等于没测。）
    const both = new FakeElement('span', {
        'data-i18n': 'nav_home',
        'data-zh': '精装小说',
        'data-en': 'Hardcover Fiction',
    }, [new FakeTextNode('精装小说')]);
    const ctx = buildPage([both]);

    ctx.applyPageTranslation('en');
    assert.equal(both.textContent, 'Hardcover Fiction', '双语支路必须压过字典支路');

    ctx.applyPageTranslation('zh');
    assert.equal(both.textContent, '精装小说');
});

test('空的双语属性不得把可见文本抹掉', () => {
    // 后端可能给出空值（缺 *_en 列）；清空会把导航变成空白，比不翻译更糟。
    const emptyEn = new FakeElement('a', { 'data-zh': '精装小说', 'data-en': '' }, [
        new FakeTextNode('精装小说'),
    ]);
    const ctx = buildPage([emptyEn]);

    ctx.applyPageTranslation('en');
    assert.equal(emptyEn.textContent, '精装小说', '值为空时应保持原文本');
});

test('容器型 data-zh/data-en 不得抹掉子元素（卡片书名链接）', () => {
    // 真实形态（_macros.html / awards.html / new_books.html 共 4 处）：
    //   <div class="book-title" data-zh="…" data-en="…"><a href="/book/1">书名</a></div>
    // 文本在子元素里。若替换时直接 el.textContent = text，会把 <a> 一起抹掉 ——
    // 卡片上的书名链接消失，比不翻译严重得多。
    const link = new FakeElement('a', { href: '/book/1' }, [new FakeTextNode('永恒之火的燃烧')]);
    const container = new FakeElement('div', {
        'data-zh': '永恒之火的燃烧',
        'data-en': 'BURN OF THE EVERFLAME',
    }, [link]);
    const ctx = buildPage([container]);

    ctx.applyPageTranslation('en');

    assert.equal(container.childNodes.length, 1, '子元素必须原样保留');
    assert.equal(container.childNodes[0].tagName, 'A');
    assert.equal(container.childNodes[0].getAttribute('href'), '/book/1');
    assert.equal(link.textContent, '永恒之火的燃烧', '容器内的文案由页面级重渲染负责，这里不越权');
});

test('data-zh/data-en 的元素带图标时保留图标', () => {
    const withIcon = new FakeElement('a', { 'data-zh': '获奖书单', 'data-en': 'Awards' }, [
        new FakeElement('svg'),
        new FakeTextNode('获奖书单'),
    ]);
    const ctx = buildPage([withIcon]);

    ctx.applyPageTranslation('en');
    assert.equal(withIcon.textContent, 'Awards');
    assert.equal(withIcon.childNodes.length, 2, '图标子元素必须保留');
    assert.equal(withIcon.childNodes[0].tagName, 'SVG');
});
