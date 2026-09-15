import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/js/index.js', import.meta.url), 'utf8');

function renderer(view) {
    const container = { innerHTML: '', addEventListener() {} };
    const context = vm.createContext({
        console,
        localStorage: { getItem: () => 'en' },
        window: {
            APP_CONFIG: { defaultCover: '/static/default-cover.png', currentCategory: 'hardcover-fiction' },
            addEventListener() {},
            location: { href: '' },
        },
        document: {
            getElementById: id => id === view ? container : null,
            querySelector: () => null,
            addEventListener() {},
        },
        esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;'),
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
        assert.match(container.innerHTML, />\+2<\/span>/);
        assert.match(container.innerHTML, /<h3[^>]*>A filtered book<\/h3>/);
        context.updateBooksOnPage([{ ...books[0], source_index: undefined }], 'hardcover-fiction', null);
        assert.match(container.innerHTML, /data-index="7"/);
    });
}

test('returning books and unknown history are not marked as new', () => {
    const { context } = renderer('books-grid');
    assert.match(context.renderRankChange({ rank_last_week: '0', weeks_on_list: 84 }, 4, 'en', 'rank-change'), /RETURN/);
    assert.match(context.renderRankChange({ rank_last_week: '0', weeks_on_list: 1 }, 4, 'en', 'rank-change'), /card_new_badge/);
    assert.equal(context.renderRankChange({ rank_last_week: 'Unknown', weeks_on_list: 12 }, 4, 'en', 'rank-change'), '');
    assert.equal(context.renderRankChange({ previous_rank: 4 }, 4, 'en', 'rank-change'), '');
});

test('cover weeks badge is shown only for a positive history count', () => {
    const { context } = renderer('books-grid');
    assert.match(context.renderCoverWeeks({ weeks_on_list: 12 }, 'zh'), /cover-weeks/);
    assert.match(context.renderCoverWeeks({ weeks_on_list: 12 }, 'zh'), />12<\/strong><span>card_weeks_suffix<\/span>/);
    assert.doesNotMatch(context.renderCoverWeeks({ weeks_on_list: 12 }, 'zh'), /cover-weeks-label|累计上榜周数/);
    assert.equal(context.renderCoverWeeks({ weeks_on_list: 0 }, 'zh'), '');
    assert.equal(context.renderCoverWeeks({ weeks_on_list: 'Unknown' }, 'en'), '');
});

test('card navigation uses source category and leaves native links alone', () => {
    const { context } = renderer('books-grid');
    const card = { getAttribute: key => key === 'data-index' ? '7' : 'hardcover-nonfiction' };
    context.handleCardClick({ target: { closest: selector => selector.startsWith('.card[') ? card : null } });
    assert.equal(context.window.location.href, '/book/7?category=hardcover-nonfiction');
    context.window.location.href = '';
    context.handleCardClick({ target: { closest: selector => selector === 'a[href]' ? {} : null } });
    assert.equal(context.window.location.href, '');
});
