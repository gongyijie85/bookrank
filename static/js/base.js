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

    // ===== Utilities =====

    /**
     * Debounce function for performance optimization
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Generate unique ID
     */
    function generateId() {
        return 'id_' + Math.random().toString(36).substr(2, 9);
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
            <span>${escapeHtml(message)}</span>
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

        applyTheme(newTheme);
        showToast(
            newTheme === 'dark' ? '已切换到深色模式' : '已切换到浅色模式',
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
            themeToggle.setAttribute('aria-label', '切换主题');
        }
    }

    // ===== View Mode Functions =====

    /**
     * Build URL with updated view param while preserving other query params
     * @param {string} view - View mode (grid, list)
     * @returns {string} URL with view param set
     */
    function buildViewUrl(view) {
        const params = new URLSearchParams(window.location.search);
        params.set('view', view);
        return window.location.pathname + '?' + params.toString();
    }

    /**
     * Toggle between grid and list view
     * @param {string} view - View mode (grid, list)
     */
    function toggleView(view) {
        const grid = document.getElementById('books-grid');
        const list = document.getElementById('books-list');
        const gridBtn = document.getElementById('view-grid');
        const listBtn = document.getElementById('view-list');

        localStorage.setItem('bookrank_view', view);

        if (grid && list) {
            // Dual-view DOM: switch visible view via CSS classes
            if (view === 'grid') {
                grid.classList.add('active');
                list.classList.remove('active');
                gridBtn?.classList.add('active');
                listBtn?.classList.remove('active');
            } else {
                list.classList.add('active');
                grid.classList.remove('active');
                gridBtn?.classList.remove('active');
                listBtn?.classList.add('active');
            }
        } else {
            // Single-view DOM: let the server render the requested view
            window.location.href = buildViewUrl(view);
        }
    }

    /**
     * Initialize view mode from saved preference
     */
    function initViewMode() {
        const grid = document.getElementById('books-grid');
        const list = document.getElementById('books-list');
        const savedView = localStorage.getItem('bookrank_view') || localStorage.getItem('viewMode');
        const urlParams = new URLSearchParams(window.location.search);

        if (!grid || !list) {
            // Single-view DOM: redirect to saved preference when URL has no view param
            if (!urlParams.has('view') && savedView) {
                const currentView = grid ? 'grid' : (list ? 'list' : null);
                if (currentView && currentView !== savedView) {
                    window.location.href = buildViewUrl(savedView);
                }
            }
            return;
        }

        // Dual-view DOM: apply saved preference or server-rendered active view
        const serverView = grid.classList.contains('active') ? 'grid' : (list.classList.contains('active') ? 'list' : null);
        const view = savedView || serverView || 'grid';
        toggleView(view);
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
                const icon = button.querySelector('i');
                const nowActive = button.classList.contains('active');
                if (icon) {
                    icon.innerHTML = nowActive
                        ? '<use href="#icon-heart-filled"/>'
                        : '<use href="#icon-heart"/>';
                }
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

    /**
     * Handle search input with debounce
     */
    const handleSearch = debounce(() => {
        applyFilters();
    }, 500);

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

        // View toggle buttons
        const viewGridBtn = document.getElementById('view-grid');
        const viewListBtn = document.getElementById('view-list');

        if (viewGridBtn) {
            viewGridBtn.addEventListener('click', () => toggleView('grid'));
        }
        if (viewListBtn) {
            viewListBtn.addEventListener('click', () => toggleView('list'));
        }

        const langGlobe = document.getElementById('lang-globe');
        const langOptZh = document.getElementById('lang-opt-zh');
        const langOptEn = document.getElementById('lang-opt-en');

        if (langGlobe) langGlobe.addEventListener('click', toggleLangMenu);
        if (langOptZh) langOptZh.addEventListener('click', () => switchLanguage('zh'));
        if (langOptEn) langOptEn.addEventListener('click', () => switchLanguage('en'));
    }

    /**
     * 全局图片错误处理 - 替代 onerror 内联属性
     */
    function initImageErrorHandler() {
        document.addEventListener('error', function(e) {
            if (e.target.tagName === 'IMG') {
                const fallback = e.target.getAttribute('data-fallback');
                if (fallback && e.target.src !== fallback) {
                    e.target.src = fallback;
                }
            }
        }, true);
    }

    /**
     * Initialize on DOM ready
     */
    function init() {
        initEventListeners();
        initTheme();
        initViewMode();
        initLanguage();
        initImageErrorHandler();
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
     * Switch language - uses backend /set-language to set cookie then refreshes page
     * @param {string} lang - Language code (en, zh)
     */
    function switchLanguage(lang) {
        localStorage.setItem('app_language', lang);
        localStorage.setItem('bookrank_language', lang);

        // 同步 html lang，便于屏幕阅读器正确发音
        document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';

        if (typeof setGlobalLanguage === 'function') {
            setGlobalLanguage(lang);
        }

        const host = window.location.hostname;
        const cookieDomain = host.includes('.') ? host : '';
        document.cookie = 'lang=' + lang + '; path=/; max-age=31536000; SameSite=Lax; domain=' + cookieDomain;
    }

    /**
     * Apply generic translation for pages without custom translation logic
     * (Kept for backward compatibility with dynamic content)
     * @param {string} lang - Language code (en, zh)
     */
    function applyGenericTranslation(lang) {
        // Most static UI text is now handled by Flask-Babel server-side
        // This remains for any dynamic elements with data-zh/data-en attributes
        const translatableElements = document.querySelectorAll('[data-zh][data-en]');

        translatableElements.forEach(el => {
            el.textContent = lang === 'zh' ? el.getAttribute('data-zh') : el.getAttribute('data-en');
        });
    }

    /**
     * Initialize language based on saved preference or browser detection
     */
    function initLanguage() {
        var savedLang = localStorage.getItem('app_language') || localStorage.getItem('bookrank_language');
        var browserLang = navigator.language || navigator.userLanguage || '';
        var defaultLang = browserLang.startsWith('zh') ? 'zh' : 'en';
        var currentLang = savedLang || defaultLang;

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

    window.BookRank = Object.assign(window.BookRank || {}, {
        showLoading,
        hideLoading,
        showToast,
        toggleView,
        toggleFavorite,
        clearFilters,
        applyFilters,
        toggleTheme,
        toggleSidebar,
        switchLanguage,
        initLanguage
    });

    // Also expose as global functions for inline handlers
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.showToast = showToast;
    window.toggleView = toggleView;
    window.toggleFavorite = toggleFavorite;
    window.clearFilters = clearFilters;
    window.applyFilters = applyFilters;
    window.toggleTheme = toggleTheme;
    window.switchLanguage = switchLanguage;
    window.toggleLangMenu = toggleLangMenu;
    window.closeLangMenu = closeLangMenu;

    /**
     * 防御式主题颜色获取函数
     * 避免旧构建产物或外部脚本调用时因返回 undefined 而抛出 TypeError
     */
    window.getThemeColors = function() {
        const root = getComputedStyle(document.documentElement);
        return {
            exportedColors: {
                primary: root.getPropertyValue('--primary').trim() || '#171717',
                secondary: root.getPropertyValue('--secondary').trim() || '#525252',
                background: root.getPropertyValue('--background').trim() || '#ffffff',
                foreground: root.getPropertyValue('--foreground').trim() || '#171717',
                accent: root.getPropertyValue('--accent').trim() || '#dc2626'
            }
        };
    };

})();
