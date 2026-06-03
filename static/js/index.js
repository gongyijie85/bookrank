import { api } from './api.js';

/* ============================================
   BookRank 首页交互逻辑 (Notion 设计系统)
   ============================================ */

// 模块级状态：当前加载的图书数据 + 分类
// 用于切换语言时本地重渲染（无需重新请求 API）
let booksData = [];
let currentCategory = '';

// 启动时从服务端嵌入的 JSON 节点读取初始数据（首页 SSR 渲染时已生成）
(function initModuleState() {
    var node = document.getElementById('initial-books-data');
    if (node) {
        try {
            booksData = JSON.parse(node.textContent || '[]');
        } catch (e) {
            console.warn('initModuleState: 解析 initial-books-data 失败', e);
        }
    }
    if (window.APP_CONFIG && window.APP_CONFIG.currentCategory) {
        currentCategory = window.APP_CONFIG.currentCategory;
    }
})();

// 语言控制变量
let currentLanguage = localStorage.getItem('bookrank_language') || 'en';

function updateLanguageButtons(lang) {
    const zhBtn = document.getElementById('lang-zh');
    const enBtn = document.getElementById('lang-en');
    if (zhBtn) {
        zhBtn.classList.toggle('active', lang === 'zh');
        zhBtn.setAttribute('aria-pressed', lang === 'zh');
    }
    if (enBtn) {
        enBtn.classList.toggle('active', lang === 'en');
        enBtn.setAttribute('aria-pressed', lang === 'en');
    }
}

/**
 * 内部语言切换处理函数（仅处理翻译文本切换）
 */
function _handleLanguageChange(lang) {
    if (lang === 'zh') {
        const translationData = [];
        const books = window.booksData || [];
        books.forEach(book => {
            const isbn = book.isbn13 || book.isbn10;
            if (!isbn) return;
            const trans = {
                title: book.title_zh || book.title,
                description: book.description_zh || book.description,
                category: book.category_name || ''
            };
            translationData.push({
                isbn: isbn,
                language: 'zh',
                data: trans
            });
            const titleEl = document.querySelector(`.card[data-isbn="${isbn}"] .card-title`);
            if (titleEl && book.title_zh) {
                titleEl.textContent = book.title_zh;
                if (!titleEl.querySelector('.translation-badge')) {
                    titleEl.insertAdjacentHTML('beforeend', '<span class="translation-badge">译</span>');
                }
            }
        });
        if (typeof BookI18n !== 'undefined') {
            BookI18n.updateBatch(translationData);
            BookI18n.applyLanguage('zh');
        } else {
            translateAllBooks();
        }
    } else {
        restoreAllBooks();
        if (typeof BookI18n !== 'undefined') {
            BookI18n.applyLanguage('en');
        }
    }
}

/**
 * 翻译系统入口函数（带节流控制）
 */
let translateTimer = null;
function startTranslationSystem() {
    if (translateTimer) {
        clearTimeout(translateTimer);
    }
    translateTimer = setTimeout(() => {
        if (currentLanguage === 'zh') {
            _handleLanguageChange('zh');
        }
    }, 1000);
}

// 切换语言
function switchLanguage(lang) {
    currentLanguage = lang;
    localStorage.setItem('bookrank_language', lang);
    updateLanguageButtons(lang);
    _handleLanguageChange(lang);
    document.dispatchEvent(new CustomEvent('languagechange', { detail: { language: lang } }));
}

// ========== 搜索功能 ==========

function saveSearchHistory(query) {
    if (!query || !query.trim()) return;
    try {
        let history = JSON.parse(localStorage.getItem('bookrank_search_history') || '[]');
        history = history.filter(item => item.query !== query.trim());
        history.unshift({
            query: query.trim(),
            timestamp: Date.now()
        });
        history = history.slice(0, 20);
        localStorage.setItem('bookrank_search_history', JSON.stringify(history));
    } catch (e) {
        console.error('保存搜索历史失败:', e);
    }
}

function renderSearchSuggestions() {
    const suggestionsEl = document.getElementById('search-suggestions');
    const searchInput = document.getElementById('search-input');
    if (!suggestionsEl || !searchInput) return;

    const query = searchInput.value.trim();
    let history = [];
    try {
        history = JSON.parse(localStorage.getItem('bookrank_search_history') || '[]');
    } catch (e) {}

    if (query) {
        const books = window.booksData || [];
        const results = books.filter(book => {
            const searchStr = `${book.title} ${book.title_zh || ''} ${book.author} ${book.description || ''}`.toLowerCase();
            return searchStr.includes(query.toLowerCase());
        }).slice(0, 5);

        if (results.length === 0 && history.length === 0) {
            suggestionsEl.style.display = 'none';
            return;
        }

        let html = '';
        if (results.length > 0) {
            html += '<div class="suggestions-header">图书结果</div>';
            html += '<ul class="suggestions-list">';
            results.forEach(book => {
                const title = currentLanguage === 'zh' ? (book.title_zh || book.title) : book.title;
                html += `
                    <li class="suggestion-item" data-search-query="${escapeHtml(book.title)}">
                        <svg class="icon" width="16" height="16"><use href="#icon-search"/></svg>
                        <span>${escapeHtml(title)}</span>
                    </li>`;
            });
            html += '</ul>';
        }

        if (history.length > 0) {
            html += '<div class="suggestions-header">搜索历史</div>';
            html += '<ul class="suggestions-list">';
            history.slice(0, 5).forEach(item => {
                html += `
                    <li class="suggestion-item" data-search-query="${escapeHtml(item.query)}">
                        <svg class="icon" width="16" height="16"><use href="#icon-clock"/></svg>
                        <span>${escapeHtml(item.query)}</span>
                        <svg class="icon delete-history" width="14" height="14" data-delete-query="${escapeHtml(item.query)}"><use href="#icon-x"/></svg>
                    </li>`;
            });
            html += '</ul>';
        }

        suggestionsEl.innerHTML = html;
        suggestionsEl.style.display = 'block';
    } else if (history.length > 0) {
        let html = '<div class="suggestions-header">搜索历史</div>';
        html += '<ul class="suggestions-list">';
        history.slice(0, 10).forEach(item => {
            html += `
                <li class="suggestion-item" data-search-query="${escapeHtml(item.query)}">
                    <svg class="icon" width="16" height="16"><use href="#icon-clock"/></svg>
                    <span>${escapeHtml(item.query)}</span>
                    <svg class="icon delete-history" width="14" height="14" data-delete-query="${escapeHtml(item.query)}"><use href="#icon-x"/></svg>
                </li>`;
        });
        html += '</ul>';
        suggestionsEl.innerHTML = html;
        suggestionsEl.style.display = 'block';
    } else {
        suggestionsEl.style.display = 'none';
    }
}

