import { api } from './api.js';

/* ============================================
   BookRank 首页交互逻辑 (Notion 设计系统)
   ============================================ */

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

    console.log(`翻译应用完成: ${appliedCount}本使用缓存, ${toTranslate.length}本需要API翻译`);

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
            console.log('合并翻译失败，回退到逐字段翻译');
            try {
                const tResult = await api.translateText(book.title, 'en', 'zh', 'title');
                if (tResult.success) translatedTitle = tResult.data.translated;
            } catch (e) { console.log('标题翻译失败:', e); }
            try {
                const dResult = await api.translateText(book.description, 'en', 'zh', 'description');
                if (dResult.success) translatedDesc = dResult.data.translated;
            } catch (e) { console.log('描述翻译失败:', e); }
            if (detailsText) {
                try {
                    const dtResult = await api.translateText(detailsText, 'en', 'zh', 'details');
                    if (dtResult.success) translatedDetails = dtResult.data.translated;
                } catch (e) {
                    console.log('详情翻译失败:', e);
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
            console.log('后台翻译失败 ISBN ' + isbn + ':', e);
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

const categoryCache = {
    get: function(category) {
        try {
            const key = `bookrank_category_${category}`;
            const data = localStorage.getItem(key);
            if (data) {
                const parsed = JSON.parse(data);
                if (Date.now() - parsed.timestamp < 86400000) {
                    return parsed.books;
                }
            }
        } catch (e) {
            console.log('Cache read error:', e);
        }
        return null;
    },
    set: function(category, books) {
        try {
            const key = `bookrank_category_${category}`;
            const data = {
                timestamp: Date.now(),
                books: books
            };
            localStorage.setItem(key, JSON.stringify(data));
        } catch (e) {
            console.log('Cache write error:', e);
        }
    },
    preload: function(categories, currentCategory) {
        categories.forEach(cat => {
            if (cat !== currentCategory && !this.get(cat)) {
                fetch(`/?category=${encodeURIComponent(cat)}`, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                }).then(() => {
                    console.log(`Preloaded ${cat}`);
                }).catch(() => {});
            }
        });
    }
};

async function changeCategory(category) {
    if (category === window.currentCategory) return;

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

        window.currentCategory = category;
        window.booksData = books;

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
        showToast('加载失败，请重试', 'error');
        hideLoading();
        document.getElementById('category-select').value = window.currentCategory;
    }
}

