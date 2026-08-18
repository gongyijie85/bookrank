/**
 * API客户端模块
 */

import { generateSessionId } from './utils.js';

/**
 * API客户端类
 */
class ApiClient {
    constructor() {
        this.sessionId = this._getOrCreateSessionId();
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
        const url = new URL(endpoint, window.location.origin);
        url.searchParams.append('session_id', this.sessionId);

        const response = await fetch(url.toString(), {
            ...options,
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
    }

    /**
     * 翻译文本
     * @param {string} text - 要翻译的文本
     * @param {string} sourceLang - 源语言（默认：en）
     * @param {string} targetLang - 目标语言（默认：zh）
     * @returns {Promise<Object>} 翻译结果
     */
    async translateText(text, sourceLang = 'en', targetLang = 'zh', fieldType = 'text') {
        return this.request('/api/translate', {
            method: 'POST',
            body: JSON.stringify({
                text: text,
                source_lang: sourceLang,
                target_lang: targetLang,
                field_type: fieldType
            })
        });
    }

    /**
     * 合并翻译一本书的多个字段（单次API调用）
     * @param {Object} fields - 待翻译字段 { title, description, details }
     * @param {string} sourceLang - 源语言
     * @param {string} targetLang - 目标语言
     * @returns {Promise<Object>} 翻译结果 { title_zh, description_zh, details_zh }
     */
    async translateBookFields(fields, sourceLang = 'en', targetLang = 'zh') {
        return this.request('/api/translate/book-fields', {
            method: 'POST',
            body: JSON.stringify({
                title: fields.title || '',
                description: fields.description || '',
                details: fields.details || '',
                source_lang: sourceLang,
                target_lang: targetLang
            })
        });
    }
}

// 导出单例
export const api = new ApiClient();