function deleteHistoryItem(query) {
    try {
        let history = JSON.parse(localStorage.getItem('bookrank_search_history') || '[]');
        history = history.filter(item => item.query !== query);
        localStorage.setItem('bookrank_search_history', JSON.stringify(history));
        renderSearchSuggestions();
    } catch (e) {
        console.error('删除搜索历史失败:', e);
    }
}

function applySearch(query) {
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.value = query;
    }
    const suggestionsEl = document.getElementById('search-suggestions');
    if (suggestionsEl) {
        suggestionsEl.style.display = 'none';
    }
    saveSearchHistory(query);
    applyFilters();
}

// ========== 视图切换 ==========

function toggleView(view) {
    const gridEl = document.getElementById('books-grid');
    const listEl = document.getElementById('books-list');
    const gridBtn = document.getElementById('view-grid');
    const listBtn = document.getElementById('view-list');

    if (view === 'grid') {
        gridEl?.classList.add('active');
        listEl?.classList.remove('active');
        gridBtn?.classList.add('active');
        listBtn?.classList.remove('active');
    } else {
        listEl?.classList.add('active');
        gridEl?.classList.remove('active');
        listBtn?.classList.add('active');
        gridBtn?.classList.remove('active');
    }
    localStorage.setItem('bookrank_view', view);
}

// ========== 收藏功能 ==========

function toggleFavorite(btn, isbn) {
    if (!isbn) return;
    let favorites = JSON.parse(localStorage.getItem('bookrank_favorites') || '[]');
    const index = favorites.indexOf(isbn);
    if (index > -1) {
        favorites.splice(index, 1);
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
        showToast('已取消收藏', 'info');
    } else {
        favorites.push(isbn);
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        showToast('已添加到收藏', 'success');
    }
    localStorage.setItem('bookrank_favorites', JSON.stringify(favorites));
}

// ========== 分享功能 ==========

function shareBook(title, author) {
    if (navigator.share) {
        navigator.share({
            title: `${title} - BookRank`,
            text: `我在 BookRank 发现了好书: ${title} (${author})`,
            url: window.location.href
        }).catch(() => {});
    } else {
        const text = `${title} - ${author}`;
        navigator.clipboard.writeText(text).then(() => {
            showToast('已复制到剪贴板', 'success');
        }).catch(() => {
            showToast('复制失败', 'error');
        });
    }
}

// ========== UI 辅助函数 ==========

/**
 * v0.9.55: 共享分类映射表的本地别名（指向 window.CATEGORIES.getLabel）
 * 之前由 translations.js 暴露为全局函数；现在改从 categories.js 共享模块取
 */
function getCategoryLabel(categoryId, lang) {
    if (typeof window !== 'undefined' && window.CATEGORIES && window.CATEGORIES.getLabel) {
        return window.CATEGORIES.getLabel(categoryId, lang);
    }
    return categoryId;
}

/**
 * v0.9.55: 8 个 skeleton 骨架卡 HTML（与真实卡片等高、动画流畅）
 * 用于分类切换的"按需加载"过程，避免出现空白闪烁
 */
function buildSkeletonCardsHTML(count) {
    var n = count || 8;
    var html = '';
    for (var i = 0; i < n; i++) {
        html += '<article class="card card-skeleton" aria-hidden="true">'
              + '    <div class="skeleton skeleton-image"></div>'
              + '    <div class="skeleton-content">'
              + '        <div class="skeleton skeleton-title"></div>'
              + '        <div class="skeleton skeleton-author"></div>'
              + '        <div class="skeleton skeleton-tag"></div>'
              + '    </div>'
              + '</article>';
    }
    return html;
}

function showSkeleton() {
    var grid = document.getElementById('books-grid');
    var list = document.getElementById('books-list');
    if (grid) grid.innerHTML = buildSkeletonCardsHTML(8);
    if (list) list.innerHTML = '';
}

function hideSkeleton() {
    // 实际渲染由 updateBooksOnPage 完成；这里只做兜底清理
    var skeletons = document.querySelectorAll('.card-skeleton');
    skeletons.forEach(function(el) { if (el.parentNode) el.parentNode.removeChild(el); });
}

