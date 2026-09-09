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

// 语言控制变量（统一读取：app_language 优先，兼容旧 bookrank_language 键）
let currentLanguage = localStorage.getItem('app_language') || localStorage.getItem('bookrank_language') || 'en';

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
    } catch (e) {
        // 空历史或脏数据：视为无历史继续
    }

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
                    <li class="suggestion-item" data-search-query="${esc(book.title)}">
                        <svg class="icon" width="16" height="16"><use href="#icon-search"/></svg>
                        <span>${esc(title)}</span>
                    </li>`;
            });
            html += '</ul>';
        }

        if (history.length > 0) {
            html += '<div class="suggestions-header">搜索历史</div>';
            html += '<ul class="suggestions-list">';
            history.slice(0, 5).forEach(item => {
                html += `
                    <li class="suggestion-item" data-search-query="${esc(item.query)}">
                        <svg class="icon" width="16" height="16"><use href="#icon-clock"/></svg>
                        <span>${esc(item.query)}</span>
                        <svg class="icon delete-history" width="14" height="14" data-delete-query="${esc(item.query)}"><use href="#icon-x"/></svg>
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
                <li class="suggestion-item" data-search-query="${esc(item.query)}">
                    <svg class="icon" width="16" height="16"><use href="#icon-clock"/></svg>
                    <span>${esc(item.query)}</span>
                    <svg class="icon delete-history" width="14" height="14" data-delete-query="${esc(item.query)}"><use href="#icon-x"/></svg>
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

    localStorage.setItem('bookrank_view', view);

    if (gridEl && listEl) {
        // Dual-view DOM: switch visible view via CSS classes
        if (view === 'grid') {
            gridEl.classList.add('active');
            listEl.classList.remove('active');
            gridBtn?.classList.add('active');
            listBtn?.classList.remove('active');
        } else {
            listEl.classList.add('active');
            gridEl.classList.remove('active');
            listBtn?.classList.add('active');
            gridBtn?.classList.remove('active');
        }
    } else {
        // Single-view DOM: navigate so the server renders the requested view
        const params = new URLSearchParams(window.location.search);
        params.set('view', view);
        window.location.href = window.location.pathname + '?' + params.toString();
    }
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
                const hasMetadata = ['updateTime', 'updateFrequency', 'listPublishedDate']
                    .every(field => Object.prototype.hasOwnProperty.call(parsed, field));
                if (Date.now() - parsed.timestamp < 86400000 && Array.isArray(parsed.books) && hasMetadata) {
                    // 命中后回填内存热层，下次切换瞬时
                    _memoryCategoryCache.set(category, parsed);
                    return parsed;
                }
                localStorage.removeItem(key);
            }
        } catch (e) { /* 忽略 */ }
        return null;
    },
    set: function(category, books, updateTime, updateFrequency, listPublishedDate) {
        const data = {
            timestamp: Date.now(),
            books: books,
            updateTime: updateTime,
            updateFrequency: updateFrequency,
            listPublishedDate: listPublishedDate
        };
        // 内存热层立即写入
        _memoryCategoryCache.set(category, data);
        // localStorage 持久化（24h TTL）
        try {
            const key = `bookrank_category_${category}`;
            localStorage.setItem(key, JSON.stringify(data));
        } catch (e) { /* 忽略 */ }
    },
};

/**
 * v0.9.55: 切换分类 - 优先走缓存，未命中才请求 API
 */
