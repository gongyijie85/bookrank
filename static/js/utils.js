/**
 * 工具函数模块
 */

/**
 * 生成会话ID
 * @returns {string} 会话ID
 */
export function generateSessionId() {
    return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

/**
 * 延迟函数
 * @param {number} ms - 延迟毫秒数
 * @returns {Promise<void>}
 */
export function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 重试包装器
 * @param {Function} fn - 要重试的函数
 * @param {number} maxRetries - 最大重试次数
 * @param {number} delayMs - 重试延迟
 * @returns {Function} 包装后的函数
 */
export function withRetry(fn, maxRetries = 2, delayMs = 2000) {
    return async function(...args) {
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                return await fn.apply(this, args);
            } catch (error) {
                if (attempt === maxRetries) {
                    throw error;
                }
                console.warn(`Attempt ${attempt + 1} failed, retrying in ${delayMs}ms...`);
                await delay(delayMs);
            }
        }
    };
}
