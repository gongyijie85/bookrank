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
     * Icon map for toast types
     */
    const iconMap = {
        success: 'fa-circle-check',
        error: 'fa-circle-exclamation',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info'
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
            <i class="fa-solid ${iconClass}" aria-hidden="true"></i>
            <span>${escapeHtml(message)}</span>
            <button class="toast-close" aria-label="关闭提示">
                <i class="fa-solid fa-times" aria-hidden="true"></i>
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
        const isDark = theme === 'dark';

        if (isDark) {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }

        // Update theme toggle button
        updateThemeToggleIcon(isDark);

        // Save preference
        localStorage.setItem('theme', theme);
    }

    /**
     * Update theme toggle button icon
     * @param {boolean} isDark - Whether dark theme is active
     */
    function updateThemeToggleIcon(isDark) {
        if (!themeToggle) return;

        const icon = themeToggle.querySelector('i');
        if (icon) {
            icon.className = isDark ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
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

        if (theme === 'dark') {
            applyTheme('dark');
        }

        // Add click listener to theme toggle
        if (themeToggle) {
            themeToggle.addEventListener('click', toggleTheme);
            themeToggle.setAttribute('aria-label', '切换主题');
        }
    }

    // ===== View Mode Functions =====

    /**
     * Toggle between grid and list view
     * @param {string} view - View mode (grid, list)
     */
    function toggleView(view) {
        const grid = document.getElementById('books-grid');
        const list = document.getElementById('books-list');
        const gridBtn = document.getElementById('view-grid');
        const listBtn = document.getElementById('view-list');

        if (!grid || !list) return;

        if (view === 'grid') {
            grid.style.display = 'grid';
            list.style.display = 'none';
            gridBtn?.classList.add('active');
            listBtn?.classList.remove('active');
            localStorage.setItem('viewMode', 'grid');
        } else {
            grid.style.display = 'none';
            list.style.display = 'flex';
            gridBtn?.classList.remove('active');
            listBtn?.classList.add('active');
            localStorage.setItem('viewMode', 'list');
        }
    }

    /**
     * Initialize view mode from saved preference
     */
    function initViewMode() {
        const savedView = localStorage.getItem('viewMode') || 'grid';
        toggleView(savedView);
    }

    // ===== Favorite Functions =====

    /**
     * Toggle favorite status for a book
     * @param {HTMLElement} button - Favorite button element
     * @param {string} bookId - Book ID
     */
    function toggleFavorite(button, bookId) {
        if (!button) return;

        const isActive = button.classList.toggle('active');
        const icon = button.querySelector('i');

        if (icon) {
            icon.className = isActive ? 'fa-solid fa-heart' : 'fa-regular fa-heart';
        }

        // Add heart beat animation
        button.classList.add('heart-beat');
        setTimeout(() => {
            button.classList.remove('heart-beat');
        }, 500);

        showToast(isActive ? '已添加到收藏' : '已取消收藏', 'success');

        // TODO: Save to backend
        console.log('Favorite toggled:', bookId, isActive);
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
     * Apply filters and reload page
     */
    function applyFilters() {
        const category = document.getElementById('category-select')?.value;
        const search = document.getElementById('search-input')?.value;

        showLoading('筛选中...');

        let url = window.location.pathname + '?';
        const params = new URLSearchParams();

        if (category) params.append('category', category);
        if (search) params.append('search', encodeURIComponent(search));

        window.location.href = url + params.toString();
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

        // Search input
        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    applyFilters();
                }
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
    }

    /**
     * Initialize on DOM ready
     */
    function init() {
        initEventListeners();
        initTheme();
        initViewMode();
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
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
        toggleSidebar
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

})();