async function changeCategory(category) {
    if (category === window.currentCategory) return;

    // 命中缓存：本地已有数据 → 直接渲染，不显示 skeleton
    const cached = categoryCache.get(category);
    if (cached && Array.isArray(cached.books) && cached.books.length > 0) {
        const cachedBooks = cached.books;
        window.currentCategory = category;
        window.booksData = cachedBooks;
        currentCategory = category;
        booksData = cachedBooks;

        if (typeof BookI18n !== 'undefined') {
            BookI18n.clear();
            BookI18n.registerAll(cachedBooks);
        }
        updateBooksOnPage(
            cachedBooks,
            category,
            cached.updateTime,
            cached.updateFrequency,
            cached.listPublishedDate
        );
        const params = new URLSearchParams();
        params.set('category', category);
        const view = new URLSearchParams(window.location.search).get('view') || localStorage.getItem('bookrank_view');
        if (view && ['grid', 'list'].includes(view)) {
            params.set('view', view);
        }
        const newUrl = window.location.pathname + '?' + params.toString();
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
        categoryCache.set(
            category,
            books,
            apiData.update_time,
            apiData.update_frequency,
            apiData.list_published_date
        );

        window.currentCategory = category;
        window.booksData = books;
        currentCategory = category;     // 模块级，供 rerenderCurrentBooks 使用
        booksData = books;             // 模块级，供 rerenderCurrentBooks 使用

        if (typeof BookI18n !== 'undefined') {
            BookI18n.clear();
            BookI18n.registerAll(books);
        }

        updateBooksOnPage(books, category, apiData.update_time, apiData.update_frequency, apiData.list_published_date);

        const params = new URLSearchParams();
        params.set('category', category);
        const view = new URLSearchParams(window.location.search).get('view') || localStorage.getItem('bookrank_view');
        if (view && ['grid', 'list'].includes(view)) {
            params.set('view', view);
        }
        const newUrl = window.location.pathname + '?' + params.toString();
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

function getCategoryUpdateFrequency(category, explicitFrequency) {
    if (explicitFrequency) return String(explicitFrequency).toLowerCase();
    const monthly = window.APP_CONFIG && Array.isArray(window.APP_CONFIG.monthlyCategories)
        ? window.APP_CONFIG.monthlyCategories
        : [];
    return monthly.includes(category) ? 'monthly' : 'weekly';
}

function getListPublishedDate(books, explicitDate) {
    if (explicitDate) return explicitDate;
    if (!Array.isArray(books)) return '';
    const book = books.find(item => item && item.published_date && item.published_date !== 'Unknown');
    return book ? book.published_date : '';
}

function updateMonthlyListHint(category, books, updateFrequency, listPublishedDate, lang) {
    const hintEl = document.getElementById('monthly-list-hint');
    if (!hintEl) return;

    const frequency = getCategoryUpdateFrequency(category, updateFrequency);
    if (frequency !== 'monthly') {
        hintEl.hidden = true;
        hintEl.textContent = '';
        return;
    }

    const publishedDate = getListPublishedDate(books, listPublishedDate);
    hintEl.textContent = publishedDate
        ? t('monthly_list_with_date', lang, { date: publishedDate })
        : t('monthly_list', lang);
    hintEl.hidden = false;
}

function renderRankChange(book, rank, lang, className) {
    const previous = Number(book.previous_rank ?? book.rank_last_week ?? 0);
    if (previous > 0) {
        const change = previous - rank;
        if (!change) return '';
        const direction = change > 0 ? 'up' : 'down';
        const label = t(change > 0 ? 'card_rank_up_aria' : 'card_rank_down_aria', lang, { n: Math.abs(change) });
        return `<span class="${className} ${direction}" aria-label="${esc(label)}">${change > 0 ? '+' : ''}${change}</span>`;
    }
    const weeks = Number(book.weeks_on_list) || 0;
    if (book.is_new ?? (previous === 0 && weeks === 1)) {
        return `<span class="${className} new" aria-label="${esc(t('card_new_aria', lang))}">${esc(t('card_new_badge', lang))}</span>`;
    }
    if (book.is_returning ?? (previous === 0 && weeks > 1)) {
        const label = lang === 'zh' ? '重返榜单' : 'Returning to the list';
        return `<span class="${className} new" aria-label="${label}">${lang === 'zh' ? '重返' : 'RETURN'}</span>`;
    }
    return '';
}

function renderCoverWeeks(book, lang) {
    const weeks = Number(book.weeks_on_list) || 0;
    if (weeks <= 0) return '';
    const label = t('weeks_on_list', lang);
    const valueLabel = t('card_weeks_suffix', lang, { n: weeks });
    const suffix = valueLabel.replace(String(weeks), '').trim();
    return `<span class="cover-weeks" role="img" aria-label="${esc(label)}: ${weeks}${esc(suffix)}">
                <span class="cover-weeks-value"><strong>${weeks}</strong><span>${esc(suffix)}</span></span>
            </span>`;
}

function updateBooksOnPage(books, category, updateTime, updateFrequency, listPublishedDate) {
    const isZh = currentLanguage === 'zh';
    const defaultCover = window.APP_CONFIG.defaultCover;
    const lang = currentLanguage;  // 显式捕获当前语言，供所有内嵌字符串使用

    const selectEl = document.getElementById('category-select');
    if (selectEl) {
        selectEl.value = category;
    }

    const timeEl = document.querySelector('.page-subtitle time');
    if (timeEl) {
        timeEl.setAttribute('datetime', updateTime || '');
        var formattedTime = formatLocalTime(updateTime, lang);
        timeEl.textContent = formattedTime
            ? t('time_updated_at', lang, { time: formattedTime })
            : t('time_just_now', lang);
    }

    updateMonthlyListHint(category, books, updateFrequency, listPublishedDate, lang);

    const gridEl = document.getElementById('books-grid');
    if (gridEl) {
        gridEl.innerHTML = books.map((book, index) => {
            const rank = Number(book.rank) || index + 1;
            const sourceIndex = book.source_index ?? rank - 1;
            const sourceCategory = book.source_category || category;
            const cover = book.cover && book.cover !== defaultCover
                ? book.cover
                : (book._original_cover || defaultCover);
            const title = isZh ? (book.title_zh || book.title) : book.title;
            const desc = isZh ? (book.description_zh || book.description || '') : (book.description || '');
            // 分类标签：优先双语映射表 → book 数据 → 默认
            const catLabel = resolveCategoryLabel(book, category, lang);
            return `
            <article class="card card-animate"
                     data-isbn="${esc(book.isbn13 || book.isbn10 || '')}"
                     data-index="${sourceIndex}"
                     data-category="${esc(sourceCategory)}"
                     role="button"
                     tabindex="0"
                     aria-label="${esc(title)} - ${esc(t('card_rank_aria', lang, { n: rank }))}">
                <div class="card-image">
                    <div class="cover-frame">
                        <img src="${cover}"
                             alt="${esc(t('card_cover_alt', lang, { title }))}"
                             loading="lazy"
                             width="280"
                             height="240"
                             data-original="${book._original_cover || ''}"
                             data-fallback="${defaultCover}">
                        ${renderCoverWeeks(book, lang)}
                    </div>
                    <span class="card-category-tag">${esc(catLabel)}</span>
                    <span class="card-badge ${rank === 1 ? 'gold' : rank === 2 ? 'silver' : rank === 3 ? 'bronze' : 'other'}"
                          aria-label="${esc(t('card_badge_aria', lang, { n: rank }))}">
                        ${rank}
                    </span>
                    ${renderRankChange(book, rank, lang, 'rank-change')}
                    </div>
                    <h3 class="card-title" title="${esc(title)}">${esc(title)}</h3>
                    <p class="card-author">${esc(book.author)}</p>
                    ${book.isbn13 ? `<p class="card-isbn">${esc(t('card_isbn_prefix', lang))} ${esc(book.isbn13)}</p>` : book.isbn10 ? `<p class="card-isbn">${esc(t('card_isbn_prefix', lang))} ${esc(book.isbn10)}</p>` : ''}
                    ${desc ? `<p class="card-desc">${esc(desc.slice(0, 100))}${desc.length > 100 ? '...' : ''}</p>` : ''}
                </div>
            </article>
        `}).join('');
    }

    const listEl = document.getElementById('books-list');
    if (listEl) {
        listEl.innerHTML = books.map((book, index) => {
            const rank = Number(book.rank) || index + 1;
            const sourceIndex = book.source_index ?? rank - 1;
            const sourceCategory = book.source_category || category;
            const cover = book.cover && book.cover !== defaultCover
                ? book.cover
                : (book._original_cover || defaultCover);
            const title = isZh ? (book.title_zh || book.title) : book.title;
            const desc = isZh ? (book.description_zh || book.description || '') : (book.description || '');
            const catLabel = resolveCategoryLabel(book, category, lang);
            return `
            <article class="list-item card-animate"
                     data-isbn="${esc(book.isbn13 || book.isbn10 || '')}"
                     data-index="${sourceIndex}"
                     data-category="${esc(sourceCategory)}"
                     role="button"
                     tabindex="0"
                     aria-label="${esc(title)} - ${esc(t('card_rank_aria', lang, { n: rank }))}">
                <div class="list-item-image">
                <img src="${cover}"
                         alt="${esc(t('card_cover_alt', lang, { title }))}"
                         loading="lazy"
                         width="100"
                         height="150"
                         data-original="${book._original_cover || ''}"
                         data-fallback="${defaultCover}">
                    ${renderCoverWeeks(book, lang)}
                </div>
                <div class="list-item-content">
                    <div class="list-item-header">
                        <span class="list-item-rank ${rank === 1 ? 'rank-gold' : rank === 2 ? 'rank-silver' : rank === 3 ? 'rank-bronze' : ''}"
                              aria-label="${esc(t('card_rank_aria', lang, { n: rank }))}">
                            ${rank}
                        </span>
                        ${renderRankChange(book, rank, lang, 'rank-change-badge')}
                        <h3 class="list-item-title">${esc(title)}</h3>
                    </div>
                    <p class="list-item-author">${esc(book.author)}</p>
                    ${desc ? `<p class="list-item-desc">${esc(desc.slice(0, 200))}${desc.length > 200 ? '...' : ''}</p>` : ''}
                    <div class="list-item-meta">
                        <span class="card-tag">${esc(catLabel)}</span>
                        ${book.weeks_on_list ? `<span class="card-tag"><svg class="icon" width="14" height="14"><use href="#icon-clock"/></svg> ${esc(t('card_weeks_suffix', lang, { n: book.weeks_on_list }))}</span>` : ''}
                        ${book.publisher ? `<span class="card-tag"><svg class="icon" width="14" height="14"><use href="#icon-building"/></svg> ${esc(book.publisher)}</span>` : ''}
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

    initOnDemandTranslation();
});

function refreshData() {
    showLoading('刷新中...');
    window.location.href = window.location.pathname + '?refresh=1';
}

function exportBooks(category) {
    showToast('正在导出...', 'info');
    window.location.href = `/api/export/${encodeURIComponent(category)}`;
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
    // Native links retain their source category and browser keyboard behavior.
    if (e.target.closest('a[href]')) return;
    const card = e.target.closest('.card[data-index], .list-item[data-index]');
    if (!card) return;
    const index = card.getAttribute('data-index');
    const category = card.getAttribute('data-category') || window.currentCategory || window.APP_CONFIG.currentCategory;
    window.location.href = `/book/${encodeURIComponent(index)}?category=${encodeURIComponent(category)}`;
}

if (booksGrid) booksGrid.addEventListener('click', handleCardClick);
if (booksList) booksList.addEventListener('click', handleCardClick);

function handleCardKeydown(e) {
    if (e.target.closest('a[href]')) return;
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

/* 按需翻译：中文页对缺中文标题的卡片逐本请求服务端翻译（结果服务端持久化）。
   免费层后台线程不可靠，故由前端在空闲时逐本触发；失败即停，不打扰阅读。 */
function initOnDemandTranslation() {
    try {
        var lang = document.documentElement.getAttribute('lang') || '';
        var appLang = null;
        try {
            appLang = localStorage.getItem('app_language') || localStorage.getItem('bookrank_language');
        } catch (e) { /* ignore */ }
        if (appLang) {
            if (appLang !== 'zh') return;
        } else if (lang && lang.toLowerCase().indexOf('zh') !== 0) {
            return;
        }

        var cards = Array.prototype.slice.call(
            document.querySelectorAll('article[data-needs-translation="1"][data-isbn]')
        ).slice(0, 15);
        if (!cards.length) {
            hideTranslationProgress();
            return;
        }

        var bar = document.getElementById('translation-progress');
        var label = bar ? bar.querySelector('.progress-text') : null;
        var fill = bar ? bar.querySelector('.progress-fill') : null;
        var total = cards.length;
        var done = 0;
        var stopped = false;

        function paint() {
            if (label) label.textContent = '正在翻译... (' + done + '/' + total + ')';
            if (fill) fill.style.width = Math.round((done / total) * 100) + '%';
            if (done >= total && bar) bar.style.display = 'none';
        }

        function next() {
            if (stopped || !cards.length) {
                paint();
                return;
            }
            var card = cards.shift();
            var isbn = (card.getAttribute('data-isbn') || '').replace(/[^0-9Xx]/g, '');
            if (!isbn) {
                done += 1;
                paint();
                next();
                return;
            }
            fetch('/api/translate/book/' + encodeURIComponent(isbn), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            })
                .then(function (resp) {
                    if (!resp.ok) {
                        // 翻译服务不可用（key 未配/限流）：停掉后续请求
                        if (resp.status === 401 || resp.status === 500 || resp.status === 429) stopped = true;
                        throw new Error('http ' + resp.status);
                    }
                    return resp.json();
                })
                .then(function (result) {
                    var book = result && result.data && result.data.book;
                    if (book) applyCardTranslation(card, book);
                    card.removeAttribute('data-needs-translation');
                    done += 1;
                    paint();
                    next();
                })
                .catch(function () {
                    done += 1;
                    paint();
                    next();
                });
        }

        function applyCardTranslation(card, book) {
            var title = book.title_zh;
            if (title) {
                var link = card.querySelector('h3.list-item-title a');
                if (link) {
                    link.textContent = title;
                } else {
                    var titleEl = card.querySelector('h3.card-title');
                    if (titleEl) {
                        titleEl.textContent = title;
                        titleEl.setAttribute('title', title);
                    }
                }
            }
            var desc = book.description_zh;
            if (desc) {
                var descEl = card.querySelector('p.card-desc, p.list-item-desc');
                if (descEl) {
                    var limit = descEl.classList.contains('card-desc') ? 80 : 200;
                    descEl.textContent = desc.length > limit ? desc.slice(0, limit) + '...' : desc;
                }
            }
            try {
                if (typeof BookI18n !== 'undefined' && BookI18n.updateBatch) {
                    var bisbn = (card.getAttribute('data-isbn') || '').replace(/[^0-9Xx]/g, '');
                    BookI18n.updateBatch([{ isbn: bisbn, language: 'zh', data: { title: title, description: desc } }]);
                }
            } catch (e) { /* ignore */ }
        }

        paint();
        // 延迟启动：先让首屏可交互
        setTimeout(next, 1500);
    } catch (e) {
        /* ignore */
    }
}

function hideTranslationProgress() {
    var b = document.getElementById('translation-progress');
    if (b) b.style.display = 'none';
}
