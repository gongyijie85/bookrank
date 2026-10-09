import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const css = fs.readFileSync(path.join(repo, 'static/css/new-books.css'), 'utf8');
const fields = '.charts-page.new-books-page div.new-books-advanced-fields';

// Inspect only the actual owner declarations at a CSS viewport width.
// This source contract cannot establish browser details-box geometry.
function atWidth(selector, width) {
    const result = new Map();
    const text = css.replace(/\/\*[\s\S]*?\*\//g, '');
    function walk(source, active = true) {
        let start = 0;
        while (start < source.length) {
            const open = source.indexOf('{', start);
            if (open < 0) break;
            const header = source.slice(start, open).trim();
            let end = open + 1; let depth = 1;
            while (end < source.length && depth) {
                if (source[end] === '{') depth++;
                if (source[end] === '}') depth--;
                end++;
            }
            assert.equal(depth, 0, 'balanced source CSS');
            const body = source.slice(open + 1, end - 1);
            if (header.startsWith('@media')) {
                const min = header.match(/min-width:\s*([\d.]+)px/);
                const max = header.match(/max-width:\s*([\d.]+)px/);
                walk(body, active && (!min || width >= Number(min[1])) && (!max || width <= Number(max[1])));
            } else if (active && header.split(',').map(value => value.trim()).includes(selector)) {
                for (const declaration of body.split(';')) {
                    const colon = declaration.indexOf(':');
                    if (colon >= 0) result.set(declaration.slice(0, colon).trim(), declaration.slice(colon + 1).trim());
                }
            }
            start = end;
        }
    }
    walk(text);
    return result;
}

test('desktop native-details fields explicitly establish a horizontal wrapping layout above 768px', () => {
    for (const width of [769, 1024, 1280]) {
        const actual = atWidth(fields, width);
        assert.equal(actual.get('display'), 'flex', `${width}px fields must own their row instead of relying on details display:contents`);
        assert.equal(actual.get('flex-direction') || 'row', 'row');
        assert.equal(actual.get('flex-wrap'), 'wrap', 'intermediate desktop widths may wrap without overflow');
        assert.equal(actual.get('align-items'), 'flex-end');
        assert.ok(['16px', '1rem'].includes(actual.get('gap')), 'same 16px gap as the existing desktop filter bar');
    }
});

test('320px, 390px and the 768px boundary retain the existing narrow grid and filter sizes', () => {
    for (const width of [320, 390, 768]) {
        const actual = atWidth(fields, width);
        assert.equal(actual.get('display'), 'flex');
        assert.equal(actual.get('flex-wrap'), 'wrap');
        assert.equal(actual.get('gap'), '8px');
        const form = atWidth('.charts-page.new-books-page #filter-form', width);
        assert.equal(form.get('display'), 'grid');
        assert.equal(form.get('grid-template-columns'), 'minmax(0, 1fr) minmax(0, 1fr)');
        const select = atWidth(fields + ' .filter-group select', width);
        assert.equal(select.get('min-width'), '0');
        assert.equal(select.get('min-height'), '44px');
    }
});
