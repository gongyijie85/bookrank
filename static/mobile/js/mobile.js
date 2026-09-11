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
    // 服务端令牌是**一次性**的：@csrf_protect 校验通过后会立即删除该令牌记录
    // （app/utils/api_helpers.py:214-222）。因此客户端在每次变更请求后必须清空
    // 缓存，否则同一页面上的第二次变更会因令牌已失效而收到 403。
    // 典型故障：移动端「我的收藏」页删第一个收藏成功，之后的都失败。
    let cachedCsrfToken = null;

    function getCsrfToken(forceRefresh) {
        if (cachedCsrfToken && !forceRefresh) return Promise.resolve(cachedCsrfToken);
        cachedCsrfToken = null;
        return fetch('/api/csrf-token', { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                cachedCsrfToken = (data && data.data && data.data.csrf_token) || '';
                return cachedCsrfToken;
            })
            .catch(function () { return ''; });
    }

    /**
     * 携带 CSRF 令牌发起请求（变更类请求请使用本方法，而非手动拼接 token）。
     * - 令牌一次性：请求结束后清空缓存，下次自动重新获取。
     * - 容错：若因令牌失效被拒（403 且响应含 csrf），强制刷新令牌重试一次，
     *   用于覆盖并发变更请求共用同一令牌的场景。
     */
    function csrfFetch(url, options) {
        var opts = options || {};
        var method = (opts.method || 'GET').toUpperCase();
        var isMutation = ['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(method) !== -1;

        function withToken(token) {
            var headers = {};
            if (opts.headers) {
                Object.keys(opts.headers).forEach(function (k) { headers[k] = opts.headers[k]; });
            }
            if (token) headers['X-CSRF-Token'] = token;
            return fetch(url, Object.assign({}, opts, { headers: headers }));
        }

        return getCsrfToken().then(withToken).then(function (response) {
            if (!isMutation) return response;
            cachedCsrfToken = null;

            if (response.status === 403) {
                return response.clone().text().then(function (body) {
                    if (body && body.toLowerCase().indexOf('csrf') !== -1) {
                        return getCsrfToken(true).then(withToken).then(function (retried) {
                            cachedCsrfToken = null;
                            return retried;
                        });
                    }
                    return response;
                });
            }
            return response;
        }, function (err) {
            if (isMutation) cachedCsrfToken = null;
            throw err;
        });
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

    // ===== 4. 封面兜底（CSP 下内联 onerror 全部失效，改为事件委托） =====
    // 标记属性只作开关：目标地址取自常量，不从页面属性流入 src
    const COVER_FALLBACK = '/static/default-cover.png';

    function applyImageFallback(img) {
        if (img.dataset.coverFallbackApplied === '1') return;
        img.dataset.coverFallbackApplied = '1';
        img.src = COVER_FALLBACK;
    }

    function initImageFallback() {
        // img 的 error 事件不冒泡，只能在捕获阶段监听
        document.addEventListener(
            'error',
            function (e) {
                const el = e.target;
                if (el && el.tagName === 'IMG' && el.hasAttribute('data-cover-fallback')) applyImageFallback(el);
            },
            true
        );
        // mobile.js 在 body 末尾执行，此前已失败的图片不会再触发 error，需补扫
        document.querySelectorAll('img[data-cover-fallback]').forEach(function (img) {
            if (img.complete && img.naturalWidth === 0) applyImageFallback(img);
        });
    }

    // ===== 4b. 周报生成轮询（模板只放 [data-report-poll] 标记） =====
    function initReportPolling() {
        if (!document.querySelector('[data-report-poll]')) return;
        const timer = setInterval(function () {
            fetch('/api/weekly-report/status', { cache: 'no-store' })
                .then(function (r) {
                    return r.json();
                })
                .then(function (d) {
                    if (d && d.has_current_week) {
                        clearInterval(timer);
                        window.location.reload();
                    }
                })
                .catch(function () {
                    /* 状态接口暂不可用，下一轮再试 */
                });
        }, 30000);
    }

    // ===== 4c. 首页搜索入口展开/收起（#66）=====
    function initMobileSearchToggle() {
        const toggle = document.getElementById('m-search-toggle');
        const bar = document.getElementById('m-search-bar');
        if (!toggle || !bar) return;
        toggle.addEventListener('click', function () {
            const expanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
            if (expanded) {
                bar.setAttribute('hidden', '');
            } else {
                bar.removeAttribute('hidden');
                const input = document.getElementById('m-search-input');
                if (input) input.focus();
            }
        });
        // 带搜索词进来时保持展开
        const input = document.getElementById('m-search-input');
        if (input && input.value) {
            bar.removeAttribute('hidden');
            toggle.setAttribute('aria-expanded', 'true');
        }
    }

    // ===== 5. v0.9.78 语言切换 =====
    const LANG_STORAGE_KEY = 'bookrank_language';
    const APP_LANG_STORAGE_KEY = 'app_language';

    function getSavedLanguage() {
        try {
            const saved = localStorage.getItem(APP_LANG_STORAGE_KEY) || localStorage.getItem(LANG_STORAGE_KEY);
            if (saved === 'en' || saved === 'zh') return saved;
        } catch (e) { /* 忽略 localStorage 不可用 */ }
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

    // ===== 4d. 分享（文案由模板以 data 属性传入：babel.cfg 不提取 JS） =====
    function initShareButtons() {
        document.addEventListener('click', function (e) {
            const btn = e.target.closest ? e.target.closest('[data-share-url]') : null;
            if (!btn) return;
            e.preventDefault();
            const url = btn.getAttribute('data-share-url');
            const title = btn.getAttribute('data-share-title') || document.title;

            function copyLink() {
                const promptText = btn.getAttribute('data-share-prompt') || '';
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard
                        .writeText(url)
                        .then(function () {
                            toast(btn.getAttribute('data-share-copied') || '');
                        })
                        .catch(function () {
                            window.prompt(promptText, url);
                        });
                } else {
                    window.prompt(promptText, url);
                }
            }

            if (navigator.share) {
                navigator.share({ title: title, url: url }).catch(copyLink);
            } else {
                copyLink();
            }
        });
    }

    // ===== 暴露 API =====
    window.MobileApp = {
        getCsrfToken: getCsrfToken,
        csrfFetch: csrfFetch,
        toast: toast,
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
        initMobileSearchToggle();
        initImageFallback();
        initReportPolling();
        initShareButtons();
    });
})();
