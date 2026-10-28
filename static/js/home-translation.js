/* 首页桌面/移动共用：每页最多 15 个不同 ISBN，串行补译，失败后不自动重试。 */
(function () {
    'use strict';

    function text(value) {
        return typeof value === 'string' ? value.trim() : '';
    }

    function isbn(book) {
        return text(book.isbn13 || book.isbn10).replace(/[\s-]/g, '').toUpperCase();
    }

    function validChinese(value, placeholders) {
        return /[\u3400-\u9fff]/.test(text(value)) && (placeholders || []).indexOf(text(value)) === -1;
    }

    function missing(book, placeholders) {
        return ['title', 'description'].some(function (field) {
            var source = text(book[field]);
            return source && (placeholders || []).indexOf(source) === -1 &&
                !/[\u3400-\u9fff]/.test(source) && !validChinese(book[field + '_zh'], placeholders);
        });
    }

    function create(options) {
        var attempted = new Set();
        var translated = new Map();
        var running = false;
        var scheduled = false;
        var halted = false;

        function valid(value) { return validChinese(value, options.placeholders); }
        function needsTranslation(book) { return missing(book, options.placeholders); }

        function merge(books) {
            (books || []).forEach(function (book) {
                var saved = translated.get(isbn(book));
                if (!saved) return;
                // 同一 ISBN 的源简介可能已经变化，旧请求的译文不能覆盖新版本。
                ['title', 'description'].forEach(function (field) {
                    if (!valid(book[field + '_zh']) && text(book[field]) === saved.source[field] && saved[field]) {
                        book[field + '_zh'] = saved[field];
                    }
                });
            });
            return books;
        }

        function paint() {
            var books = merge(options.getBooks());
            var zh = options.getLanguage() === 'zh';
            options.getCards().forEach(function (card, index) {
                // 搜索结果中同 ISBN 可有来自不同分类的独立快照；只合并请求，不能合并卡片内容。
                var position = card.getAttribute('data-book-position');
                var book = books[position === null ? index : Number(position)];
                var cardIsbn = text(card.getAttribute('data-isbn')).replace(/[\s-]/g, '').toUpperCase();
                if (!book || isbn(book) !== cardIsbn) return;
                if (needsTranslation(book)) card.setAttribute('data-needs-translation', '1');
                else card.removeAttribute('data-needs-translation');
                var title = zh && valid(book.title_zh) ? book.title_zh : book.title;
                var description = zh && valid(book.description_zh) ? book.description_zh : book.description;
                var titleEl = card.querySelector(options.titleSelector);
                if (titleEl && title) {
                    var titleLink = titleEl.querySelector('a[href]');
                    (titleLink || titleEl).textContent = title;
                    titleEl.setAttribute('title', title);
                }
                var descEl = card.querySelector(options.descriptionSelector);
                if (!descEl && description && (options.placeholders || []).indexOf(text(description)) === -1) {
                    var content = card.querySelector(options.descriptionContainerSelector);
                    if (content) {
                        descEl = document.createElement('p');
                        descEl.className = options.descriptionClass;
                        content.appendChild(descEl);
                    }
                }
                if (descEl && description) {
                    var limit = options.descriptionLimit;
                    descEl.textContent = limit && description.length > limit
                        ? description.slice(0, limit) + '…' : description;
                }
            });
        }

        function nextBook() {
            if (halted || attempted.size >= 15 || options.getLanguage() !== 'zh') return null;
            var visible = new Set(options.getCards().map(function (card) {
                return text(card.getAttribute('data-isbn')).replace(/[\s-]/g, '').toUpperCase();
            }));
            return merge(options.getBooks()).find(function (book) {
                var key = isbn(book);
                return /^(?:\d{13}|\d{9}[\dX])$/.test(key) && visible.has(key) && !attempted.has(key) && needsTranslation(book);
            });
        }

        function matchingValue(value, book, source, field) {
            if (!value || valid(book[field + '_zh']) || !valid(value[field + '_zh'])) return '';
            // API 可能读取了比浏览器分类缓存更新的版本；不能把 B 的译文记成 A 的。
            if (Object.prototype.hasOwnProperty.call(value, field) && text(value[field]) !== source[field]) return '';
            return text(value[field + '_zh']);
        }

        async function run() {
            if (running) return;
            running = true;
            try {
                var book;
                // 每次请求前重新取可见分类，已被替换的卡片不会继续消耗翻译请求。
                while ((book = nextBook())) {
                    var key = isbn(book);
                    var source = { title: text(book.title), description: text(book.description) };
                    attempted.add(key);
                    var resp = await options.request('/api/translate/book/' + encodeURIComponent(key), {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
                    });
                    if (resp.status === 404) continue;
                    if (!resp.ok) { halted = true; break; }
                    var result = await resp.json();
                    var value = result && result.success && result.data && result.data.book;
                    var saved = {
                        source: source,
                        title: matchingValue(value, book, source, 'title'),
                        description: matchingValue(value, book, source, 'description'),
                    };
                    // HTTP 200/空对象都不等于完成；部分成功只填补空字段。
                    if (!saved.title && !saved.description) {
                        // 另一入口可能已补齐该书，保留有效译文并继续其它 ISBN。
                        if (value && (valid(value.title_zh) || valid(value.description_zh))) continue;
                        halted = true;
                        break;
                    }
                    translated.set(key, saved);
                    merge(options.getBooks());
                    if (options.onTranslation) options.onTranslation(merge);
                    paint();
                }
            } catch (e) {
                // 网络失败或结果未知：本页停止，禁止自动重放可能已被服务端处理的 POST。
                halted = true;
            } finally {
                running = false;
                if (options.onIdle) options.onIdle();
            }
        }

        function refresh() {
            paint();
            if (running || scheduled || !nextBook()) return;
            scheduled = true;
            setTimeout(function () { scheduled = false; run(); }, 1500);
        }

        return { refresh: refresh, merge: merge };
    }

    window.BookRankHomeTranslation = { create: create, missing: missing };
})();
