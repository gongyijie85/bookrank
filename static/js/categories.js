/**
 * BookRank 图书分类中英映射共享模块
 *
 * 数据源必须与 app/config.py 的 CATEGORIES 字典保持一致。
 * 加载顺序：必须早于 translations.js / book-i18n.js / index.js。
 * 通过 window.CATEGORIES 暴露给所有脚本（普通脚本和 ES Module 都可访问）。
 */
(function (global) {
    'use strict';

    // 8 个 NYT 分类的中英双语映射
    // 键名 = NYT API 分类 ID；值 = { zh, en }
    var LABELS = {
        'hardcover-fiction':                { zh: '精装小说',           en: 'Hardcover Fiction' },
        'trade-fiction-paperback':          { zh: '平装小说',           en: 'Trade Fiction Paperback' },
        'hardcover-nonfiction':             { zh: '精装非虚构',         en: 'Hardcover Nonfiction' },
        'paperback-nonfiction-monthly':     { zh: '平装非虚构',         en: 'Paperback Nonfiction' },
        'advice-how-to-and-miscellaneous':  { zh: '建议、方法与杂项',   en: 'Advice, How-To & Miscellaneous' },
        'graphic-books-and-manga':          { zh: '漫画与绘本',         en: 'Graphic Books & Manga' },
        'childrens-middle-grade-hardcover': { zh: '儿童中级精装本',     en: "Children's Middle Grade Hardcover" },
        'young-adult-hardcover':            { zh: '青少年精装本',       en: 'Young Adult Hardcover' }
    };

    // 按显示顺序排列的分类 ID 列表（下拉框用）
    var ORDERED_IDS = [
        'hardcover-fiction',
        'trade-fiction-paperback',
        'hardcover-nonfiction',
        'paperback-nonfiction-monthly',
        'advice-how-to-and-miscellaneous',
        'graphic-books-and-manga',
        'childrens-middle-grade-hardcover',
        'young-adult-hardcover'
    ];

    /**
     * 获取分类在指定语言下的标签
     * @param {string} categoryId - NYT 分类 ID
     * @param {string} lang - 'zh' | 'en'，默认 'zh'
     * @returns {string} 本地化标签；找不到则原样返回 categoryId
     */
    function getLabel(categoryId, lang) {
        var entry = LABELS[categoryId];
        if (!entry) return categoryId;
        var key = (lang === 'en') ? 'en' : 'zh';
        return entry[key] || entry.zh || categoryId;
    }

    /**
     * 生成分类下拉框的 <option> 列表 HTML
     * @param {string} currentId - 当前选中的分类 ID
     * @param {string} lang - 'zh' | 'en'
     * @returns {string} <option>...</option> 拼接的 HTML
     */
    function renderOptions(currentId, lang) {
        var html = '';
        for (var i = 0; i < ORDERED_IDS.length; i++) {
            var id = ORDERED_IDS[i];
            var label = getLabel(id, lang);
            var selected = (id === currentId) ? ' selected' : '';
            html += '<option value="' + escapeAttr(id) + '"' + selected + '>' +
                    escapeHtml(label) + '</option>';
        }
        return html;
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
    function escapeAttr(s) {
        return String(s).replace(/"/g, '&quot;');
    }

    // 暴露到全局：普通脚本和 ES Module 都能访问
    global.CATEGORIES = {
        LABELS: LABELS,
        ORDERED_IDS: ORDERED_IDS,
        getLabel: getLabel,
        renderOptions: renderOptions
    };

    // 兼容旧名称（translations.js 之前用过的全局名）
    global.CATEGORY_LABELS = LABELS;
    global.getCategoryLabel = getLabel;
})(window);
