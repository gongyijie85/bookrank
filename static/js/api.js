/**
 * API客户端模块
 */

import { CONFIG } from './config.js';
import { generateSessionId, withRetry } from './utils.js';

/**
 * API客户端类
 */
class ApiClient {
    constructor() {
        this.baseUrl = CONFIG.API_BASE_URL;
        this.sessionId = this._getOrCreateSessionId();
        this.abortController = null;
    }
    
    /**
     * 获取或创建会话ID
     * @returns {string} 会话ID
     */
    _getOrCreateSessionId() {
        let sessionId = localStorage.getItem('session_id');
        if (!sessionId) {
            sessionId = generateSessionId();
            localStorage.setItem('session_id', sessionId);
        }
        return sessionId;
    }
    
    /**
     * 发送请求
     * @param {string} endpoint - API端点
     * @param {Object} options - 请求选项
     * @returns {Promise<Object>} 响应数据
     */
    async request(endpoint, options = {}) {
        // 取消之前的请求
        if (this.abortController) {
            this.abortController.abort();
        }
        this.abortController = new AbortController();
        
        const url = new URL(endpoint, window.location.origin);
        url.searchParams.append('session_id', this.sessionId);
        
        try {
            const response = await fetch(url.toString(), {
                ...options,
                signal: this.abortController.signal,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({
                    message: `HTTP error: ${response.status}`
                }));
                throw new Error(error.message || `HTTP error: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('Request cancelled');
            }
            throw error;
        }
    }
    
    /**
     * 获取图书列表
     * @param {string} category - 分类ID或'all'
     * @returns {Promise<Object>} 图书数据
     */
    async getBooks(category) {
        const fetchFn = withRetry(
            () => this.request(`/api/books/${category}`),
            CONFIG.RETRY.maxRetries,
            CONFIG.RETRY.delay
        );
        return fetchFn();
    }
    
    /**
     * 搜索图书
     * @param {string} keyword - 搜索关键词
     * @returns {Promise<Object>} 搜索结果
     */
    async searchBooks(keyword) {
        const fetchFn = withRetry(
            () => this.request(`/api/search?keyword=${encodeURIComponent(keyword)}`),
            CONFIG.RETRY.maxRetries,
            CONFIG.RETRY.delay
        );
        return fetchFn();
    }
    
    /**
     * 获取搜索历史
     * @param {number} limit - 返回数量限制
     * @returns {Promise<Object>} 搜索历史
     */
    async getSearchHistory(limit = 5) {
        return this.request(`/api/search/history?limit=${limit}`);
    }
    
    /**
     * 获取用户偏好
     * @returns {Promise<Object>} 用户偏好
     */
    async getUserPreferences() {
        return this.request('/api/user/preferences');
    }
    
    /**
     * 保存用户偏好
     * @param {Object} preferences - 偏好设置
     * @returns {Promise<Object>} 响应
     */
    async saveUserPreferences(preferences) {
        return this.request('/api/user/preferences', {
            method: 'POST',
            body: JSON.stringify(preferences)
        });
    }
    
    /**
     * 导出CSV
     * @param {string} category - 分类ID或'all'
     */
    exportCSV(category) {
        const url = `/api/export/${category}?session_id=${this.sessionId}`;
        window.location.href = url;
    }

    /**
     * 翻译文本
     * @param {string} text - 要翻译的文本
     * @param {string} sourceLang - 源语言（默认：en）
     * @param {string} targetLang - 目标语言（默认：zh）
     * @returns {Promise<Object>} 翻译结果
     */
    async translateText(text, sourceLang = 'en', targetLang = 'zh') {
        return this.request('/api/translate', {
            method: 'POST',
            body: JSON.stringify({
                text: text,
                source_lang: sourceLang,
                target_lang: targetLang
            })
        });
    }

    /**
     * 翻译图书信息
     * @param {string} isbn - 图书ISBN
     * @returns {Promise<Object>} 翻译结果
     */
    async translateBook(isbn) {
        return this.request(`/api/translate/book/${isbn}`, {
            method: 'POST'
        });
    }

    /**
     * 获取翻译服务状态
     * @returns {Promise<Object>} 服务状态
     */
    async getTranslationStatus() {
        return this.request('/api/translate/cache/stats');
    }
}

// 导出单例
export const api = new ApiClient();
