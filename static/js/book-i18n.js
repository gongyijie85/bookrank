/**
 * BookRank 图书内容语言包
 * 存储图书的中英双语内容，切换语言时即时替换，无需调翻译API
 */
var BookI18n = (function() {
    'use strict';

    var _store = new Map();

    var TITLE_SELECTORS = '.card-title, .list-item-title, .book-title, .detail-title, .recommendation-title, .change-title';
    var DESC_SELECTORS = '.card-desc, .list-item-desc, .book-description, .detail-description';
    var CAT_SELECTORS = '.card-category-tag, .book-category, .list-item-meta .card-tag:first-child';

    function _extractBookData(book) {
        var isbn = book.isbn13 || book.isbn10 || '';
        if (!isbn) return null;

        // 分类标签：优先用 window.CATEGORIES 共享映射表（与首页一致）
        // 当 book.category_id 存在时查表；缺失则回退到后端 list_name / category_name
        var categoryId = book.category_id || '';
        var enCat, zhCat;
        if (categoryId && typeof window !== 'undefined' && window.CATEGORIES && window.CATEGORIES.getLabel) {
            enCat = window.CATEGORIES.getLabel(categoryId, 'en');
            zhCat = window.CATEGORIES.getLabel(categoryId, 'zh');
        } else {
            enCat = book.list_name || book.category_name || 'Fiction';
            zhCat = book.category_name || enCat;
        }

        return {
            isbn: isbn,
            category_id: categoryId,
            en: {
                title: book.title || '',
                description: book.description || '',
                category: enCat,
                details: book.details || ''
            },
            zh: {
                title: book.title_zh || '',
                description: book.description_zh || '',
                category: zhCat,
                details: book.details_zh || ''
            },
            _raw: book
        };
    }

    function register(isbn, book) {
        if (!isbn) return;
        var existing = _store.get(isbn);
        var data = _extractBookData(book);
        if (!data) return;

        if (existing) {
            if (data.zh.title && !existing.zh.title) existing.zh.title = data.zh.title;
            if (data.zh.description && !existing.zh.description) existing.zh.description = data.zh.description;
            if (data.zh.category && !existing.zh.category) existing.zh.category = data.zh.category;
            if (data.zh.details && !existing.zh.details) existing.zh.details = data.zh.details;
        } else {
            _store.set(isbn, data);
        }
    }

    function registerAll(books) {
        if (!Array.isArray(books)) return;
        for (var i = 0; i < books.length; i++) {
            var isbn = books[i].isbn13 || books[i].isbn10;
            if (isbn) register(isbn, books[i]);
        }
    }

    function get(isbn, lang) {
        var entry = _store.get(isbn);
        if (!entry) return null;
        var localized = entry[lang] || {};
        var base = entry.en;
        return {
            title: localized.title || base.title,
            description: localized.description || base.description,
            category: localized.category || base.category,
            details: localized.details || base.details
        };
    }

    function getRaw(isbn) {
        var entry = _store.get(isbn);
        return entry ? entry._raw : null;
    }

    function updateTranslation(isbn, lang, data) {
        var entry = _store.get(isbn);
        if (!entry) return;
        if (!entry[lang]) entry[lang] = {};
        if (data.title) entry[lang].title = data.title;
        if (data.description) entry[lang].description = data.description;
        if (data.category) entry[lang].category = data.category;
        if (data.details) entry[lang].details = data.details;
    }

    /**
     * 批量更新翻译（兼容 items: [{isbn, language, data}]）
     * 解决 index.js 调用 BookI18n.updateBatch 不存在的报错
     */
    function updateBatch(items) {
        if (!Array.isArray(items)) return;
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            if (!item || !item.isbn) continue;
            updateTranslation(item.isbn, item.language || 'zh', item.data || {});
        }
    }

    function hasTranslation(isbn, lang) {
        var entry = _store.get(isbn);
        if (!entry) return false;
        if (lang === 'en') return true;
        return entry[lang] && entry[lang].title && entry[lang].title !== entry.en.title;
    }

    function getMissingTranslations(lang) {
        var missing = [];
        _store.forEach(function(entry, isbn) {
            if (!hasTranslation(isbn, lang)) {
                missing.push(isbn);
            }
        });
        return missing;
    }

    function _updateElement(el, text, truncate) {
        if (!el || text === undefined) return;
        if (truncate && text.length > truncate) {
            el.textContent = text.substring(0, truncate) + '...';
        } else {
            el.textContent = text;
        }
    }

    /**
     * 更新卡片标题：兼容两种结构
     * - 卡片本身就是标题元素（如获奖页面 h3.card-title 自身带 data-isbn）
     * - 卡片内部嵌套标题元素（如详情页/首页的 .book-card > .card-title）
     *
     * 修复前对获奖页面失效，因为 h3.querySelector(TITLE_SELECTORS) 返回 null
     */
    function _updateTitleInCard(card, text) {
        if (!card) return;
        if (card.matches && card.matches(TITLE_SELECTORS)) {
            _updateElement(card, text);
        } else {
            _updateElement(card.querySelector(TITLE_SELECTORS), text);
        }
    }

    function _findMetaValueByLabelKey(labelKey) {
        var labels = document.querySelectorAll('.detail-meta-grid .meta-label[data-i18n="' + labelKey + '"]');
        for (var i = 0; i < labels.length; i++) {
            var card = labels[i].closest ? labels[i].closest('.meta-card') : null;
            if (!card) continue;
            var value = card.querySelector('.meta-value');
            if (value) return value;
        }
        return null;
    }

    function applyLanguage(lang) {
        if (_store.size === 0) return;

        var hasDataIsbn = document.querySelectorAll('[data-isbn]').length > 0;

        if (hasDataIsbn || _store.size > 1) {
            _store.forEach(function(entry, isbn) {
                var data = get(isbn, lang);
                if (!data) return;

                var cards = document.querySelectorAll('[data-isbn="' + isbn + '"]');
                for (var c = 0; c < cards.length; c++) {
                    var card = cards[c];
                    _updateTitleInCard(card, data.title);
                    _updateElement(card.querySelector(DESC_SELECTORS), data.description, 80);
                    _updateElement(card.querySelector(CAT_SELECTORS), data.category);
                }
            });
        } else if (_store.size === 1) {
            var onlyEntry = null;
            _store.forEach(function(entry) { onlyEntry = entry; });
            var data = get(onlyEntry.isbn, lang);
            if (!data) return;

            var detailTitle = document.querySelector('.detail-title');
            if (detailTitle) _updateElement(detailTitle, data.title);

            var titleEnEl = document.querySelector('.detail-title-en');
            if (titleEnEl) {
                if (lang === 'zh' && data.title !== onlyEntry.en.title) {
                    titleEnEl.style.display = 'block';
                    titleEnEl.textContent = onlyEntry.en.title;
                } else {
                    titleEnEl.style.display = 'none';
                }
            }

            var descZhEl = document.querySelector('#panel-description .zh-description');
            var descEnEl = document.querySelector('#panel-description #desc-en, #panel-description .lang-toggle-content');
            if (descZhEl && descEnEl) {
                if (lang === 'zh') {
                    if (data.description && data.description !== onlyEntry.en.description) {
                        descZhEl.textContent = data.description;
                        descZhEl.style.display = 'block';
                        descEnEl.style.display = '';
                    } else {
                        descZhEl.style.display = 'none';
                        descEnEl.style.display = 'block';
                    }
                } else {
                    descZhEl.style.display = 'none';
                    descEnEl.style.display = 'block';
                }
            }

            var catValueEl = document.querySelector('.detail-meta-grid .meta-value[data-cat-zh][data-cat-en]') || _findMetaValueByLabelKey('book_category');
            if (catValueEl) {
                _updateElement(catValueEl, data.category);
            }

            var toggleBtns = document.querySelectorAll('.lang-toggle-btn');
            toggleBtns.forEach(function(btn) {
                var textEl = btn.querySelector('.toggle-text');
                if (textEl) {
                    textEl.textContent = lang === 'zh' ? '\u67e5\u770b\u82f1\u6587\u539f\u6587' : 'View Original';
                }
                btn.style.display = lang === 'zh' ? '' : 'none';
            });
        }

        window.dispatchEvent(new CustomEvent('booklanguagechange', {
            detail: { language: lang }
        }));
    }

    function clear() {
        _store.clear();
    }

    function size() {
        return _store.size;
    }

    return {
        register: register,
        registerAll: registerAll,
        get: get,
        getRaw: getRaw,
        updateTranslation: updateTranslation,
        updateBatch: updateBatch,
        hasTranslation: hasTranslation,
        getMissingTranslations: getMissingTranslations,
        applyLanguage: applyLanguage,
        clear: clear,
        size: size
    };
})();

window.BookI18n = BookI18n;
