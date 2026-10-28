import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const root = fileURLToPath(new URL('../', import.meta.url));

for (const name of ['index.html', 'mobile/index.html']) {
    test(`${name}: real SSR falls back to usable English when the Chinese description is a placeholder`, () => {
        const result = spawnSync(process.env.PYTHON || 'python', ['tests/fixtures/render_ux_round3.py'], {
            cwd: root, encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
            input: JSON.stringify({ root, name, locale: 'zh', url: '/?lang=zh', context: {
                books: [{ isbn13: '9780000000001', title: 'Fixture title', title_zh: '夹具书名',
                    description: 'A usable English description', description_zh: '暂无简介',
                    author: 'Fixture Author', rank: 1, source_index: 0, cover: '/static/default-cover.png' }],
                categories: { 'hardcover-nonfiction': '非虚构' }, current_category: 'hardcover-nonfiction',
                category_names_en: {}, monthly_categories: [], search_query: '', search_unavailable_count: 0,
                data_load_failed: false, is_cached: false,
            } }),
        });
        assert.equal(result.error, undefined);
        assert.equal(result.status, 0, result.stderr);
        const rendered = JSON.parse(result.stdout);
        const className = name.startsWith('mobile/') ? 'm-book-card-desc' : 'card-desc';
        const description = rendered.nodes.find(node => (node.attrs.class || '').split(/\s+/).includes(className));
        assert.ok(description, 'the real template must render a description element for later translation updates');
        assert.equal(description.text.trim(), 'A usable English description');
    });
}
