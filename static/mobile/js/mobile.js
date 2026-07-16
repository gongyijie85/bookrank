/* BookRank 移动端交互脚本
   - 卡片点击导航
   - CSRF token 懒加载
   - Toast 通知
   - 30 秒轮询（周报生成）
   - v0.9.78：语言切换、详情页 Tab 切换、Google Books 详情懒加载 */
'use strict';

(function () {
    const SERVER_LANGUAGE = document.documentElement.getAttribute('data-lang') || 'zh';

    // ===== 1. 卡片点击导航 =====
    document.addEventListener('click', function (e) {
        if (e.target.closest('select, input, button')) {
            return;
        }
        const card = e.target.closest('[data-href]');
        if (!card) return;
        const href = card.getAttribute('data-href');
        if (href) window.location.href = href;
    });

    // ===== 2. CSRF token 缓存 =====
    let cachedCsrfToken = null;

    function getCsrfToken() {
        if (cachedCsrfToken) return Promise.resolve(cachedCsrfToken);
        return fetch('/api/csrf-token')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                cachedCsrfToken = (data && data.data && data.data.csrf_token) || '';
                return cachedCsrfToken;
            })
            .catch(function () { return ''; });
    }

    // ===== 3. Toast 通知 =====
    function toast(msg, type) {
        const container = document.getElementById('m-toast-container');
        if (!container) {
            alert(msg);
            return;
        }
        const el = document.createElement('div');
        el.className = 'm-toast' + (type ? ' ' + type : '');
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(function () {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.3s';
            setTimeout(function () {
                if (el.parentNode) el.parentNode.removeChild(el);
            }, 300);
        }, 2500);
    }

    // ===== 4. 周报生成轮询 =====
    let pollingTimer = null;
    function startPolling(intervalMs) {
        if (pollingTimer) clearInterval(pollingTimer);
        pollingTimer = setInterval(function () {
            fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function () { window.location.reload(); })
                .catch(function () {});
        }, intervalMs || 30000);
    }

    // ===== 5. v0.9.78 语言切换 =====
    const LANG_STORAGE_KEY = 'bookrank_language';
    const APP_LANG_STORAGE_KEY = 'app_language';

    function getSavedLanguage() {
        return SERVER_LANGUAGE === 'en' ? 'en' : 'zh';
    }

    function setSavedLanguage(lang) {
        try {
            localStorage.setItem(LANG_STORAGE_KEY, lang);
            localStorage.setItem(APP_LANG_STORAGE_KEY, lang);
        } catch (e) { /* 忽略 localStorage 不可用 */ }
    }

    function updateLangMenu(lang) {
        document.querySelectorAll('#m-lang-dropdown button[data-lang]').forEach(function (btn) {
            const isActive = btn.getAttribute('data-lang') === lang;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-current', isActive ? 'true' : 'false');
        });
    }

    function applyLanguage(lang) {
        if (typeof window.BookI18n !== 'undefined' && window.BookI18n.applyLanguage) {
            window.BookI18n.applyLanguage(lang);
        }
        setSavedLanguage(lang);
        updateLangMenu(lang);
        document.documentElement.setAttribute('lang', lang === 'en' ? 'en' : 'zh-CN');
        // 派发事件，供其他组件监听
        try {
            window.dispatchEvent(new CustomEvent('languagechange', { detail: { language: lang } }));
        } catch (e) { /* 旧浏览器忽略 */ }
    }

    function switchLanguage(lang) {
        lang = lang === 'en' ? 'en' : 'zh';
        setSavedLanguage(lang);
        const next = window.location.pathname + window.location.search + window.location.hash;
        window.location.href = '/set-language?lang=' + lang + '&next=' + encodeURIComponent(next);
    }

    function initLangSwitcher() {
        const globe = document.getElementById('m-lang-globe');
        const dropdown = document.getElementById('m-lang-dropdown');
        if (!globe || !dropdown) return;

        // 点击地球按钮：切换下拉
        globe.addEventListener('click', function (e) {
            e.stopPropagation();
            const isOpen = dropdown.classList.toggle('open');
            globe.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });

        // 点击下拉项：切换语言
        dropdown.querySelectorAll('button[data-lang]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const lang = btn.getAttribute('data-lang') || 'zh';
                switchLanguage(lang);
                dropdown.classList.remove('open');
                globe.setAttribute('aria-expanded', 'false');
            });
        });

        // 点击页面其他位置：关闭下拉
        document.addEventListener('click', function (e) {
            if (!dropdown.contains(e.target) && e.target !== globe) {
                dropdown.classList.remove('open');
                globe.setAttribute('aria-expanded', 'false');
            }
        });

        // 初始化：读取已保存语言
        const saved = getSavedLanguage();
        applyLanguage(saved);
    }

    // ===== 6. v0.9.78 详情页 Tab 切换 =====
    function switchDetailTab(tabName) {
        const wrapper = document.querySelector('.m-detail-tabs-wrapper');
        if (!wrapper) return;
        wrapper.querySelectorAll('.m-tab-btn').forEach(function (btn) {
            const isActive = btn.getAttribute('data-tab') === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        wrapper.querySelectorAll('.m-tab-panel').forEach(function (panel) {
            panel.classList.toggle('active', panel.getAttribute('data-panel') === tabName);
        });
    }

    function initDetailTabs() {
        const wrapper = document.querySelector('.m-detail-tabs-wrapper');
        if (!wrapper) return;
        wrapper.querySelectorAll('.m-tab-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const tabName = btn.getAttribute('data-tab');
                if (!tabName) return;
                switchDetailTab(tabName);
                // 切到"详细信息"时懒加载 Google Books 详细数据
                if (tabName === 'details') {
                    fetchBookDetails(wrapper);
                }
            });
        });
    }

    // ===== 7. v0.9.78 懒加载 Google Books 详细介绍 =====
    function fetchBookDetails(wrapper) {
        if (!wrapper || wrapper.dataset.loaded === '1') return;
        const isbn = wrapper.getAttribute('data-isbn') || '';
        const bookIndex = wrapper.getAttribute('data-book-index');
        const category = wrapper.getAttribute('data-category') || '';
        if (!isbn || bookIndex === null || bookIndex === '') return;

        wrapper.dataset.loaded = '1';
        const extraEl = wrapper.querySelector('[data-panel="details"] .m-tab-panel-extra');
        if (!extraEl) return;

        const params = new URLSearchParams({
            book_index: bookIndex,
            isbn: isbn,
            category: category,
        });

        fetch('/api/book-details?' + params.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data || !data.data) return;
                const details = (data.data.details || '').trim();
                const PLACEHOLDERS = ['暂无详细介绍', 'No detailed description available.', 'No summary available.', 'No summary available'];
                if (!details || PLACEHOLDERS.indexOf(details) !== -1) return;
                // 渲染到 .m-tab-panel-extra
                extraEl.innerHTML = '';
                const heading = document.createElement('h3');
                heading.style.cssText = 'font-size:14px;font-weight:600;margin:0 0 8px 0;color:var(--color-text-secondary);';
                heading.textContent = 'Google Books 详细介绍';
                extraEl.appendChild(heading);
                details.split('\n').forEach(function (para) {
                    const p = para.trim();
                    if (!p) return;
                    const node = document.createElement('p');
                    node.textContent = p;
                    extraEl.appendChild(node);
                });
            })
            .catch(function () { /* 静默失败，详情区已有元信息列表 */ });
    }

    // ===== 暴露 API =====
    window.MobileApp = {
        getCsrfToken: getCsrfToken,
        toast: toast,
        startPolling: startPolling,
        getSessionId: function () {
            const m = document.cookie.match(/(?:^|; )session_id=([^;]*)/);
            return m ? m[1] : 'anonymous';
        },
        // v0.9.78 新增
        applyLanguage: applyLanguage,
        switchLanguage: switchLanguage,
        switchDetailTab: switchDetailTab,
        fetchBookDetails: fetchBookDetails,
    };

    // ===== DOM Ready 初始化 =====
    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        initLangSwitcher();
        initDetailTabs();
    });
})();