function showLoading(text) {
    const overlay = document.getElementById('loading-overlay');
    const textEl = document.getElementById('loading-text');
    if (overlay) overlay.style.display = 'flex';
    if (textEl && text) textEl.textContent = text;
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = 'none';
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast-message ${type === 'error' ? 'toast-error' : type === 'success' ? 'toast-success' : ''}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ========== 翻译系统 ==========

const translationCache = {
    cache: {},
    getBook: function(isbn) {
        try {
            const key = `bookrank_trans_${isbn}`;
            const data = localStorage.getItem(key);
            if (data) {
                const parsed = JSON.parse(data);
                if (Date.now() - parsed.timestamp < 604800000) {
                    return parsed.data;
                }
            }
        } catch (e) {}
        return null;
    },
    setBook: function(isbn, data) {
        try {
            const key = `bookrank_trans_${isbn}`;
            localStorage.setItem(key, JSON.stringify({
                timestamp: Date.now(),
                data: data
            }));
        } catch (e) {}
    }
};

function showTranslationProgress(current, total) {
    const progressEl = document.getElementById('translation-progress');
    const fillEl = document.getElementById('progress-fill');
    const textEl = document.getElementById('progress-text');
    if (progressEl && fillEl && textEl) {
        progressEl.classList.add('active');
        const percent = Math.round((current / total) * 100);
        fillEl.style.width = `${percent}%`;
        textEl.textContent = `${current}/${total} (${percent}%)`;
    }
}

function hideTranslationProgress() {
    const progressEl = document.getElementById('translation-progress');
    if (progressEl) {
        progressEl.classList.remove('active');
    }
}

async function parallelLimit(tasks, concurrency = 3) {
    const results = [];
    let nextIndex = 0;

    async function worker() {
        while (nextIndex < tasks.length) {
            const idx = nextIndex++;
            results[idx] = await tasks[idx]();
        }
    }

    const workers = Array.from({ length: Math.min(concurrency, tasks.length) }, () => worker());
    await Promise.all(workers);
    return results;
}

async function translateAllBooks() {
    const books = window.booksData;
    let toTranslate = [];
    let appliedCount = 0;

    showTranslationProgress(0, books.length);

    for (let i = 0; i < books.length; i++) {
        const book = books[i];
        const isbn = book.isbn13 || book.isbn10;

        if (!isbn) continue;

        if (book.title_zh || book.description_zh) {
            applyTranslationToCard(i, {
                title_zh: book.title_zh,
                desc_zh: book.description_zh,
                details_zh: book.details_zh
            });
            appliedCount++;
            showTranslationProgress(appliedCount, books.length);
            continue;
        }

        const cached = translationCache.getBook(isbn);
        if (cached && cached.title_zh) {
            applyTranslationToCard(i, cached);
            appliedCount++;
            showTranslationProgress(appliedCount, books.length);
            continue;
        }

        toTranslate.push({ index: i, book, isbn });
    }

    if (toTranslate.length === 0) {
        hideTranslationProgress();
        return;
    }

    let translatedCount = appliedCount;
    const tasks = toTranslate.map(({ index, book, isbn }) => async () => {
        await translateSingleBook(index, book, isbn);
        translatedCount++;
        showTranslationProgress(translatedCount, books.length);
    });

    await parallelLimit(tasks, 3);
}

async function translateSingleBook(index, book, isbn) {
    try {
        const bestDescription = getBestDescription(book);
        const detailsText = (bestDescription && bestDescription !== book.description)
            ? bestDescription : '';

        const result = await api.translateBookFields({
            title: book.title || '',
            description: book.description || '',
            details: detailsText
        }, 'en', 'zh');

        let translatedTitle = book.title;
        let translatedDesc = book.description;
        let translatedDetails = bestDescription || book.description;

        if (result.success && result.data) {
            if (result.data.title_zh) translatedTitle = result.data.title_zh;
            if (result.data.description_zh) translatedDesc = result.data.description_zh;
            if (result.data.details_zh) {
                translatedDetails = result.data.details_zh;
            } else if (result.data.description_zh) {
                translatedDetails = result.data.description_zh;
            }
        } else {

            try {
                const tResult = await api.translateText(book.title, 'en', 'zh', 'title');
                if (tResult.success) translatedTitle = tResult.data.translated;
            } catch (e) { /* 标题翻译失败: */ }
            try {
                const dResult = await api.translateText(book.description, 'en', 'zh', 'description');
                if (dResult.success) translatedDesc = dResult.data.translated;
            } catch (e) { /* 描述翻译失败: */ }
            if (detailsText) {
                try {
                    const dtResult = await api.translateText(detailsText, 'en', 'zh', 'details');
                    if (dtResult.success) translatedDetails = dtResult.data.translated;
                } catch (e) {

                    translatedDetails = translatedDesc;
                }
            } else {
                translatedDetails = translatedDesc;
            }
        }

        const translatedData = {
            title_zh: translatedTitle,
            desc_zh: translatedDesc,
            details_zh: translatedDetails,
            original_title: book.title,
            original_desc: book.description,
            original_details: bestDescription
        };

        if (isbn) {
            translationCache.setBook(isbn, translatedData);
        }

        applyTranslationToCard(index, translatedData);

    } catch (error) {
        console.error('翻译失败:', error);
    }
}

async function translateMissingBooks(missingIsbns) {
    if (!missingIsbns || !missingIsbns.length) return;
    var books = window.booksData;
    if (!books) return;

    for (var i = 0; i < books.length; i++) {
        var book = books[i];
        var isbn = book.isbn13 || book.isbn10;
        if (!isbn || missingIsbns.indexOf(isbn) === -1) continue;

        try {
            var result = await api.translateBookFields({
                title: book.title || '',
                description: book.description || '',
                details: ''
            }, 'en', 'zh');

            if (result.success && result.data) {
                var transData = {
                    title: result.data.title_zh || book.title,
                    description: result.data.description_zh || book.description,
                    category: book.category_name || ''
                };
                if (typeof BookI18n !== 'undefined') {
                    BookI18n.updateTranslation(isbn, 'zh', transData);
                }
                book.title_zh = transData.title;
                book.description_zh = transData.description;
            }
        } catch (e) {

        }
    }

    if (typeof BookI18n !== 'undefined') {
        BookI18n.applyLanguage('zh');
    }
}

function applyTranslationToCard(index, data) {
    const cards = document.querySelectorAll('.card');
    const listItems = document.querySelectorAll('.list-item');

    if (cards[index]) {
        const titleEl = cards[index].querySelector('.card-title');
        const descEl = cards[index].querySelector('.card-desc');

        if (titleEl) {
            titleEl.textContent = data.title_zh;
            titleEl.title = data.title_zh;
            if (!titleEl.querySelector('.translation-badge')) {
                titleEl.insertAdjacentHTML('beforeend', '<span class="translation-badge">译</span>');
            }
        }
        if (descEl && data.desc_zh) {
            const shortDesc = data.desc_zh.slice(0, 100) +
                (data.desc_zh.length > 100 ? '...' : '');
            descEl.textContent = shortDesc;
        }
    }

    if (listItems[index]) {
        const titleEl = listItems[index].querySelector('.list-item-title');
        const descEl = listItems[index].querySelector('.list-item-desc');

        if (titleEl) {
            titleEl.textContent = data.title_zh;
        }
        if (descEl && data.desc_zh) {
            const shortDesc = data.desc_zh.slice(0, 200) +
                (data.desc_zh.length > 200 ? '...' : '');
            descEl.textContent = shortDesc;
        }
    }
}

function restoreAllBooks() {
    const books = window.booksData;

    for (let i = 0; i < books.length; i++) {
        const book = books[i];
        const cards = document.querySelectorAll('.card');
        const listItems = document.querySelectorAll('.list-item');

        if (cards[i]) {
            const titleEl = cards[i].querySelector('.card-title');
            const descEl = cards[i].querySelector('.card-desc');

            if (titleEl) {
                titleEl.textContent = book.title;
                titleEl.title = book.title;
                const badge = titleEl.querySelector('.translation-badge');
                if (badge) badge.remove();
            }
            if (descEl && book.description) {
                const shortDesc = book.description.slice(0, 100) +
                    (book.description.length > 100 ? '...' : '');
                descEl.textContent = shortDesc;
            }
        }

        if (listItems[i]) {
            const titleEl = listItems[i].querySelector('.list-item-title');
            const descEl = listItems[i].querySelector('.list-item-desc');

            if (titleEl) {
                titleEl.textContent = book.title;
            }
            if (descEl && book.description) {
                const shortDesc = book.description.slice(0, 200) +
                    (book.description.length > 200 ? '...' : '');
                descEl.textContent = shortDesc;
            }
        }
    }
}

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', function() {
    updateLanguageButtons(currentLanguage);

    if (currentLanguage === 'zh') {
        if (typeof BookI18n !== 'undefined') {
            BookI18n.applyLanguage('zh');
        }
    }
});

