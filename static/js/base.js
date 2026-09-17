/**
 * BookRank Base JavaScript - Optimized for performance and accessibility
 */
(function() {
    'use strict';

    // ===== DOM Elements =====
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const loadingOverlay = document.getElementById('loading-overlay');
    const toastContainer = document.getElementById('toast-container');
    const themeToggle = document.getElementById('theme-toggle');
    const searchInput = document.getElementById('search-input');

    // ===== 顶部导航高度同步（--top-nav-height 跟随真实高度）=====

    /**
     * 把 --top-nav-height 同步为导航条的**实测高度**。
     *
     * 为什么需要这一步：窄屏（≤767px）导航会折行成两行，真实高度随视口变化
     * （实测 390px 下为 95px），任何写死的值都只能适配一种宽度。
     *
     * 此前该变量在 ≤767px 被写成 `auto`，而它被用于 `calc(var(--top-nav-height) + …)`，
     * 于是这些声明全部**非法并被浏览器丢弃**，后果有两处（均由 dsh-design-audit 实测发现）：
     *   ① .sidebar-toggle 的 top 退回 auto，position:fixed 的按钮落到 y≈0 的导航条区域内，
     *      被 z-index 1000 的 .top-nav 完全覆盖 —— 6 个采样点全部命中导航，侧栏开关点不到；
     *   ② 主内容 padding-top 少了约 7px（88px < 导航实际 95px），正文压在导航条下缘。
     *
     * 窄屏下 .top-nav 的 height 是 auto（不是 var），因此实测回写不会自触发循环；
     * 仍加一道相等判断以彻底避免 ResizeObserver 抖动。
     */
    function syncTopNavHeight() {
        const nav = document.querySelector('.top-nav');
        if (!nav) return;
        const height = Math.round(nav.getBoundingClientRect().height);
        if (height <= 0) return;
        const current = document.documentElement.style.getPropertyValue('--top-nav-height').trim();
        if (current === height + 'px') return;
        document.documentElement.style.setProperty('--top-nav-height', height + 'px');
    }

    (function initTopNavHeightSync() {
        // 注意：不要在这里用 `if (!nav) return;` 提前退出 —— base.js 若在导航条进入 DOM
        // 之前执行，提前退出会把下面的 load 监听一并跳过，同步将永不发生（本次实测踩到）。
        // 因此监听无条件注册，找不到导航时由 load 事件兜底。
        syncTopNavHeight();
        window.addEventListener('load', syncTopNavHeight);
        window.addEventListener('resize', syncTopNavHeight);
        document.addEventListener('DOMContentLoaded', syncTopNavHeight);
        const nav = document.querySelector('.top-nav');
        if (nav && typeof ResizeObserver === 'function') {
            new ResizeObserver(syncTopNavHeight).observe(nav);
        }
    })();

    // ===== Utilities =====

    /**
     * Escape HTML to prevent XSS
     */
    function esc(text) {
        if (text === undefined || text === null) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    // ===== Loading Functions =====

    /**
     * Show loading overlay with custom message
     * @param {string} text - Loading message
     */
    function showLoading(text = '加载中...') {
        if (!loadingOverlay) return;

        const textElement = loadingOverlay.querySelector('.loading-text');
        if (textElement) {
            textElement.textContent = text;
        }
        loadingOverlay.style.display = 'flex';
        loadingOverlay.classList.remove('hidden');

        // Prevent body scroll when loading
        document.body.style.overflow = 'hidden';
    }

    /**
     * Hide loading overlay
     */
    function hideLoading() {
        if (!loadingOverlay) return;

        loadingOverlay.classList.add('hidden');

        // Delay display none for smooth transition
        setTimeout(() => {
            if (!loadingOverlay.classList.contains('hidden')) return;
            loadingOverlay.style.display = 'none';
            document.body.style.overflow = '';
        }, 300);
    }

    // ===== Toast Notifications =====

    /**
     * Icon map for toast types (using SVG icons)
     */
    const iconMap = {
        success: 'icon-check-circle',
        error: 'icon-x-circle',
        warning: 'icon-alert-triangle',
        info: 'icon-info'
    };

    /**
     * Show toast notification
     * @param {string} message - Toast message
     * @param {string} type - Toast type (success, error, warning, info)
     * @param {number} duration - Display duration in milliseconds
     */
    function showToast(message, type = 'info', duration = 3000) {
        if (!toastContainer) return;

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'polite');

        const iconClass = iconMap[type] || iconMap.info;

        toast.innerHTML = `
            <svg class="icon" width="20" height="20" style="flex-shrink: 0;"><use href="#${iconClass}"/></svg>
            <span>${esc(message)}</span>
            <button class="toast-close" aria-label="关闭提示">
                <svg class="icon" width="16" height="16"><use href="#icon-x"/></svg>
            </button>
        `;

        toastContainer.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Close button handler
        const closeBtn = toast.querySelector('.toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => removeToast(toast));
        }

        // Auto remove after duration
        const removeTimeout = setTimeout(() => removeToast(toast), duration);

        // Store timeout on element for cleanup
        toast.dataset.timeoutId = removeTimeout;
    }

    /**
     * Remove toast from DOM
     * @param {HTMLElement} toast - Toast element
     */
    function removeToast(toast) {
        if (!toast || !toast.parentNode) return;

        // Clear timeout
        if (toast.dataset.timeoutId) {
            clearTimeout(parseInt(toast.dataset.timeoutId));
        }

        toast.classList.remove('show');

        // Remove after animation
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }

    // ===== Sidebar Functions =====

    /**
     * Toggle sidebar on mobile
     */
    function toggleSidebar() {
        if (!sidebar || !sidebarToggle) return;
        sidebar.classList.toggle('open');
        sidebarToggle.setAttribute(
            'aria-expanded',
            sidebar.classList.contains('open')
        );
    }

    /**
     * Close sidebar when clicking outside on mobile
     */
    function handleClickOutside(event) {
        if (!sidebar || !sidebarToggle) return;

        const isMobile = window.innerWidth <= 1024;
        const isOutside = !sidebar.contains(event.target) && !sidebarToggle.contains(event.target);

        if (isMobile && isOutside && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            sidebarToggle.setAttribute('aria-expanded', 'false');
        }
    }

    // ===== 窄屏全局导航对话框（native <dialog>）=====

    /**
     * 窄屏（≤900px）全局导航：原生 <dialog> 的 showModal。
     *
     * 原生行为已覆盖：Escape 关闭、焦点圈定（focus containment）、
     * 关闭后焦点还原到打开者（showModal 前的活动元素）。因此这里
     * **不**实现自定义焦点陷阱，只做：打开按钮 → showModal()、
     * 关闭按钮 → close()、点击遮罩/对话框空白区 → close()。
     * 各控件不存在时静默跳过（模板/老页面可能没有这些元素）。
     */
    function initNavDialog() {
        const dialog = document.getElementById('site-nav-dialog');
        if (!dialog || typeof dialog.showModal !== 'function') return;

        const openBtn = document.getElementById('nav-menu-btn');
        const closeBtn = document.getElementById('site-nav-dialog-close');

        function syncExpanded() {
            if (openBtn) {
                openBtn.setAttribute('aria-expanded', dialog.open ? 'true' : 'false');
            }
        }

        if (openBtn) {
            openBtn.addEventListener('click', function() {
                dialog.showModal();
                syncExpanded();
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                dialog.close();
            });
        }

        // 点击遮罩/对话框自身（非子元素）关闭；点内容区不关闭
        dialog.addEventListener('click', function(event) {
            if (event.target === dialog) {
                dialog.close();
            }
        });

        // 真实浏览器中，从 autofocus 关闭按钮按 Shift+Tab 会把焦点丢到 document.body
        //（showModal 的焦点圈定并非在所有浏览器/焦点序下都完整）。这里在打开的 dialog
        // 内做一个小范围 Tab/Shift+Tab 循环：只对当前可见、可用、可聚焦的元素生效，
        // 不改动原生 Escape、close() 与关闭后的焦点归还行为。
        dialog.addEventListener('keydown', function(event) {
            if (event.key !== 'Tab' || !dialog.open) return;

            var focusables = Array.prototype.slice.call(
                dialog.querySelectorAll(
                    'a[href], button:not([disabled]), input:not([disabled]), ' +
                    'select:not([disabled]), textarea:not([disabled]), ' +
                    '[tabindex]:not([tabindex="-1"])'
                )
            ).filter(function(el) {
                return el.offsetParent !== null && !el.disabled && el.getAttribute('aria-hidden') !== 'true';
            });
            if (focusables.length === 0) return;

            var first = focusables[0];
            var last = focusables[focusables.length - 1];
            var active = document.activeElement;

            if (event.shiftKey) {
                if (active === first || !dialog.contains(active)) {
                    event.preventDefault();
                    last.focus();
                }
            } else if (active === last || !dialog.contains(active)) {
                event.preventDefault();
                first.focus();
            }
        });

        // 任何关闭路径（close()、Escape、点击遮罩）后同步 aria-expanded，
        // 并在菜单按钮存在、已连接且可见时把焦点还给按钮（对话框关闭时不再持有焦点）。
        dialog.addEventListener('close', function() {
            syncExpanded();
            if (openBtn && openBtn.isConnected && openBtn.offsetParent !== null) {
                openBtn.focus();
            }
        });
    }

    // ===== Theme Functions =====

    /**
     * Get system theme preference
     */
    function getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    /**
     * Get saved theme from localStorage
     */
    function getSavedTheme() {
        return localStorage.getItem('theme');
    }

    /**
     * Apply theme to document
     * @param {string} theme - Theme name (dark, light)
     */
    function applyTheme(theme) {
        // Always set data-theme to explicit value (never remove)
        // This prevents @media (prefers-color-scheme: dark) from overriding
        // the user's explicit light-mode choice on dark-mode systems.
        document.documentElement.setAttribute('data-theme', theme);

        // Update theme toggle button
        updateThemeToggleIcon(theme === 'dark');

        // Save preference
        localStorage.setItem('theme', theme);
    }

    /**
     * Update theme toggle button icon
     * @param {boolean} isDark - Whether dark theme is active
     */
    function updateThemeToggleIcon(isDark) {
        if (!themeToggle) return;

        const icon = themeToggle.querySelector('svg.icon');
        if (icon) {
            const useEl = icon.querySelector('use');
            if (useEl) {
                useEl.setAttribute('href', isDark ? '#icon-sun' : '#icon-moon');
            }
        }
    }

    /**
     * Toggle between light and dark theme
     */
    function toggleTheme() {
        const currentTheme = getSavedTheme() || getSystemTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        const lang = getCurrentLang();

        applyTheme(newTheme);
        showToast(
            window.t(newTheme === 'dark' ? 'theme_switched_dark' : 'theme_switched_light', lang),
            'success'
        );
    }

    /**
     * Initialize theme based on saved preference or system setting
     */
    function initTheme() {
        const savedTheme = getSavedTheme();
        const theme = savedTheme || getSystemTheme();

        // Always apply the theme to ensure icon is set correctly
        applyTheme(theme);

        // Add click listener to theme toggle
        if (themeToggle) {
            themeToggle.addEventListener('click', toggleTheme);
            themeToggle.setAttribute('aria-label', window.t('theme_toggle_label', getCurrentLang()));
        }
    }

    // ===== Favorite Functions =====

    /**
     * Toggle favorite status for a book
     * @param {HTMLElement} button - Favorite button element
     * @param {string} bookId - Book ID
     */
    function toggleFavorite(button, bookId) {
        if (!button) return;

        const isActive = button.classList.contains('active');
        const method = isActive ? 'DELETE' : 'POST';
        const url = isActive ? `/api/favorites/${bookId}` : '/api/favorites';

        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: method === 'POST' ? JSON.stringify({ isbn: bookId }) : undefined,
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                button.classList.toggle('active');
                const nowActive = button.classList.contains('active');
                // 按钮里是 <svg class="icon"><use href="#icon-heart"/></svg>，没有 <i> 节点：
                // 旧代码 querySelector('i') 恒为 null，实心图标从未换上过。
                const iconUse = button.querySelector('use');
                if (iconUse) {
                    iconUse.setAttribute('href', nowActive ? '#icon-heart-filled' : '#icon-heart');
                }
                button.setAttribute('aria-pressed', nowActive ? 'true' : 'false');
                button.classList.add('heart-beat');
                setTimeout(() => button.classList.remove('heart-beat'), 500);
                showToast(nowActive ? '已添加到收藏' : '已取消收藏', 'success');
            } else {
                showToast(data.message || '操作失败', 'error');
            }
        })
        .catch(() => showToast('网络错误，请重试', 'error'));
    }

    // ===== Filter Functions =====

    /**
     * Clear all filters and reload page
     */
    function clearFilters() {
        showLoading('重置中...');
        window.location.href = window.location.pathname;
    }

    /**
     * Apply filters and reload page, preserving existing query params like view
     */
    function applyFilters() {
        const category = document.getElementById('category-select')?.value;
        const search = document.getElementById('search-input')?.value;

        showLoading('筛选中...');

        const params = new URLSearchParams(window.location.search);

        if (category) params.set('category', category);
        else params.delete('category');

        if (search) params.set('search', search.trim());
        else params.delete('search');

        const query = params.toString();
        window.location.href = window.location.pathname + (query ? '?' + query : '');
    }

    // ===== Keyboard Navigation =====

    /**
     * Handle keyboard events for accessibility
     */
    function handleKeydown(event) {
        // Close modal on Escape
        if (event.key === 'Escape') {
            const modal = document.querySelector('.modal.active');
            if (modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        }
    }

    // ===== Initialize =====

    /**
     * Initialize all event listeners
     */
    function initEventListeners() {
        // Sidebar toggle
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', toggleSidebar);
            sidebarToggle.setAttribute('aria-label', '切换侧边栏');
            sidebarToggle.setAttribute('aria-expanded', 'false');
        }

        // Click outside to close sidebar
        document.addEventListener('click', handleClickOutside);

        // Keyboard events
        document.addEventListener('keydown', handleKeydown);

        // Search input (仅首页；新书页表单有自己的提交处理)
        if (searchInput && document.getElementById('category-select')) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    applyFilters();
                }
            });
        }

        // Filter form submit (prevents default GET reload and uses JS filters)
        // 仅绑定首页表单（包含 category-select）；新书页有自己的 submit 处理
        const filterForm = document.getElementById('filter-form');
        if (filterForm && document.getElementById('category-select')) {
            filterForm.addEventListener('submit', (e) => {
                e.preventDefault();
                applyFilters();
            });
        }

        const langGlobe = document.getElementById('lang-globe');
        const langOptZh = document.getElementById('lang-opt-zh');
        const langOptEn = document.getElementById('lang-opt-en');

        if (langGlobe) langGlobe.addEventListener('click', toggleLangMenu);
        if (langOptZh) langOptZh.addEventListener('click', () => setGlobalLanguage('zh'));
        if (langOptEn) langOptEn.addEventListener('click', () => setGlobalLanguage('en'));
    }

    /**
     * 封面地址规范化：委托 cover.js 的 BookRankCover.toSrc。
     * cover.js 未加载时仍走同源代理，禁止身份回退把境外图床写进 img src。
     */
    function coverToSrc(raw) {
        if (window.BookRankCover && typeof window.BookRankCover.toSrc === 'function') {
            return window.BookRankCover.toSrc(raw);
        }
        const value = (raw === null || raw === undefined) ? '' : String(raw).trim();
        if (!value) return '';
        if (value.indexOf('/static/') === 0 || value.indexOf('/cache/images/') === 0 || value.indexOf('/cover') === 0) {
            return value;
        }
        return '/cover?src=' + encodeURIComponent(value);
    }

    /**
     * 全局图片错误处理 - 替代 onerror 内联属性
     *
     * 多级回退：本地缓存(cover_local_path) → 原始URL(cover_original_url) → 默认封面(data-fallback)
     * 通过 data-original / data-fallback 属性实现，避免无限回退。
     */
    function applyImageFallback(img) {
        const tried = img.dataset.imgTried ? img.dataset.imgTried.split(',') : [];
        const current = img.currentSrc || img.src;
        if (tried.indexOf(current) === -1) tried.push(current);

        const original = coverToSrc(img.getAttribute('data-original'));
        const fallback = img.getAttribute('data-fallback');
        const candidates = [];
        if (original && tried.indexOf(original) === -1) candidates.push(original);
        if (fallback && tried.indexOf(fallback) === -1) candidates.push(fallback);

        if (candidates.length > 0) {
            img.dataset.imgTried = tried.join(',') + ',' + candidates[0];
            img.src = candidates[0];
        }
    }

    function initImageErrorHandler() {
        document.addEventListener('error', function(e) {
            if (e.target.tagName === 'IMG') applyImageFallback(e.target);
        }, true);
        // base.js 在 body 末尾执行，此前已失败的图片不会再触发 error，需补扫
        document.querySelectorAll('img[data-fallback]').forEach(function(img) {
            if (img.complete && img.naturalWidth === 0) applyImageFallback(img);
        });
    }

    /**
     * Initialize on DOM ready
     */
    function init() {
        initEventListeners();
        initNavDialog();
        initTheme();
        initLanguage();
        initImageErrorHandler();
        if (window.BookRankCover && typeof window.BookRankCover.bind === 'function') {
            window.BookRankCover.bind(document);
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ===== Language Functions =====

    /**
     * Toggle language dropdown menu
     * @param {Event} event - Click event
     */
    function toggleLangMenu(event) {
        event.stopPropagation();
        const dropdown = document.getElementById('lang-dropdown');
        const btn = document.getElementById('lang-globe');
        if (!dropdown || !btn) return;

        const isOpen = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

        // Close on outside click
        if (isOpen) {
            setTimeout(() => {
                document.addEventListener('click', closeLangMenu, { once: true });
            }, 0);
        }
    }

    function closeLangMenu() {
        const dropdown = document.getElementById('lang-dropdown');
        const btn = document.getElementById('lang-globe');
        if (dropdown) dropdown.classList.remove('open');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }

    /**
     * Update language dropdown UI state
     * @param {string} lang - Current language code
     */
    function updateLangDropdown(lang) {
        const currentLabel = document.getElementById('lang-current');
        const optZh = document.getElementById('lang-opt-zh');
        const optEn = document.getElementById('lang-opt-en');

        if (currentLabel) currentLabel.textContent = lang === 'zh' ? '中' : 'EN';
        if (optZh) optZh.classList.toggle('active', lang === 'zh');
        if (optEn) optEn.classList.toggle('active', lang === 'en');

        // Also update old-style buttons if present (backward compatibility)
        const langEnBtn = document.getElementById('lang-en');
        const langZhBtn = document.getElementById('lang-zh');
        if (langEnBtn && langZhBtn) {
            langEnBtn.classList.toggle('active', lang === 'en');
            langZhBtn.classList.toggle('active', lang === 'zh');
        }
    }

    /**
     * Current UI language: saved preference, else browser detection
     */
    function getCurrentLang() {
        var savedLang = localStorage.getItem('app_language') || localStorage.getItem('bookrank_language');
        var browserLang = navigator.language || navigator.userLanguage || '';
        var defaultLang = browserLang.startsWith('zh') ? 'zh' : 'en';
        return savedLang || defaultLang;
    }

    /**
     * Initialize language based on saved preference or browser detection
     */
    function initLanguage() {
        var currentLang = getCurrentLang();

        updateLangDropdown(currentLang);

        var labelEl = document.getElementById('lang-current');
        if (labelEl) { labelEl.textContent = currentLang === 'zh' ? '\u4e2d' : 'EN'; }

        var langEnBtn = document.getElementById('lang-en');
        var langZhBtn = document.getElementById('lang-zh');
        if (langEnBtn && langZhBtn) {
            langEnBtn.classList.toggle('active', currentLang === 'en');
            langZhBtn.classList.toggle('active', currentLang === 'zh');
        }

        window.dispatchEvent(new CustomEvent('languagechange', { detail: { language: currentLang } }));
    }

    // ===== Expose Public API =====

    // Expose global helpers for inline handlers/templates
    window.esc = esc;
    window.escapeHtml = esc;
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.showToast = showToast;
    window.toggleFavorite = toggleFavorite;
    window.clearFilters = clearFilters;
    window.applyFilters = applyFilters;
    window.toggleTheme = toggleTheme;
    window.toggleLangMenu = toggleLangMenu;
    window.closeLangMenu = closeLangMenu;

})();
