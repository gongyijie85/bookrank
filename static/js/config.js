/**
 * 应用配置
 */

export const CONFIG = {
    // API配置
    API_BASE_URL: '',
    
    // 分类配置
    CATEGORIES: {
        'hardcover-fiction': '精装小说',
        'hardcover-nonfiction': '精装非虚构',
        'trade-fiction-paperback': '平装小说',
        'paperback-nonfiction': '平装非虚构'
    },
    
    CATEGORY_ORDER: [
        'hardcover-fiction',
        'hardcover-nonfiction',
        'trade-fiction-paperback',
        'paperback-nonfiction'
    ],
    
    // 分页配置
    PAGINATION: {
        itemsPerPage: 20,
        maxVisiblePages: 5
    },
    
    // 重试配置
    RETRY: {
        maxRetries: 2,
        delay: 2000
    },
    
    // 防抖延迟
    DEBOUNCE_DELAY: 300,
    
    // 消息显示时间
    MESSAGE_DURATION: 3000
};