// ========== 原有功能保持不变 ==========

/**
 * v0.9.55: 分类缓存（localStorage 持久层 + 内存热层）
 * 内存热层：本次会话内已加载的分类瞬时切换不消耗 NYT API
 * localStorage 持久层：跨会话 24h 内切换同分类也走缓存
 */
const _memoryCategoryCache = new Map();

const categoryCache = {
    get: function(category) {
        // 1) 内存热层（本次会话）
        if (_memoryCategoryCache.has(category)) {
            return _memoryCategoryCache.get(category);
        }
        // 2) localStorage 持久层（24h 跨会话）
        try {
            const key = `bookrank_category_${category}`;
            const data = localStorage.getItem(key);
            if (data) {
                const parsed = JSON.parse(data);
                if (Date.now() - parsed.timestamp < 86400000) {
                    // 命中后回填内存热层，下次切换瞬时
                    _memoryCategoryCache.set(category, parsed.books);
                    return parsed.books;
                }
            }
        } catch (e) { /* 忽略 */ }
        return null;
    },
    set: function(category, books) {
        // 内存热层立即写入
        _memoryCategoryCache.set(category, books);
        // localStorage 持久化（24h TTL）
        try {
            const key = `bookrank_category_${category}`;
            const data = { timestamp: Date.now(), books: books };
            localStorage.setItem(key, JSON.stringify(data));
        } catch (e) { /* 忽略 */ }
    },
    /**
     * v0.9.55: 移除批量预拉取（preload）
     * 改为按需加载：用户切换到哪个分类才请求哪个，避免每天 500 次 NYT 配额被浪费
     * 保留方法名仅供向后兼容（不执行任何网络请求）
     */
    preload: function(_categories, _currentCategory) { /* no-op, v0.9.55 按需加载 */ }
};

/**
 * v0.9.55: 切换分类 - 优先走缓存，未命中才请求 API
 */