function updateBooksOnPage(books, category, updateTime) {
    const isZh = currentLanguage === 'zh';
    const defaultCover = window.APP_CONFIG.defaultCover;

    const selectEl = document.getElementById('category-select');
    if (selectEl) {
        selectEl.value = category;
    }

    const timeEl = document.querySelector('.page-subtitle time');
    if (timeEl && updateTime) {
        timeEl.textContent = `更新于: ${updateTime}`;
    }

    const gridEl = document.getElementById('books-grid');
    if (gridEl) {
        gridEl.innerHTML = books.map((book, index) => {
            const title = isZh ? (book.title_zh || book.title) : book.title;
            const desc = isZh ? (book.description_zh || book.description || '') : (book.description || '');
            const catLabel = isZh ? (book.category_name || '虚构类') : (book.list_name || book.category_name || 'Fiction');
            return `
            <article class="card card-animate"
                     data-isbn="${escapeHtml(book.isbn13 || book.isbn10 || '')}"
                     data-index="${index}"
                     role="button"
                     tabindex="0"
                     aria-label="${escapeHtml(title)} - 第${index + 1}名">
                <div class="card-image">
                    <img src="${book.cover || defaultCover}"
                         alt="${escapeHtml(title)}封面"
                         loading="lazy"
                         width="280"
                         height="240"
                         data-fallback="${defaultCover}">
                    <span class="card-category-tag">${escapeHtml(catLabel)}</span>
                    <span class="card-badge ${index === 0 ? 'gold' : index === 1 ? 'silver' : index === 2 ? 'bronze' : 'other'}"
                          aria-label="排名: 第${index + 1}名">
                        ${index + 1}
                    </span>
                    ${book.rank_last_week && book.rank_last_week !== '0' ?
                        (() => {
                            const change = parseInt(book.rank_last_week) - (index + 1);
                            if (change > 0) return `<span class="rank-change up" aria-label="上升${change}名">+${change}</span>`;
                            if (change < 0) return `<span class="rank-change down" aria-label="下降${Math.abs(change)}名">-${Math.abs(change)}</span>`;
                            return '';
                        })() :
                        `<span class="rank-change new" aria-label="新书上榜">NEW</span>`
                    }
                </div>
                <div class="card-content">
                    <div class="card-rank-row">
                        <span class="card-rank-badge">第${index + 1}名</span>
                        ${book.weeks_on_list ? `<span class="card-weeks"><svg class="icon" width="14" height="14"><use href="#icon-clock"/></svg> ${book.weeks_on_list}周</span>` : ''}
                    </div>
                    <h3 class="card-title" title="${escapeHtml(title)}">${escapeHtml(title)}</h3>
                    <p class="card-author">${escapeHtml(book.author)}</p>
                    ${book.isbn13 ? `<p class="card-isbn">ISBN: ${escapeHtml(book.isbn13)}</p>` : book.isbn10 ? `<p class="card-isbn">ISBN: ${escapeHtml(book.isbn10)}</p>` : ''}
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
            const catLabel = isZh ? (book.category_name || '虚构类') : (book.list_name || book.category_name || 'Fiction');
            return `
            <article class="list-item card-animate"
                     data-isbn="${escapeHtml(book.isbn13 || book.isbn10 || '')}"
                     data-index="${index}"
                     role="button"
                     tabindex="0"
                     aria-label="${escapeHtml(title)} - 第${index + 1}名">
                <div class="list-item-image">
                    <img src="${book.cover || defaultCover}"
                         alt="${escapeHtml(title)}封面"
                         loading="lazy"
                         width="100"
                         height="150"
                         data-fallback="${defaultCover}">
                </div>
                <div class="list-item-content">
                    <div class="list-item-header">
                        <span class="list-item-rank ${index === 0 ? 'rank-gold' : index === 1 ? 'rank-silver' : index === 2 ? 'rank-bronze' : ''}"
                              aria-label="第${index + 1}名">
                            ${index + 1}
                        </span>
                        ${book.rank_last_week && book.rank_last_week !== '0' ?
                            (() => {
                                const change = parseInt(book.rank_last_week) - (index + 1);
                                if (change > 0) return `<span class="rank-change-badge up" aria-label="上升${change}名">+${change}</span>`;
                                if (change < 0) return `<span class="rank-change-badge down" aria-label="下降${Math.abs(change)}名">-${Math.abs(change)}</span>`;
                                return '';
                            })() :
                            `<span class="rank-change-badge new" aria-label="新书上榜">NEW</span>`
                        }
                        <h3 class="list-item-title">${escapeHtml(title)}</h3>
                    </div>
                    <p class="list-item-author">${escapeHtml(book.author)}</p>
                    ${desc ? `<p class="list-item-desc">${escapeHtml(desc.slice(0, 200))}${desc.length > 200 ? '...' : ''}</p>` : ''}
                    <div class="list-item-meta">
                        <span class="card-tag">${escapeHtml(catLabel)}</span>
                        ${book.weeks_on_list ? `<span class="card-tag"><svg class="icon" width="14" height="14"><use href="#icon-clock"/></svg> ${book.weeks_on_list}周</span>` : ''}
                        ${book.publisher ? `<span class="card-tag"><svg class="icon" width="14" height="14"><use href="#icon-building"/></svg> ${escapeHtml(book.publisher)}</span>` : ''}
                    </div>
                </div>
                <div class="list-item-actions">
                    <button class="btn btn-icon btn-outline btn-favorite"
                            data-isbn="${book.isbn13 || ''}"
                            aria-label="收藏 ${escapeHtml(title)}"
                            aria-pressed="false">
                        <svg class="icon" width="18" height="18"><use href="#icon-heart"/></svg>
                    </button>
                </div>
            </article>
        `}).join('');
    }

    const exportActions = document.querySelector('.export-actions-bar');
    if (exportActions) {
        const infoEl = exportActions.querySelector('.export-info');
        if (infoEl) {
            infoEl.innerHTML = `共 <strong>${books.length}</strong> 本图书`;
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const categories = Array.from(document.querySelectorAll('#category-select option')).map(opt => opt.value);
    const currentCategory = window.currentCategory;

    setTimeout(() => {
        categories.forEach(cat => {
            if (cat !== currentCategory) {
                fetch(`/api/category-books?category=${encodeURIComponent(cat)}`, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          categoryCache.set(cat, data.books);
                      }
                  }).catch(() => {});
            }
        });
    }, 5000);
});

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

    if (typeof BookI18n !== 'undefined' && BookI18n.size() > 0) {
        BookI18n.applyLanguage(lang);
    } else {
        _handleLanguageChange(lang);
    }
});
