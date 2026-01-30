/**
 * 主应用模块
 */

import { CONFIG } from './config.js';
import { api } from './api.js';
import { store, actions, selectors } from './store.js';
import { BookCard, BookDetailModal, MessageToast, LoadingIndicator, SearchSuggestions } from './components.js';
import { debounce, appendElements } from './utils.js';

/**
 * 图书应用类
 */
class BookApp {
    constructor() {
        this.dom = {};
        this.modal = null;
        this.toast = null;
        this.loader = null;
        this.searchSuggestions = null;
        
        this._init();
    }
    
    /**
     * 初始化应用
     */
    _init() {
        this._cacheDOM();
        this._initComponents();
        this._bindEvents();
        this._subscribeToStore();
        this._loadInitialData();
    }
    
    /**
     * 缓存DOM元素引用
     */
    _cacheDOM() {
        this.dom = {
            listTypeSelect: document.getElementById('listType'),
            fetchButton: document.getElementById('fetchBooks'),
            exportButton: document.getElementById('exportBooks'),
            searchInput: document.getElementById('searchInput'),
            searchButton: document.getElementById('searchBtn'),
            toggleViewButton: document.getElementById('toggleView'),
            toggleLangButton: document.getElementById('toggleLang'),
            langText: document.getElementById('langText'),
            booksContainer: document.getElementById('booksContainer'),
            loader: document.getElementById('loader'),
            errorDiv: document.getElementById('error'),
            infoDiv: document.getElementById('info'),
            lastUpdateElement: document.getElementById('lastUpdate')
        };
        
        // 初始化语言设置
        this.currentLang = localStorage.getItem('app_language') || 'zh';
        this._updateLanguageUI();
    }
    
    /**
     * 初始化组件
     */
    _initComponents() {
        this.modal = new BookDetailModal();
        this.toast = new MessageToast();
        this.loader = new LoadingIndicator();
        this.searchSuggestions = new SearchSuggestions(
            this.dom.searchInput,
            (keyword) => this._handleSearch(keyword)
        );
    }
    
