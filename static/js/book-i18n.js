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

    /**
     * 简易 ISBN 检测（10 或 13 位纯数字，可含连字符/空格）
     */
    function _looksLikeIsbn(text) {
        if (!text) return false;
        var cleaned = text.replace(/[-\s]/g, '');
        return /^\d+$/.test(cleaned) && (cleaned.length === 10 || cleaned.length === 13);
    }

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

        var enTitle = book.title || '';
        var zhTitle = book.title_zh || '';

        // 安全网：如果英文标题看起来是 ISBN，尝试用中文标题替代
        if (_looksLikeIsbn(enTitle)) {
            enTitle = zhTitle || enTitle;
        }
        // 同理处理中文标题
        if (_looksLikeIsbn(zhTitle)) {
            zhTitle = enTitle || zhTitle;
        }

        return {
            isbn: isbn,
            category_id: categoryId,
            en: {
                title: enTitle,
                description: book.description || '',
                category: enCat,
                details: book.details || ''
            },
            zh: {
                title: zhTitle,
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
        // 最终防线：如果取到的标题仍是 ISBN，回退到另一语言
        var title = localized.title || base.title;
        if (_looksLikeIsbn(title)) {
            title = (lang === 'zh' ? base.title : localized.title) || title;
        }
        return {
            title: title,
            description: localized.description || base.description,
            category: localized.category || base.category,
            details: localized.details || base.details
        };
    }

    function updateTranslation(isbn, lang, data) {
        var entry = _store.get(isbn);
        if (!entry) return;
        if (!entry[lang]) entry[lang] = {};
        // 防止 ISBN 脏数据被写入标题
        if (data.title && !_looksLikeIsbn(data.title)) entry[lang].title = data.title;
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

    function getMissingTranslations(lang) {
        var missing = [];
        _store.forEach(function(entry, isbn) {
            if (lang === 'en') return;
            var has = entry[lang] && entry[lang].title && entry[lang].title !== entry.en.title;
            if (!has) {
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
     *
     * 另一个更隐蔽的失效：新书速递卡片的标题是 `<div class="book-title"><a
     * href="/new-book/1">书名</a></div>`。直接给标题容器赋 textContent 会把
     * `<a>` 一起抹掉 —— 书名变成一段死文本，卡片不再可点，详情路由整条丢失。
     * 所以有内层链接时只改链接文本，href 与容器内的其它节点（卷号徽标等）原样保留。
     */
    function _updateTitleInCard(card, text) {
        if (!card) return;
        var titleEl = (card.matches && card.matches(TITLE_SELECTORS))
            ? card
            : card.querySelector(TITLE_SELECTORS);
        if (!titleEl) return;
        // 标题内的书名链接：`.browse-card-title-link` 是卷号并排时的显式钩子，
        // 其余卡片用「标题元素内带 href 的链接」兜底识别。
        var link = titleEl.querySelector('a.browse-card-title-link') || titleEl.querySelector('a[href]');
        if (link) {
            _updateElement(link, text);
            return;
        }
        _updateElement(titleEl, text);
    }

    /**
     * 按 i18n key 找详情页的字段值节点，兼容两套布局：
     * - 旧版：`.detail-meta-grid > .meta-card > .meta-label[data-i18n] + .meta-value`
     * - 新版：`.detail-meta > .detail-meta-row > dt.meta-label[data-i18n] + dd.meta-value`
     *
     * 详情页任务的改造把卡片式栅格换成 dt/dd 行；这里两种都认，旧页面行为不变。
     */
    function _findMetaValueByLabelKey(labelKey) {
        var selector = '[data-i18n="' + labelKey + '"]';
        var layouts = [
            { rows: '.detail-meta-grid .meta-label' + selector, container: '.meta-card', value: '.meta-value' },
            { rows: '.detail-meta .detail-meta-row .meta-label' + selector, container: '.detail-meta-row', value: '.meta-value' }
        ];
        for (var l = 0; l < layouts.length; l++) {
            var labels = document.querySelectorAll(layouts[l].rows);
            for (var i = 0; i < labels.length; i++) {
                var row = labels[i].closest ? labels[i].closest(layouts[l].container) : null;
                if (!row) continue;
                var value = row.querySelector(layouts[l].value);
                if (value) return value;
            }
        }
        return null;
    }

    /**
     * 详情页分类值节点：优先显式数据属性（新旧布局都带 data-cat-zh/en），
     * 否则按 i18n key 兜底。
     *
     * 必须限定在详情页的 meta-value 上：不带作用域的
     * `document.querySelector('[data-cat-zh][data-cat-en]')` 会抓到页面上**先出现的
     * 任意**同类元素 —— 新书速递页的分类筛选 `<option>` 也带这对属性且排在详情
     * 字段之前，于是详情页分类切换去改了筛选项，真正的分类值停在原文（英文页
     * 显示「商业」而不是 Business）。
     */
    function _findCategoryValue() {
        var attrEl = document.querySelector('.detail-meta-grid .meta-value[data-cat-zh][data-cat-en]') ||
            document.querySelector('.detail-meta .meta-value[data-cat-zh][data-cat-en]');
        return attrEl || _findMetaValueByLabelKey('book_category');
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
                    // 简介不传 truncate：整段写入，行数由 CSS 钳制决定。
                    // 这里曾传 80，与 index.js 的 100/80 一起把简介砍成开头一句。
                    _updateElement(card.querySelector(DESC_SELECTORS), data.description);
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
                // 英文原文面板的显隐归 CSS 规则 .lang-toggle-content(.visible) 独占，
                // toggleOriginal() 切的也是这个类；这里若写内联 display，会盖过类，
                // 导致按钮只能展开、永远收不回。
                var showOriginal = true;
                if (lang === 'zh') {
                    if (data.description && data.description !== onlyEntry.en.description) {
                        descZhEl.textContent = data.description;
                        descZhEl.style.display = 'block';
                        showOriginal = false;
                    } else {
                        descZhEl.style.display = 'none';
                    }
                } else {
                    descZhEl.style.display = 'none';
                }
                descEnEl.style.display = '';
                descEnEl.classList.toggle('visible', showOriginal);
            }

            var catValueEl = _findCategoryValue();
            if (catValueEl) {
                // 新版布局把中英分类都放在 data-cat-zh / data-cat-en 上；有属性时按其取值，
                // 与 BookI18n 持有的 store 数据无关（详情页可能没注册这本书）。
                var catAttr = catValueEl.getAttribute('data-cat-' + (lang === 'zh' ? 'zh' : 'en'));
                _updateElement(catValueEl, catAttr || data.category);
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

    /**
     * v0.9.63 新增：通用化"出版社名称"语言切换。
     *
     * 处理任意带 `data-pub-name-zh` / `data-pub-name-en` 属性的元素：
     * - 侧边栏链接（`.sidebar-link` / `.publisher-link`）
     * - 筛选下拉框 option（`<option>`）
     * - 图书卡片出版社（`.book-publisher` / `.meta-value`）
     * - 详情页 meta-value 出版社
     *
     * 调用方不需关心是哪种元素，零依赖 HTML 结构。
     *
     * 有图标（SVG）时只能改文本节点：整体赋 textContent 会把图标一起抹掉
     * （新书速递卡片的出版社行就是「图标 + 名称」）。侧边栏链接更复杂——
     * `<svg/> + <span class="pub-name"> + <span class="badge">计数</span>`，
     * 链接自身没有非空白文本节点，必须优先写 `.pub-name` 子元素；否则要么
     * 什么都不做，要么把图标与计数一起抹掉。
     */
    function applyPublisherLanguage(lang) {
        if (lang !== 'zh' && lang !== 'en') return;
        var els = document.querySelectorAll('[data-pub-name-zh]');
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            var nameZh = el.getAttribute('data-pub-name-zh') || '';
            var nameEn = el.getAttribute('data-pub-name-en') || nameZh;
            var text = (lang === 'en') ? nameEn : nameZh;
            // 1) 显式名称子元素优先（计数徽标 / 图标是兄弟节点，保持原样）
            var nameEl = el.querySelector ? el.querySelector('.pub-name') : null;
            if (nameEl) {
                nameEl.textContent = text;
                continue;
            }
            // 2) 有直接文本节点时只改它（保住 SVG）
            var textNode = _firstTextNode(el);
            if (textNode) {
                textNode.textContent = text;
            } else if (!el.querySelector('svg, img')) {
                // 3) 无图标无文本节点：整体赋值是安全的
                el.textContent = text;
            }
        }
    }

    function _firstTextNode(el) {
        for (var i = 0; i < el.childNodes.length; i++) {
            if (el.childNodes[i].nodeType === 3 && el.childNodes[i].textContent.trim()) {
                return el.childNodes[i];
            }
        }
        return null;
    }

    /**
     * 双语留痕徽标：`data-cat-zh`/`data-cat-en` 与 `data-date-zh`/`data-date-en`。
     *
     * 分类与日期状态的**判定**与语言无关（日期状态只由 publication_date 决定，
     * 绝不用 created_at 冒充），所以双语文案在 SSR 时一次写好，切语言只按属性换文本：
     * - 分类标签：整段文本替换；
     * - 日期标签：「<svg/>YYYY-MM-DD · 状态」只替换**最后**一段文本节点里的状态，
     *   图标与日期本身保留 —— 整体覆盖会把日历图标一起删掉。
     */
    function applyBilingualBadges(lang) {
        if (lang !== 'zh' && lang !== 'en') return;
        var suffix = (lang === 'en') ? 'en' : 'zh';
        var i;

        var cats = document.querySelectorAll('[data-cat-zh][data-cat-en]');
        for (i = 0; i < cats.length; i++) {
            var catEl = cats[i];
            var catText = catEl.getAttribute('data-cat-' + suffix);
            if (!catText) continue;
            var catNode = _firstTextNode(catEl);
            if (catNode) {
                // option 的文本形如「商业 (12)」：只换名称部分，计数原样保留。
                var suffixMatch = catNode.textContent.match(/\s*\([^()]*\)\s*$/);
                catNode.textContent = suffixMatch ? catText + ' ' + suffixMatch[0].trim() : catText;
            } else if (!catEl.querySelector('svg, img')) {
                catEl.textContent = catText;
            }
        }

        var dates = document.querySelectorAll('[data-date-zh][data-date-en]');
        for (i = 0; i < dates.length; i++) {
            var dateEl = dates[i];
            var label = dateEl.getAttribute('data-date-' + suffix);
            if (!label) continue;
            var nodes = [];
            for (var k = 0; k < dateEl.childNodes.length; k++) {
                if (dateEl.childNodes[k].nodeType === 3 && dateEl.childNodes[k].textContent.trim()) {
                    nodes.push(dateEl.childNodes[k]);
                }
            }
            if (!nodes.length) {
                if (!dateEl.querySelector('svg, img')) dateEl.textContent = label;
                continue;
            }
            var last = nodes[nodes.length - 1];
            // 「日期 · 状态」只换状态段；无分隔符（移动端无日期的纯状态）整段替换。
            last.textContent = /(·\s*)[^·]*$/.test(last.textContent)
                ? last.textContent.replace(/(·\s*)[^·]*$/, '$1' + label)
                : label;
        }

        // 「刚上市」徽标（数据属性一次性写好双语，切语言只换文本、闪光图标保留）。
        var fresh = document.querySelectorAll('[data-just-zh][data-just-en]');
        for (i = 0; i < fresh.length; i++) {
            var freshEl = fresh[i];
            var freshText = freshEl.getAttribute('data-just-' + suffix);
            if (!freshText) continue;
            var freshNode = _firstTextNode(freshEl);
            if (freshNode) freshNode.textContent = freshText;
            else if (!freshEl.querySelector('svg, img')) freshEl.textContent = freshText;
        }

        // 只带 tooltip 的日期角标（精选书列的 MM-DD）：文本是日期本身，**不换**，
        // 只把 title 里的状态文案跟着语言走，避免留一个过期语言的提示。
        var tips = document.querySelectorAll('[data-date-tip-zh][data-date-tip-en]');
        for (i = 0; i < tips.length; i++) {
            var tipEl = tips[i];
            var tip = tipEl.getAttribute('data-date-tip-' + suffix);
            if (tip) tipEl.setAttribute('title', tip);
        }
    }

    return {
        register: register,
        registerAll: registerAll,
        get: get,
        updateTranslation: updateTranslation,
        updateBatch: updateBatch,
        getMissingTranslations: getMissingTranslations,
        applyLanguage: applyLanguage,
        applyPublisherLanguage: applyPublisherLanguage,
        applyBilingualBadges: applyBilingualBadges,
        clear: clear,
        size: size
    };
})();

window.BookI18n = BookI18n;
