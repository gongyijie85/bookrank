/**
 * 状态管理模块
 */

import { CONFIG } from './config.js';

/**
 * 简单的状态存储类
 */
class Store {
    constructor(initialState = {}) {
        this.state = { ...initialState };
        this.listeners = new Set();
    }
    
    /**
     * 获取当前状态
     * @returns {Object} 当前状态
     */
    getState() {
        return { ...this.state };
    }
    
    /**
     * 更新状态
     * @param {Object|Function} updater - 更新对象或更新函数
     */
    setState(updater) {
        const newState = typeof updater === 'function'
            ? updater(this.state)
            : { ...this.state, ...updater };
        
        this.state = newState;
        this._notify();
    }
    
    /**
     * 订阅状态变化
     * @param {Function} listener - 监听器函数
     * @returns {Function} 取消订阅函数
     */
    subscribe(listener) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }
    
    /**
     * 通知所有监听器
     */
    _notify() {
        this.listeners.forEach(listener => listener(this.state));
    }
}

// 创建应用状态
export const store = new Store({
    // 视图状态
    currentView: 'grid', // 'grid' | 'list'
    currentCategory: 'all',
    
    // 数据状态
    books: {},
    searchResults: [],
    searchKeyword: '',
    
    // UI状态
    isLoading: false,
    error: null,
    message: null,
    
    // 用户状态
    sessionId: null,
    preferences: {},
    searchHistory: [],
    
    // 语言设置
    language: localStorage.getItem('app_language') || 'zh',
    
    // 元数据
    categories: CONFIG.CATEGORIES,
    latestUpdate: null
});

/**
 * 状态选择器
 */
export const selectors = {
    getBooksByCategory: (categoryId) => {
        const state = store.getState();
        return state.books[categoryId] || [];
    },
    
    getAllBooks: () => {
        const state = store.getState();
        return Object.values(state.books).flat();
    },
    
    getBookById: (id) => {
        const state = store.getState();
        for (const categoryBooks of Object.values(state.books)) {
            const book = categoryBooks.find(b => b.id === id);
            if (book) return book;
        }
        return null;
    },
    
    isLoading: () => store.getState().isLoading,
    
    getError: () => store.getState().error,
    
    getMessage: () => store.getState().message
};

/**
 * 状态操作
 */
export const actions = {
    /**
     * 设置加载状态
     * @param {boolean} isLoading - 是否加载中
     */
    setLoading(isLoading) {
        store.setState({ isLoading });
    },
    
    /**
     * 设置错误信息
     * @param {string|null} error - 错误信息
     */
    setError(error) {
        store.setState({ error });
    },
    
    /**
     * 设置消息
     * @param {string|null} message - 消息内容
     */
    setMessage(message) {
        store.setState({ message });
        
        // 自动清除消息
        if (message) {
            setTimeout(() => {
                store.setState({ message: null });
            }, CONFIG.MESSAGE_DURATION);
        }
    },
    
    /**
     * 设置图书数据
     * @param {string} categoryId - 分类ID
     * @param {Array} books - 图书数组
     */
    setBooks(categoryId, books) {
        store.setState(state => ({
            books: {
                ...state.books,
                [categoryId]: books
            }
        }));
    },
    
    /**
     * 设置所有分类的图书
     * @param {Object} books - 分类图书映射
     */
    setAllBooks(books) {
        store.setState({ books });
    },
    
    /**
     * 设置搜索结果
     * @param {string} keyword - 搜索关键词
     * @param {Array} results - 搜索结果
     */
    setSearchResults(keyword, results) {
        store.setState({
            searchKeyword: keyword,
            searchResults: results
        });
    },
    
    /**
     * 切换视图模式
     */
    toggleView() {
        store.setState(state => ({
            currentView: state.currentView === 'grid' ? 'list' : 'grid'
        }));
    },
    
    /**
     * 设置当前分类
     * @param {string} category - 分类ID
     */
    setCategory(category) {
        store.setState({ currentCategory: category });
    },
    
    /**
     * 设置用户偏好
     * @param {Object} preferences - 偏好设置
     */
    setPreferences(preferences) {
        store.setState({ preferences });
        
        // 应用偏好
        if (preferences.view_mode) {
            store.setState({ currentView: preferences.view_mode });
        }
    },
    
    /**
     * 设置搜索历史
     * @param {Array} history - 搜索历史
     */
    setSearchHistory(history) {
        store.setState({ searchHistory: history });
    },
    
    /**
     * 设置最后更新时间
     * @param {string} latestUpdate - 更新时间字符串
     */
    setLatestUpdate(latestUpdate) {
        store.setState({ latestUpdate });
    }
};