    /**
     * 绑定事件
     */
    _bindEvents() {
        // 加载图书
        this.dom.fetchButton.addEventListener('click', () => {
            const category = this.dom.listTypeSelect.value;
            this._loadBooks(category);
        });
        
        // 导出CSV
        this.dom.exportButton.addEventListener('click', () => {
            const category = this.dom.listTypeSelect.value;
            api.exportCSV(category);
        });
        
        // 搜索
        this.dom.searchButton.addEventListener('click', () => {
            const keyword = this.dom.searchInput.value.trim();
            if (keyword) {
                this._handleSearch(keyword);
            }
        });
        
        // 搜索输入（防抖）
        this.dom.searchInput.addEventListener('input', 
            debounce(() => this._loadSearchSuggestions(), CONFIG.DEBOUNCE_DELAY)
        );
        
        // 搜索框回车
        this.dom.searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const keyword = this.dom.searchInput.value.trim();
                if (keyword) {
                    this._handleSearch(keyword);
                }
            }
        });
        
        // 搜索框聚焦
        this.dom.searchInput.addEventListener('focus', () => {
            this._loadSearchSuggestions();
        });
        
        // 切换视图
        this.dom.toggleViewButton.addEventListener('click', () => {
            actions.toggleView();
        });
        
        // 切换语言
        this.dom.toggleLangButton.addEventListener('click', () => {
            this._toggleLanguage();
        });
        
        // 图书卡片点击（事件委托）
        this.dom.booksContainer.addEventListener('book:click', (e) => {
            this.modal.show(e.detail.book);
        });
        
        // 分类切换（事件委托）
        this.dom.booksContainer.addEventListener('click', (e) => {
            if (e.target.matches('.category-toggle')) {
                const category = e.target.dataset.category;
                const grid = document.getElementById(`books-${category}`);
                if (grid) {
                    const isHidden = grid.style.display === 'none';
                    grid.style.display = isHidden ? 'grid' : 'none';
                    e.target.textContent = isHidden ? '收起' : '展开';
                }
            }
        });
    }
    
    /**
     * 订阅状态变化
     */
    _subscribeToStore() {
        store.subscribe((state) => {
            // 更新视图模式
            this._updateViewMode(state.currentView);
            
            // 更新加载状态
            this._updateLoadingState(state.isLoading);
            
            // 更新错误信息
            this._updateError(state.error);
            
            // 更新消息
            this._updateMessage(state.message);
            
            // 更新时间
            if (state.latestUpdate) {
                this.dom.lastUpdateElement.textContent = state.latestUpdate;
            }
        });
    }
    
    /**
     * 加载初始数据
     */
    async _loadInitialData() {
        try {
            // 加载用户偏好
            const prefsResponse = await api.getUserPreferences();
            if (prefsResponse.success && prefsResponse.data.preferences) {
                actions.setPreferences(prefsResponse.data.preferences);
            }
            
            // 加载默认分类
            await this._loadBooks('all');
            
        } catch (error) {
            console.error('Failed to load initial data:', error);
        }
    }
    
    /**
     * 加载图书
     * @param {string} category - 分类ID
     */
    async _loadBooks(category) {
        actions.setLoading(true);
        actions.setError(null);
        
        try {
            const response = await api.getBooks(category);
            
            if (!response.success) {
                throw new Error(response.message || 'Failed to load books');
            }
            
            actions.setLatestUpdate(response.data.latest_update);
            
            if (category === 'all') {
                actions.setAllBooks(response.data.books);
                this._renderAllCategories(response.data.books);
            } else {
                actions.setBooks(category, response.data.books);
                this._renderBooks(response.data.books, response.data.category_name);
            }
            
        } catch (error) {
            console.error('Failed to load books:', error);
            actions.setError(error.message);
        } finally {
            actions.setLoading(false);
        }
    }
    
    /**
     * 处理搜索
     * @param {string} keyword - 搜索关键词
     */
    async _handleSearch(keyword) {
        actions.setLoading(true);
        actions.setError(null);
        this.dom.searchInput.value = keyword;
        
        try {
            const response = await api.searchBooks(keyword);
            
            if (!response.success) {
                throw new Error(response.message || 'Search failed');
            }
            
            actions.setSearchResults(keyword, response.data.books);
            actions.setLatestUpdate(response.data.latest_update);
            
            this._renderSearchResults(response.data.books, keyword, response.data.count);
            
        } catch (error) {
            console.error('Search failed:', error);
            actions.setError(error.message);
        } finally {
            actions.setLoading(false);
        }
    }
    
    /**
     * 加载搜索建议
     */
    async _loadSearchSuggestions() {
        try {
            const response = await api.getSearchHistory(5);
            if (response.success) {
                actions.setSearchHistory(response.data.history);
                this.searchSuggestions.show(response.data.history);
            }
        } catch (error) {
            console.error('Failed to load search history:', error);
        }
    }
    
    /**
     * 渲染所有分类
     * @param {Object} booksByCategory - 分类图书映射
     */
    _renderAllCategories(booksByCategory) {
        this.dom.booksContainer.innerHTML = '';
        
        const fragment = document.createDocumentFragment();
        
        CONFIG.CATEGORY_ORDER.forEach(catId => {
            const books = booksByCategory[catId] || [];
            if (books.length === 0) return;
            
            const categoryName = CONFIG.CATEGORIES[catId];
            const section = this._createCategorySection(catId, categoryName, books);
            fragment.appendChild(section);
        });
        
        this.dom.booksContainer.appendChild(fragment);
    }
    
    /**
     * 创建分类区块
     * @param {string} catId - 分类ID
     * @param {string} categoryName - 分类名称
     * @param {Array} books - 图书数组
     * @returns {HTMLElement} 分类区块元素
     */
    _createCategorySection(catId, categoryName, books) {
        const section = document.createElement('div');
        section.className = 'category-section';
        
        const header = document.createElement('div');
        header.className = 'category-title';
        header.innerHTML = `
            <span>${categoryName} (${books.length}本)</span>
            <button class="category-toggle" data-category="${catId}">收起</button>
        `;
        
        const grid = document.createElement('div');
        grid.className = 'books-container';
        grid.id = `books-${catId}`;
        
        const cards = books.map(book => new BookCard(book).render());
        appendElements(grid, cards);
        
        section.appendChild(header);
        section.appendChild(grid);
        
        return section;
    }
    
    /**
     * 渲染图书列表
     * @param {Array} books - 图书数组
     * @param {string} categoryName - 分类名称
     */
    _renderBooks(books, categoryName) {
        this.dom.booksContainer.innerHTML = '';
        
        if (books.length === 0) {
            actions.setMessage('该分类暂无数据');
            return;
        }
        
        const title = document.createElement('h2');
        title.className = 'category-title';
        title.textContent = categoryName;
        
        const grid = document.createElement('div');
        grid.className = 'books-container';
        
        const cards = books.map(book => new BookCard(book).render());
        appendElements(grid, cards);
        
        this.dom.booksContainer.appendChild(title);
        this.dom.booksContainer.appendChild(grid);
    }
    
    /**
     * 渲染搜索结果
     * @param {Array} books - 搜索结果
     * @param {string} keyword - 搜索关键词
     * @param {number} count - 结果数量
     */
    _renderSearchResults(books, keyword, count) {
        this.dom.booksContainer.innerHTML = '';
        
        if (books.length === 0) {
            actions.setMessage(`没有找到包含"${keyword}"的图书`);
            return;
        }
        
        const title = document.createElement('h2');
        title.className = 'category-title';
        title.textContent = `搜索"${keyword}"的结果 (${count}本)`;
        
        const grid = document.createElement('div');
        grid.className = 'books-container';
        
        const cards = books.map(book => new BookCard(book).render());
        appendElements(grid, cards);
        
        this.dom.booksContainer.appendChild(title);
        this.dom.booksContainer.appendChild(grid);
    }
    
    /**
     * 更新视图模式
     * @param {string} viewMode - 视图模式
     */
    _updateViewMode(viewMode) {
        this.dom.booksContainer.className = viewMode === 'grid' ? 'grid-view' : 'list-view';
        this.dom.toggleViewButton.innerHTML = viewMode === 'grid'
            ? '<i class="fa fa-th-list"></i> 列表视图'
            : '<i class="fa fa-th-large"></i> 网格视图';
    }
    
    /**
     * 更新加载状态
     * @param {boolean} isLoading - 是否加载中
     */
    _updateLoadingState(isLoading) {
        if (isLoading) {
            this.dom.loader.style.display = 'block';
            this.dom.fetchButton.disabled = true;
            this.dom.fetchButton.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 加载中...';
        } else {
            this.dom.loader.style.display = 'none';
            this.dom.fetchButton.disabled = false;
            this.dom.fetchButton.innerHTML = '<i class="fa fa-refresh"></i> 加载图书';
        }
    }
    
    /**
     * 更新错误信息
     * @param {string|null} error - 错误信息
     */
    _updateError(error) {
        if (error) {
            this.dom.errorDiv.textContent = error;
            this.dom.errorDiv.style.display = 'block';
            this.toast.show(error, 'error');
        } else {
            this.dom.errorDiv.style.display = 'none';
        }
    }
    
    /**
     * 更新消息
     * @param {string|null} message - 消息内容
     */
    _updateMessage(message) {
        if (message) {
            this.dom.infoDiv.textContent = message;
            this.dom.infoDiv.style.display = 'block';
            this.toast.show(message, 'info');
        } else {
            this.dom.infoDiv.style.display = 'none';
        }
    }
    
    /**
     * 切换语言
     */
    _toggleLanguage() {
        this.currentLang = this.currentLang === 'zh' ? 'en' : 'zh';
        localStorage.setItem('app_language', this.currentLang);
        this._updateLanguageUI();
        
        // 刷新当前显示的图书
        const currentCategory = this.dom.listTypeSelect.value;
        if (currentCategory) {
            this._loadBooks(currentCategory);
        }
        
        // 显示提示
        const langName = this.currentLang === 'zh' ? '中文' : 'English';
        this.toast.show(`已切换到${langName}`, 'success');
    }
    
    /**
     * 更新语言UI
     */
    _updateLanguageUI() {
        if (this.dom.langText) {
            this.dom.langText.textContent = this.currentLang === 'zh' ? '中文' : 'EN';
        }
        if (this.dom.toggleLangButton) {
            this.dom.toggleLangButton.classList.toggle('active', this.currentLang === 'en');
        }
    }
    
    /**
     * 获取当前语言
     * @returns {string} 当前语言代码
     */
    getCurrentLanguage() {
        return this.currentLang;
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new BookApp();
});

// 注册Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(registration => {
                console.log('SW registered:', registration);
            })
            .catch(error => {
                console.log('SW registration failed:', error);
            });
    });
}
