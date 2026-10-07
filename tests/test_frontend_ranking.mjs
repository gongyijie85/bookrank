import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/js/index.js', import.meta.url), 'utf8');

function renderer(view, overrides = {}) {
    const container = { innerHTML: '', addEventListener() {} };
    // 切语言时 rerenderCurrentBooks() 优先读内存 booksData，为空才回落到 SSR 内嵌的
    // `#initial-books-data`。夹具不给这个节点，语言重渲染路径就永远走不到（静默 return），
    // 于是"重渲染后卡片是否还完整"这类断言全部变成空转。
    const initialBooksNode = overrides.initialBooks
        ? { textContent: JSON.stringify(overrides.initialBooks) }
        : null;
    const appConfig = Object.assign(
        { defaultCover: '/static/default-cover.png', currentCategory: 'hardcover-fiction' },
        overrides.appConfig || {}
    );
    const context = vm.createContext({
        console,
        localStorage: { getItem: () => 'en' },
        window: {
            APP_CONFIG: appConfig,
            addEventListener(type, fn) { this['_on' + type] = fn; },
            location: { href: '', pathname: '/', search: '', reload() { this._reloaded = true; } },
        },
        document: {
            getElementById: id => (id === view ? container : (id === 'initial-books-data' ? initialBooksNode : null)),
            querySelector: () => null,
            addEventListener() {},
        },
        esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;'),
        URLSearchParams,
        t: (key, lang, values = {}) => `${key} ${values.n ?? ''}`,
    });
    vm.runInContext(source, context);
    return { context, container };
}

// 只覆盖真实存在的容器：#209 用「网格密度」切换取代了列表视图，模板里已无
// id="books-list"，而 index.js 的渲染目标只有 books-grid。此前这里按两个视图参数化，
// books-list 那条永远拿到空 innerHTML 而失败（test:frontend 未进 CI，所以一直没被发现）。
for (const view of ['books-grid']) {
    test(`${view}: search and language rerender preserve original rank and destination`, () => {
        const { context, container } = renderer(view);
        const books = [{
            rank: 8, source_index: 7, source_category: 'hardcover-nonfiction',
            title: 'A filtered book', author: 'An author', previous_rank: 10, weeks_on_list: 12,
        }];
        context.updateBooksOnPage(books, 'hardcover-fiction', null);
        assert.match(container.innerHTML, /data-index="7"/);
        assert.match(container.innerHTML, /data-category="hardcover-nonfiction"/);
        assert.match(container.innerHTML, /card_rank_aria 8/);
        assert.match(container.innerHTML, />↑ Up 2<\/span>/);
        assert.match(container.innerHTML, /<h3[^>]*>A filtered book<\/h3>/);
        context.updateBooksOnPage([{ ...books[0], source_index: undefined }], 'hardcover-fiction', null);
        assert.match(container.innerHTML, /data-index="7"/);
    });
}

test('returning books and unknown history are not marked as new', () => {
    const { context } = renderer('books-grid');
    assert.match(context.renderRankChange({ rank_last_week: '0', weeks_on_list: 84 }, 4, 'en', 'rank-change'), /RETURN/);
    assert.match(context.renderRankChange({ rank_last_week: '0', weeks_on_list: 1 }, 4, 'en', 'rank-change'), />\+ NEW<\/span>/);
    assert.equal(context.renderRankChange({ rank_last_week: 'Unknown', weeks_on_list: 12 }, 4, 'en', 'rank-change'), '');
    assert.match(context.renderRankChange({ previous_rank: 4 }, 4, 'en', 'rank-change'), />— Unchanged<\/span>/);
});

test('cover weeks badge is shown only for a positive history count', () => {
    const { context } = renderer('books-grid');
    assert.match(context.renderCoverWeeks({ weeks_on_list: 12 }, 'zh'), /cover-weeks/);
    assert.match(context.renderCoverWeeks({ weeks_on_list: 12 }, 'zh'), />12<\/strong><span>card_weeks_suffix<\/span>/);
    assert.doesNotMatch(context.renderCoverWeeks({ weeks_on_list: 12 }, 'zh'), /cover-weeks-label|累计上榜周数/);
    assert.equal(context.renderCoverWeeks({ weeks_on_list: 0 }, 'zh'), '');
    assert.equal(context.renderCoverWeeks({ weeks_on_list: 'Unknown' }, 'en'), '');
});

