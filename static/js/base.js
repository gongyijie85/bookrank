(function() {
    'use strict';
    
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
        
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024 && 
                !sidebar.contains(e.target) && 
                !sidebarToggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }
    
    function showLoading(text = '加载中...') {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.querySelector('.loading-text').textContent = text;
            overlay.style.display = 'flex';
        }
    }
    
    function hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    function showToast(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const iconMap = {
            'success': 'fa-circle-check',
            'error': 'fa-circle-exclamation',
            'warning': 'fa-triangle-exclamation',
            'info': 'fa-circle-info'
        };
        
        toast.innerHTML = `
            <i class="fa-solid ${iconMap[type] ?? iconMap.info}"></i>
            <span>${message}</span>
        `;
        
        container.appendChild(toast);
        
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    }
    
    function showAboutModal() {
        showToast('BookRank - 图书排行榜与获奖书单平台', 'info', 5000);
    }
    
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
    
    function toggleFavorite(button, bookId) {
        button.classList.toggle('active');
        const isActive = button.classList.contains('active');
        button.innerHTML = `<i class="fa-solid fa-heart${isActive ? '' : '-o'}"></i>`;
        
        button.classList.add('heart-beat');
        setTimeout(() => {
            button.classList.remove('heart-beat');
        }, 500);
        
        showToast(isActive ? '已添加到收藏' : '已取消收藏', 'success');
    }
    
    function clearFilters() {
        showLoading('重置中...');
        window.location.href = window.location.pathname;
    }
    
    function applyFilters() {
        console.log('applyFilters not implemented');
    }
    
    function toggleTheme() {
        const html = document.documentElement;
        const isDark = html.classList.toggle('dark-theme');
        
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            const icon = themeToggle.querySelector('i');
            if (isDark) {
                icon.className = 'fa-solid fa-sun';
            } else {
                icon.className = 'fa-solid fa-moon';
            }
        }
        
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        showToast(isDark ? '已切换到深色模式' : '已切换到浅色模式', 'success');
    }
    
    function initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        const isDark = savedTheme === 'dark';
        
        if (isDark) {
            document.documentElement.classList.add('dark-theme');
        }
        
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            const icon = themeToggle.querySelector('i');
            if (isDark) {
                icon.className = 'fa-solid fa-sun';
            }
            
            themeToggle.addEventListener('click', toggleTheme);
        }
    }
    
    document.addEventListener('DOMContentLoaded', () => {
        const savedView = localStorage.getItem('viewMode') || 'grid';
        toggleView(savedView);
        
        initTheme();
        
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    applyFilters();
                }
            });
        }
    });
    
    window.BookRank = {
        showLoading,
        hideLoading,
        showToast,
        showAboutModal,
        toggleView,
        toggleFavorite,
        clearFilters,
        applyFilters,
        toggleTheme,
        initTheme
    };
    
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.showToast = showToast;
    window.showAboutModal = showAboutModal;
    window.toggleView = toggleView;
    window.toggleFavorite = toggleFavorite;
    window.clearFilters = clearFilters;
    window.applyFilters = applyFilters;
    window.toggleTheme = toggleTheme;
    window.initTheme = initTheme;
})();