async function changeCategory(category) {
    if (category === window.currentCategory) return;

    // 命中缓存：本地已有数据 → 直接渲染，不显示 skeleton
    const cachedBooks = categoryCache.get(category);
    if (Array.isArray(cachedBooks) && cachedBooks.length > 0) {
        window.currentCategory = category;
        window.booksData = cachedBooks;
        currentCategory = category;
        booksData = cachedBooks;

        if (typeof BookI18n !== 'undefined') {
            BookI18n.clear();
            BookI18n.registerAll(cachedBooks);
        }
        // 缓存命中时使用页面上已存在的更新时间（避免显示"刚刚"）
        const timeEl = document.querySelector('.page-subtitle time');
        const cachedTime = timeEl ? timeEl.getAttribute('datetime') : null;
        updateBooksOnPage(cachedBooks, category, cachedTime);
        const newUrl = `/?category=${encodeURIComponent(category)}`;
        window.history.pushState({ category }, '', newUrl);
        if (currentLanguage === 'zh' && typeof BookI18n !== 'undefined') {
            BookI18n.applyLanguage('zh');
        }
        return;
    }

    // 未命中缓存：显示 skeleton 占位 + 全屏 loading
    showSkeleton();
    showLoading('加载中...');

    try {
        const response = await fetch(`/api/category-books?category=${encodeURIComponent(category)}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });

        if (!response.ok) {
            throw new Error('网络请求失败');
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.message || data.error || '加载失败');
        }

        const apiData = data.data || data;
        const books = apiData.books || [];

        // 写入缓存（内存 + localStorage）
        categoryCache.set(category, books);

        window.currentCategory = category;
        window.booksData = books;
        currentCategory = category;     // 模块级，供 rerenderCurrentBooks 使用
        booksData = books;             // 模块级，供 rerenderCurrentBooks 使用

        if (typeof BookI18n !== 'undefined') {
            BookI18n.clear();
            BookI18n.registerAll(books);
        }

        updateBooksOnPage(books, category, apiData.update_time);

        const newUrl = `/?category=${encodeURIComponent(category)}`;
        window.history.pushState({ category }, '', newUrl);

        hideLoading();

        if (currentLanguage === 'zh' && typeof BookI18n !== 'undefined') {
            BookI18n.applyLanguage('zh');
        }

    } catch (error) {
        console.error('分类切换失败:', error);
        showToast(t('toast_category_load_failed', currentLanguage), 'error');
        hideSkeleton();
        hideLoading();
        document.getElementById('category-select').value = window.currentCategory;
    }
}

/**
 * 根据当前语言解析图书分类标签
 * 优先级：1) book 数据自带的中英文名 → 2) CATEGORY_LABELS 映射表 → 3) 默认兜底
 * @param {Object} book - 图书数据对象
 * @param {string} categoryId - 服务端 CATEGORIES 的 key
 * @param {string} lang - 'zh' | 'en'
 * @returns {string} 分类标签文本
 */
function resolveCategoryLabel(book, categoryId, lang) {
    if (lang === 'zh') {
        return book.category_name
            || (typeof getCategoryLabel === 'function' ? getCategoryLabel(categoryId, 'zh') : null)
            || '虚构类';
    }
    return book.list_name
        || book.category_name
        || (typeof getCategoryLabel === 'function' ? getCategoryLabel(categoryId, 'en') : null)
        || 'Fiction';
}

/**
 * 用指定语言重渲染当前已加载的图书（grid + list 视图）
 * 切换语言时被 languagechange 监听器调用，不重新请求 API
 * 数据来源优先级：1) 分类切换后的内存变量 booksData  2) 服务端嵌入的 initial-books-data
 * @param {string} lang - 'zh' | 'en'
 */
function rerenderCurrentBooks(lang) {
    var books = booksData;
    if (!Array.isArray(books) || books.length === 0) {
        var node = document.getElementById('initial-books-data');
        if (node) {
            try { books = JSON.parse(node.textContent || '[]'); } catch (e) { books = []; }
        }
    }
    if (!Array.isArray(books) || books.length === 0) {
        return;
    }
    var category = currentCategory || (window.APP_CONFIG && window.APP_CONFIG.currentCategory) || 'hardcover-fiction';
    var timeEl = document.querySelector('.page-subtitle time');
    var updateTime = timeEl ? timeEl.getAttribute('datetime') : null;
    try {
        updateBooksOnPage(books, category, updateTime);
    } catch (e) {
        console.error('[rerenderCurrentBooks] FAILED:', e.message);
    }
}

/**
 * 把分类下拉框的 option 文本切换到指定语言
 * @param {string} lang - 'zh' | 'en'
 */
function updateCategorySelectOptions(lang) {
    var selectEl = document.getElementById('category-select');
    if (!selectEl || typeof getCategoryLabel !== 'function') return;
    Array.from(selectEl.options).forEach(function(opt) {
        opt.textContent = getCategoryLabel(opt.value, lang);
    });
}

/**
 * 按当前语言格式化更新时间
 * 中文：原样保留（YYYY-MM-DD HH:mm:ss）
 * 英文：月日年 + 12 小时制（Jun 3, 2026 8:08 AM）
 * @param {string} isoTime - 'YYYY-MM-DD HH:mm:ss'
 * @param {string} lang - 'zh' | 'en'
 * @returns {string} 格式化后的时间字符串
 */
function formatLocalTime(isoTime, lang) {
    if (!isoTime) return '';
    if (lang === 'zh') return isoTime;

    var parts = String(isoTime).match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (!parts) return isoTime;

    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var year = parts[1];
    var month = months[parseInt(parts[2], 10) - 1] || parts[2];
    var day = parseInt(parts[3], 10);
    var hour24 = parseInt(parts[4], 10);
    var min = parts[5];
    var ampm = hour24 >= 12 ? 'PM' : 'AM';
    var hour12 = hour24 % 12 || 12;
    return month + ' ' + day + ', ' + year + ' ' + hour12 + ':' + min + ' ' + ampm;
}

function updateBooksOnPage(books, category, updateTime) {
    const isZh = currentLanguage === 'zh';
    const defaultCover = window.APP_CONFIG.defaultCover;
    const lang = currentLanguage;  // 显式捕获当前语言，供所有内嵌字符串使用

    const selectEl = document.getElementById('category-select');
    if (selectEl) {
        selectEl.value = category;
    }

    const timeEl = document.querySelector('.page-subtitle time');
    if (timeEl) {
        var formattedTime = formatLocalTime(updateTime, lang);
        timeEl.textContent = formattedTime
            ? t('time_updated_at', lang, { time: formattedTime })
            : t('time_just_now', lang);
    }

    const gridEl = document.getElementById('books-grid');
    if (gridEl) {
        gridEl.innerHTML = books.map((book, index) => {
            const title = isZh ? (book.title_zh || book.title) : book.title;
            const desc = isZh ? (book.description_zh || book.description || '') : (book.description || '');
            // 分类标签：优先双语映射表 → book 数据 → 默认
            const catLabel = resolveCategoryLabel(book, category, lang);
            return `
            <article class="card card-animate"
                     data-isbn="${escapeHtml(book.isbn13 || book.isbn10 || '')}"
                     data-index="${index}"
                     role="button"
                     tabindex="0"
                     aria-label="${escapeHtml(title)} - ${escapeHtml(t('card_rank_aria', lang, { n: index + 1 }))}">
                <div class="card-image">
                    <div class="cover-frame">
                        <img src="${book.cover || defaultCover}"
                             alt="${escapeHtml(t('card_cover_alt', lang, { title }))}"
                             loading="lazy"
                             width="280"
                             height="240"
                             data-fallback="${defaultCover}">
                    </div>
                    <span class="card-category-tag">${escapeHtml(catLabel)}</span>
                    <span class="card-badge ${index === 0 ? 'gold' : index === 1 ? 'silver' : index === 2 ? 'bronze' : 'other'}"
                          aria-label="${escapeHtml(t('card_badge_aria', lang, { n: index + 1 }))}">
                        ${index + 1}
                    </span>
                    ${book.rank_last_week && book.rank_last_week !== '0' ?
                        (() => {
                            const change = parseInt(book.rank_last_week) - (index + 1);
                            if (change > 0) return `<span class="rank-change up" aria-label="${escapeHtml(t('card_rank_up_aria', lang, { n: change }))}">+${change}</span>`;
                            if (change < 0) return `<span class="rank-change down" aria-label="${escapeHtml(t('card_rank_down_aria', lang, { n: Math.abs(change) }))}">-${Math.abs(change)}</span>`;
                            return '';
                        })() :
                        `<span class="rank-change new" aria-label="${escapeHtml(t('card_new_aria', lang))}">${escapeHtml(t('card_new_badge', lang))}</span>`
                    }
                </div>
                <div class="card-content">
                    <div class="card-rank-row">
                        <span class="card-rank-badge">${escapeHtml(t('card_rank_aria', lang, { n: index + 1 }))}</span>
                        ${book.weeks_on_list ? `<span class="card-weeks"><svg class="icon" width="14" height="14"><use href="#icon-clock"/></svg> ${escapeHtml(t('card_weeks_suffix', lang, { n: book.weeks_on_list }))}</span>` : ''}
                    </div>
                    <h3 class="card-title" title="${escapeHtml(title)}">${escapeHtml(title)}</h3>
                    <p class="card-author">${escapeHtml(book.author)}</p>
                    ${book.isbn13 ? `<p class="card-isbn">${escapeHtml(t('card_isbn_prefix', lang))} ${escapeHtml(book.isbn13)}</p>` : book.isbn10 ? `<p class="card-isbn">${escapeHtml(t('card_isbn_prefix', lang))} ${escapeHtml(book.isbn10)}</p>` : ''}
                    ${desc ? `<p class="card-desc">${escapeHtml(desc.slice(0, 100))}${desc.length > 100 ? '...' : ''}</p>` : ''}
                </div>
            </article>
        `}).join('');
    }

    const listEl = document.getElementById('books-list');
    if (listEl) {
        listEl.innerHTML = books.map((book, index) => {
            const title = isZh ? (book.title_zh || book.title) : book.title;
            const desc = isZh ? (book.description_zh || book.description || '') : (book.description || '');
            const catLabel = resolveCategoryLabel(book, category, lang);
            return `
            <article class="list-item card-animate"
                     data-isbn="${escapeHtml(book.isbn13 || book.isbn10 || '')}"
                     data-index="${index}"
                     role="button"
                     tabindex="0"
                     aria-label="${escapeHtml(title)} - ${escapeHtml(t('card_rank_aria', lang, { n: index + 1 }))}">
                <div class="list-item-image">
                    <img src="${book.cover || defaultCover}"
                         alt="${escapeHtml(t('card_cover_alt', lang, { title }))}"
                         loading="lazy"
                         width="100"
                         height="150"
                         data-fallback="${defaultCover}">
                </div>
                <div class="list-item-content">
                    <div class="list-item-header">
                        <span class="list-item-rank ${index === 0 ? 'rank-gold' : index === 1 ? 'rank-silver' : index === 2 ? 'rank-bronze' : ''}"
                              aria-label="${escapeHtml(t('card_rank_aria', lang, { n: index + 1 }))}">
                            ${index + 1}
                        </span>
                        ${book.rank_last_week && book.rank_last_week !== '0' ?
                            (() => {
                                const change = parseInt(book.rank_last_week) - (index + 1);
                                if (change > 0) return `<span class="rank-change-badge up" aria-label="${escapeHtml(t('card_rank_up_aria', lang, { n: change }))}">+${change}</span>`;
                                if (change < 0) return `<span class="rank-change-badge down" aria-label="${escapeHtml(t('card_rank_down_aria', lang, { n: Math.abs(change) }))}">-${Math.abs(change)}</span>`;
                                return '';
                            })() :
                            `<span class="rank-change-badge new" aria-label="${escapeHtml(t('card_new_aria', lang))}">${escapeHtml(t('card_new_badge', lang))}</span>`
                        }
                        <h3 class="list-item-title">${escapeHtml(title)}</h3>
                    </div>
                    <p class="list-item-author">${escapeHtml(book.author)}</p>
                    ${desc ? `<p class="list-item-desc">${escapeHtml(desc.slice(0, 200))}${desc.length > 200 ? '...' : ''}</p>` : ''}
                    <div class="list-item-meta">
                        <span class="card-tag">${escapeHtml(catLabel)}</span>
                        ${book.weeks_on_list ? `<span class="card-tag"><svg class="icon" width="14" height="14"><use href="#icon-clock"/></svg> ${escapeHtml(t('card_weeks_suffix', lang, { n: book.weeks_on_list }))}</span>` : ''}
                        ${book.publisher ? `<span class="card-tag"><svg class="icon" width="14" height="14"><use href="#icon-building"/></svg> ${escapeHtml(book.publisher)}</span>` : ''}
                    </div>
                </div>
            </article>
        `}).join('');
    }

    const exportActions = document.querySelector('.export-actions-bar');
    if (exportActions) {
        const infoEl = exportActions.querySelector('.export-info');
        if (infoEl) {
            // 共 N 本图书 / {count} books total
            const countText = t('books_count', lang, { count: books.length });
            infoEl.innerHTML = countText.replace(/(\d+)/, '<strong>$1</strong>');
        }
    }
}

// v0.9.55: 已移除 8 分类批量预拉取（每天浪费 8 次 NYT 配额）
// 改为按需加载：用户切换到哪个分类才请求哪个，首次切换显示 skeleton 占位
// （实现见 changeCategory() 和 categoryCache.get()）
document.addEventListener('DOMContentLoaded', function() { /* on-demand loading, no prefetch */ });

window.addEventListener('popstate', function(e) {
    if (e.state && e.state.category) {
        changeCategory(e.state.category);
    }
});

// ========== 手机端手势操作 ==========
let touchStartX = 0;
let touchStartY = 0;
let touchStartTime = 0;

document.addEventListener('touchstart', function(e) {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchStartTime = Date.now();
}, { passive: true });

document.addEventListener('touchend', function(e) {
    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const deltaX = touchEndX - touchStartX;
    const deltaY = touchEndY - touchStartY;
    const deltaTime = Date.now() - touchStartTime;

    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 80 && deltaTime < 500) {
        const gridBtn = document.getElementById('view-grid');
        const listBtn = document.getElementById('view-list');

        if (deltaX > 0 && listBtn.classList.contains('active')) {
            toggleView('grid');
        } else if (deltaX < 0 && gridBtn.classList.contains('active')) {
            toggleView('list');
        }
    }
}, { passive: true });

if (!window.applyFilters) {
    window.applyFilters = function() {
        const category = document.getElementById('category-select').value;
        const search = document.getElementById('search-input').value;
        const publisher = document.getElementById('publisher-select')?.value || '';
        const weeks = document.getElementById('weeks-select')?.value || '';
        const sort = document.getElementById('sort-select')?.value || '';

        if (search) {
            saveSearchHistory(search);
        }

        showLoading('搜索中...');

        let url = `/?category=${encodeURIComponent(category)}`;
        if (search) {
            url += `&search=${encodeURIComponent(search)}`;
        }
        if (publisher) {
            url += `&publisher=${encodeURIComponent(publisher)}`;
        }
        if (weeks) {
            url += `&weeks=${encodeURIComponent(weeks)}`;
        }
        if (sort) {
            url += `&sort=${encodeURIComponent(sort)}`;
        }

        window.location.href = url;
    };
}

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-input');
    const clearBtn = document.getElementById('search-clear-btn');

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            if (clearBtn) {
                clearBtn.style.display = this.value ? 'flex' : 'none';
            }
            const suggestionsEl = document.getElementById('search-suggestions');
            if (suggestionsEl) {
                suggestionsEl.style.display = 'none';
            }
        });

        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                searchInput.value = '';
                clearBtn.style.display = 'none';
                searchInput.focus();
                renderSearchSuggestions();
            });
        }

        searchInput.addEventListener('focus', function() {
            setTimeout(() => renderSearchSuggestions(), 100);
        });

        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (this.value.trim()) {
                    saveSearchHistory(this.value.trim());
                    applyFilters();
                }
            }
        });
    }

    document.addEventListener('click', function(e) {
        const suggestionsEl = document.getElementById('search-suggestions');
        const searchInput = document.getElementById('search-input');
        if (suggestionsEl && searchInput && !e.target.closest('.search-box')) {
            suggestionsEl.style.display = 'none';
        }
    });
});

function refreshData() {
    showLoading('刷新中...');
    window.location.href = window.location.pathname + '?refresh=1';
}

function exportBooks(category) {
    showToast('正在导出...', 'info');
    window.location.href = `/api/export/${encodeURIComponent(category)}`;
}

const escapeHtml = window.escapeHtml || function(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

function getBestDescription(book) {
    const hasDetails = book.details && book.details.length > 50;
    const hasDescription = book.description && book.description.length > 50;

    if (hasDetails && hasDescription) {
        return book.details.length > book.description.length ? book.details : book.description;
    }

    if (hasDetails) return book.details;
    if (hasDescription) return book.description;

    return '暂无详细描述';
}

function buildDetailItem(label, value) {
    return `
        <div class="detail-item">
            <span class="detail-label">${escapeHtml(label)}</span>
            <span class="detail-value">${escapeHtml(value) || '暂无'}</span>
        </div>
    `;
}

function renderBuyLinks(container, buyLinks) {
    container.innerHTML = '';
    if (!buyLinks || buyLinks.length === 0) {
        container.innerHTML = '<p class="no-links">暂无购买链接</p>';
        return;
    }

    buyLinks.forEach(link => {
        if (!link.url) return;
        const a = document.createElement('a');
        a.href = link.url;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.className = 'buy-link';
        a.innerHTML = `<svg class="icon" width="16" height="16"><use href="#icon-external-link"/></svg> ${escapeHtml(link.name || '购买链接')}`;
        a.setAttribute('aria-label', `在 ${escapeHtml(link.name || '购买链接')} 上购买`);
        container.appendChild(a);
    });
}

const booksGrid = document.getElementById('books-grid');
const booksList = document.getElementById('books-list');

function handleCardClick(e) {
    const favBtn = e.target.closest('.btn-favorite');
    if (favBtn) {
        e.stopPropagation();
        const isbn = favBtn.getAttribute('data-isbn');
        if (typeof toggleFavorite === 'function') toggleFavorite(favBtn, isbn);
        return;
    }
    const shareBtn = e.target.closest('.btn-share');
    if (shareBtn) {
        e.stopPropagation();
        const title = shareBtn.getAttribute('data-title');
        const author = shareBtn.getAttribute('data-author');
        if (typeof shareBook === 'function') shareBook(title, author);
        return;
    }
    const amazonLink = e.target.closest('.btn-amazon');
    if (amazonLink) return;
    const card = e.target.closest('.card[data-index], .list-item[data-index]');
    if (!card) return;
    const index = card.getAttribute('data-index');
    const category = window.currentCategory || window.APP_CONFIG.currentCategory;
    window.location.href = `/book/${index}?category=${category}`;
}

if (booksGrid) booksGrid.addEventListener('click', handleCardClick);
if (booksList) booksList.addEventListener('click', handleCardClick);

function handleCardKeydown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
        const card = e.target.closest('.card[data-index], .list-item[data-index]');
        if (card) {
            e.preventDefault();
            card.click();
        }
    }
}

if (booksGrid) booksGrid.addEventListener('keydown', handleCardKeydown);
if (booksList) booksList.addEventListener('keydown', handleCardKeydown);

const categorySelect = document.getElementById('category-select');
if (categorySelect) {
    categorySelect.addEventListener('change', function() {
        changeCategory(this.value);
    });
}

const btnSearch = document.getElementById('btn-search');
const btnClear = document.getElementById('btn-clear');
const btnExportAll = document.getElementById('btn-export-all');
const refreshDataLink = document.getElementById('refresh-data-link');

if (btnSearch) btnSearch.addEventListener('click', () => { if (typeof applyFilters === 'function') applyFilters(); });
if (btnClear) btnClear.addEventListener('click', () => { if (typeof clearFilters === 'function') clearFilters(); });
if (btnExportAll) btnExportAll.addEventListener('click', () => { if (typeof exportBooks === 'function') exportBooks('all'); });
if (refreshDataLink) refreshDataLink.addEventListener('click', () => { if (typeof refreshData === 'function') refreshData(); });

const searchSuggestions = document.getElementById('search-suggestions');
if (searchSuggestions) {
    searchSuggestions.addEventListener('click', function(e) {
        const deleteBtn = e.target.closest('.delete-history');
        if (deleteBtn) {
            e.stopPropagation();
            const query = deleteBtn.getAttribute('data-delete-query');
            if (typeof deleteHistoryItem === 'function') deleteHistoryItem(query);
            return;
        }
        const item = e.target.closest('.suggestion-item[data-search-query]');
        if (item) {
            const query = item.getAttribute('data-search-query');
            if (typeof applySearch === 'function') applySearch(query);
        }
    });
}

window.addEventListener('languagechange', function(e) {
    var lang = e.detail.language;
    currentLanguage = lang;

    if (typeof applyPageTranslation === 'function') {
        applyPageTranslation(lang);
    }

    // 切换分类下拉框 option 文本（中英）
    if (typeof updateCategorySelectOptions === 'function') {
        try { updateCategorySelectOptions(lang); } catch(err) { console.warn('updateCategorySelectOptions:', err); }
    }

    // 重渲染图书卡片（grid + list），无需重新请求 API
    if (typeof rerenderCurrentBooks === 'function') {
        try { rerenderCurrentBooks(lang); } catch(err) { console.warn('rerenderCurrentBooks:', err); }
    }

    // BookI18n 兜底（用于更新仍未迁移到 renderBooks 的 DOM 节点）
    if (typeof BookI18n !== 'undefined' && BookI18n.size() > 0) {
        try { BookI18n.applyLanguage(lang); } catch(e) { console.warn('BookI18n error:', e); }
    }
});