test('category rerender proxies NYT covers even when BookRankCover is missing', () => {
    // 分类切换走 /api/category-books 再由本函数重绘卡片。BookRankCover 若尚未挂上
    // （脚本顺序、移动端、测试夹具），身份回退会把 static01.nyt.com 原样写入 img src，
    // 国内用户这一屏封面就会变成占位图。回退必须自己走 /cover 代理。
    const { context, container } = renderer('books-grid');
    assert.equal(context.window.BookRankCover, undefined);
    const nyt = 'https://static01.nyt.com/bestsellers/images/9780316608329.jpg';
    context.updateBooksOnPage([{
        rank: 1,
        title: 'Covered',
        author: 'A',
        cover: nyt,
        _original_cover: nyt,
    }], 'hardcover-fiction', null);
    assert.match(container.innerHTML, /src="\/cover\?src=https%3A%2F%2Fstatic01\.nyt\.com/);
    assert.doesNotMatch(container.innerHTML, /src="https:\/\/static01\.nyt\.com/);
    assert.match(container.innerHTML, /data-original="\/cover\?src=/);
});

test('category rerender leaves already-local cover paths unwrapped', () => {
    const { context, container } = renderer('books-grid');
    context.updateBooksOnPage([{
        rank: 1,
        title: 'Cached',
        author: 'A',
        cover: '/cache/images/abc.jpg',
        _original_cover: 'https://static01.nyt.com/x.jpg',
    }], 'hardcover-fiction', null);
    assert.match(container.innerHTML, /src="\/cache\/images\/abc\.jpg"/);
    assert.doesNotMatch(container.innerHTML, /src="\/cover\?src=.*cache\/images/);
});

test('card navigation uses source category and leaves native links alone', () => {
    const { context } = renderer('books-grid');
    context.window.location.search = '?lang=en&view=compact&search=rain&page=3';
    const card = { getAttribute: key => key === 'data-index' ? '7' : 'hardcover-nonfiction' };
    context.handleCardClick({ target: { closest: selector => selector.startsWith('.card[') ? card : null } });
    const target = new URL(context.window.location.href, 'https://bookrank.test');
    assert.equal(target.pathname, '/book/7');
    assert.equal(target.searchParams.get('category'), 'hardcover-nonfiction');
    assert.equal(target.searchParams.get('return_to'), '/?lang=en&view=compact&search=rain&page=3');
    context.window.location.href = '';
    context.handleCardClick({ target: { closest: selector => selector === 'a[href]' ? {} : null } });
    assert.equal(context.window.location.href, '');
});

test('category change from an active search state navigates to category-only URL', () => {
    // 搜索是跨全部分类的临时视图：旧输入框与空状态条不会随 AJAX 重绘清除，
    // 所以从搜索/错误状态换分类必须整页跳转到仅分类的 URL（丢弃 search 参数）。
    const { context } = renderer('books-grid', { appConfig: { searchQuery: '不存在', searchUnavailableCount: 0 } });
    context.changeCategory('business-books');
    assert.equal(context.window.location.href, '/?category=business-books');
});

test('popstate restores URL state by reloading instead of pushing again', () => {
    // 前进/后退不再走 changeCategory（其内部 pushState 会新增历史条目），
    // 而是整页重载当前 URL 还原状态。
    const { context } = renderer('books-grid');
    const popstate = context.window._onpopstate;
    assert.equal(typeof popstate, 'function');
    popstate();
    assert.equal(context.window.location._reloaded, true);
});

// ---------------------------------------------------------------------------
// 明文 ISBN：产品契约，别再删（#248 删过一次，用户问"卡片上 ISBN 怎么没了"才暴露）
//
// 卡片有两条渲染路径，两条都必须显示明文 ISBN：
//   1) SSR —— templates/index.html 的 .card-pub-isbn-item.isbn（已有回归锁，
//      见 tests/test_card_desc_and_details_render.py::TestCardShowsPlainIsbn）
//   2) 客户端重渲染 —— 本文件的 updateBooksOnPage()。切语言（languagechange →
//      rerenderCurrentBooks）与切换分类（/api/category-books）都走这条，
//      SSR 里好好的 ISBN 会被它整块重写成"只有出版社"。
//
// data-isbn 属性和可见 ISBN **不能互相替代**：前者供 BookI18n 注册，
// 用户在卡片上看不到它。
// ---------------------------------------------------------------------------

/** 该单测里所有卡片断言都基于同一个书对象，字段与 /api/category-books 的真实载荷一致。 */
function isbnBook(overrides = {}) {
    return {
        rank: 1,
        title: 'BURN OF THE EVERFLAME',
        author: 'Penn Cole',
        publisher: 'Atria',
        isbn13: '9781668200223',
        isbn10: '',
        weeks_on_list: 1,
        ...overrides,
    };
}

test('language rerender keeps the plain ISBN visible on home cards', () => {
    // 用户报的症状：首页卡片只有 "Penn Cole / Atria"，看不到 ISBN。
    // SSR 与 #initial-books-data 都带 isbn13（线上实测），丢它的是这条客户端模板。
    const books = [isbnBook()];
    const { context, container } = renderer('books-grid', { initialBooks: books });
    context.rerenderCurrentBooks('zh');
    assert.match(container.innerHTML, /class="card-pub-isbn-item isbn"/);
    assert.match(container.innerHTML, /9781668200223/);
    assert.match(container.innerHTML, /ISBN-13: 9781668200223/);
});

test('category switch rerender keeps the plain ISBN visible too', () => {
    // 同一条模板也服务于分类切换（AJAX 结果直接重绘），修一处必须两处都覆盖。
    const { context, container } = renderer('books-grid');
    context.updateBooksOnPage([isbnBook()], 'hardcover-fiction', null);
    assert.match(container.innerHTML, /class="card-pub-isbn-item isbn"/);
    assert.match(container.innerHTML, /9781668200223/);
});

test('isbn10 is used when isbn13 is missing', () => {
    // 与 templates/index.html 的 {% if book.isbn13 %}…{% elif book.isbn10 %} 一致。
    const { context, container } = renderer('books-grid');
    context.updateBooksOnPage([isbnBook({ isbn13: '', isbn10: '0316608327' })], 'hardcover-fiction', null);
    assert.match(container.innerHTML, /class="card-pub-isbn-item isbn"/);
    assert.match(container.innerHTML, /0316608327/);
    assert.match(container.innerHTML, /ISBN-10: 0316608327/);
});

test('a card with only an ISBN still shows the meta line', () => {
    // 元信息行的入场条件也必须把 ISBN 算进去：出版社缺失但 ISBN 存在的书，
    // 此前整块 <p class="card-pub-isbn"> 都不会输出，ISBN 自然也没了。
    const { context, container } = renderer('books-grid');
    context.updateBooksOnPage(
        [isbnBook({ publisher: '', weeks_on_list: 0 })],
        'hardcover-fiction',
        null
    );
    assert.match(container.innerHTML, /<p class="card-pub-isbn">/);
    assert.match(container.innerHTML, /class="card-pub-isbn-item isbn"/);
    assert.match(container.innerHTML, /9781668200223/);
});

test('an unknown publisher does not suppress the ISBN', () => {
    // 占位出版社被过滤掉时，ISBN 仍然要出现（两者是同一条行里的独立判断）。
    const { context, container } = renderer('books-grid');
    context.updateBooksOnPage(
        [isbnBook({ publisher: 'Unknown Publisher' })],
        'hardcover-fiction',
        null
    );
    assert.doesNotMatch(container.innerHTML, /card-pub-isbn-item publisher/);
    assert.match(container.innerHTML, /class="card-pub-isbn-item isbn"/);
});

test('cards without any identifier keep the meta line unchanged', () => {
    // 反向用例：既无 ISBN 也无出版社、无周数时，不该凭空造出一个空的行。
    const { context, container } = renderer('books-grid');
    context.updateBooksOnPage(
        [isbnBook({ publisher: '', isbn13: '', isbn10: '', weeks_on_list: 0 })],
        'hardcover-fiction',
        null
    );
    assert.doesNotMatch(container.innerHTML, /class="card-pub-isbn"/);
});

function suggestionPage({ lang = 'en', query = 'John', history = [], initialBooks = [], windowBooks, deniedStorage = false, urlLang = lang, htmlLang = lang } = {}) {
    const suggestions = { innerHTML: '', style: {}, addEventListener() {} };
    const search = { value: query };
    const documentElement = { lang: htmlLang === 'zh' ? 'zh-CN' : htmlLang, getAttribute(name) { return name === 'lang' ? this.lang : null; } };
    const context = vm.createContext({
        console, URLSearchParams,
        localStorage: { getItem(key) {
            if (deniedStorage) throw Object.assign(new Error('Storage denied'), { name: 'SecurityError' });
            return key === 'bookrank_search_history' ? JSON.stringify(history) : lang;
        } },
        window: { APP_CONFIG: { currentCategory: 'hardcover-fiction', defaultCover: '/static/default-cover.png' }, booksData: windowBooks, addEventListener() {}, location: { pathname: '/', search: urlLang ? '?lang=' + urlLang : '', href: 'https://bookrank.example/' } },
        document: { documentElement, getElementById: id => id === 'search-suggestions' ? suggestions : id === 'search-input' ? search : id === 'initial-books-data' ? { textContent: JSON.stringify(initialBooks) } : null, querySelector: () => null, addEventListener() {} },
        esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    });
    vm.runInContext(readFileSync(new URL('../static/js/translations.js', import.meta.url), 'utf8'), context);
    vm.runInContext(source, context);
    return { context, suggestions, search };
}

test('search suggestions translate real book and history headings in English and Chinese', () => {
    const books = [{ title: 'John at Home', title_zh: '约翰的家', author: 'A Writer' }];
    for (const lang of ['en', 'zh']) {
        const { context, suggestions, search } = suggestionPage({ lang, windowBooks: books, history: [{ query: 'A saved search' }] });
        vm.runInContext('renderSearchSuggestions()', context);
        const headings = [...suggestions.innerHTML.matchAll(/class="suggestions-header">([^<]+)</g)].map(match => match[1]);
        assert.equal(headings.length, 2);
        if (lang === 'en') {
            assert.match(headings[0], /book.*results/i);
            assert.equal(headings[1], 'Search History');
            assert.doesNotMatch(suggestions.innerHTML, /图书结果|搜索历史/);
        } else {
            assert.deepEqual(headings, ['图书结果', '搜索历史']);
        }
        search.value = '';
        vm.runInContext('renderSearchSuggestions()', context);
        assert.match(suggestions.innerHTML, lang === 'en' ? /Search History/ : /搜索历史/);
    }
});

test('SSR books provide search suggestions before any category AJAX request, limited to five', () => {
    const { context, suggestions } = suggestionPage({ initialBooks: Array.from({ length: 7 }, (_, i) => ({ title: 'John ' + i, author: 'Writer' })) });
    vm.runInContext('renderSearchSuggestions()', context);
    assert.equal(suggestions.style.display, 'block');
    assert.equal([...suggestions.innerHTML.matchAll(/class="suggestion-item"/g)].length, 5);
    assert.match(suggestions.innerHTML, /John 0/);
    assert.doesNotMatch(suggestions.innerHTML, /John 5|John 6/);
});

test('homepage source initializes and renders with denied storage using valid URL or HTML language', () => {
    for (const [urlLang, htmlLang, expected] of [['en', 'zh', 'en'], ['', 'zh', 'zh'], ['invalid', 'en', 'en']]) {
        const { context, suggestions } = suggestionPage({ deniedStorage: true, urlLang, htmlLang, initialBooks: [{ title: 'John', author: 'Writer' }] });
        assert.equal(vm.runInContext('currentLanguage', context), expected);
        vm.runInContext('renderSearchSuggestions()', context);
        assert.match(suggestions.innerHTML, /John/);
    }
});

for (const mode of ['search', 'cache', 'fetch']) {
    test(`category navigation keeps valid language and view in the ${mode} path`, async () => {
        const { context } = renderer('books-grid', { appConfig: { searchQuery: mode === 'search' ? 'rain' : '' } });
        context.window.location.search = '?lang=en&view=compact&search=rain&page=3';
        let destination = '';
        context.window.history = { pushState(_state, _title, url) { destination = url; } };
        context.fetch = async () => ({ ok: true, json: async () => ({ success: true, data: { books: [], update_time: null, update_frequency: 'weekly', list_published_date: null } }) });
        if (mode === 'cache') {
            vm.runInContext("categoryCache.set('business-books', [{ title: 'Cached book', author: 'Writer' }], null, 'weekly', null)", context);
        }
        await context.changeCategory('business-books');
        const url = new URL(context.window.location.href || destination, 'https://bookrank.example');
        assert.equal(url.searchParams.get('category'), 'business-books', mode);
        assert.equal(url.searchParams.get('lang'), 'en', mode);
        assert.equal(url.searchParams.get('view'), 'compact', mode);
        assert.equal(url.searchParams.has('search'), false, mode + ': category switch retains existing search reset behavior');
        assert.equal(url.searchParams.has('page'), false, mode + ': page starts over with the new category');
    });
}

function browserHistory(context, search) {
    const pushes = [];
    context.window.location.search = search;
    context.window.location.href = 'https://bookrank.example/' + search;
    context.window.history = {
        pushState(_state, _title, target) {
            const url = new URL(target, context.window.location.href);
            context.window.location.href = url.href;
            context.window.location.pathname = url.pathname;
            context.window.location.search = url.search;
            pushes.push(url.pathname + url.search);
        },
    };
    return pushes;
}

function renderedDetailUrl(container) {
    const link = container.innerHTML.match(/<a class="card-link" href="([^"]+)"/);
    assert.ok(link, 'the actual dynamic card must contain its native detail link');
    return new URL(link[1].replaceAll('&amp;', '&'), 'https://bookrank.example');
}

for (const mode of ['cache', 'fetch']) {
    for (const search of ['?lang=en&view=compact', '?category=hardcover-fiction&lang=en&view=compact&search=rain&page=3']) {
        test(`dynamic ${mode} cards return to the selected category from ${search}`, async () => {
            const { context, container } = renderer('books-grid');
            const pushes = browserHistory(context, search);
            const books = [isbnBook({ title: 'ATOMIC HABITS' })];
            context.fetch = async () => ({ ok: true, json: async () => ({ success: true, data: { books } }) });
            if (mode === 'cache') {
                context.cachedBooks = books;
                vm.runInContext("categoryCache.set('business-books', cachedBooks, null, 'weekly', null)", context);
            }

            await context.changeCategory('business-books');

            const detail = renderedDetailUrl(container);
            const back = new URL(detail.searchParams.get('return_to'), 'https://bookrank.example');
            assert.equal(back.searchParams.get('category'), 'business-books');
            assert.equal(back.searchParams.get('lang'), 'en');
            assert.equal(back.searchParams.get('view'), 'compact');
            assert.equal(back.searchParams.has('search'), false, 'category switches keep the existing search reset');
            assert.equal(back.searchParams.has('page'), false, 'category switches keep the existing page reset');
            assert.equal(detail.searchParams.get('lang'), 'en');
            assert.equal(detail.searchParams.get('category'), 'business-books');
            assert.equal(detail.searchParams.get('return_to'), context.window.location.pathname + context.window.location.search);
            assert.deepEqual(pushes, ['/?category=business-books&lang=en&view=compact']);
        });
    }
}

test('dynamic search cards retain the full current return context without replacing the source category', () => {
    const { context, container } = renderer('books-grid');
    const search = '?category=hardcover-fiction&lang=en&view=compact&search=rain&page=3';
    const pushes = browserHistory(context, search);
    context.updateBooksOnPage([isbnBook({ source_index: 7, source_category: 'hardcover-nonfiction' })], 'hardcover-fiction', null);
    const detail = renderedDetailUrl(container);
    assert.equal(detail.pathname, '/book/7');
    assert.equal(detail.searchParams.get('category'), 'hardcover-nonfiction');
    assert.equal(detail.searchParams.get('return_to'), '/' + search);
    assert.deepEqual(pushes, []);
});

test('failed category requests leave the current URL and history unchanged', async () => {
    const { context } = renderer('books-grid');
    const pushes = browserHistory(context, '?category=hardcover-fiction&lang=en&view=compact');
    const before = context.window.location.href;
    const originalGet = context.document.getElementById;
    context.document.getElementById = id => id === 'category-select' ? { value: 'hardcover-fiction' } : originalGet(id);
    context.document.querySelectorAll = () => [];
    context.console = { ...console, error() {} };
    context.showToast = () => {};
    context.fetch = async () => ({ ok: false });
    await context.changeCategory('business-books');
    assert.equal(context.window.location.href, before);
    assert.deepEqual(pushes, []);
});

test('popstate reloads the restored category context without adding a history entry', () => {
    const { context } = renderer('books-grid');
    const pushes = browserHistory(context, '?category=business-books&lang=en&view=compact');
    context.window._onpopstate();
    assert.equal(context.window.location._reloaded, true);
    assert.deepEqual(pushes, []);
});
