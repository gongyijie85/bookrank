/**
 * BookRank 翻译系统
 * 提供中英文 UI 文字切换功能
 */

const TRANSLATIONS = {
    zh: {
        // 导航
        'nav_home': '首页',
        'nav_awards': '获奖书单',
        'nav_publishers': '出版社',
        'nav_new_books': '新书速递',
        'nav_weekly': '畅销书周报',
        'nav_about': '关于我们',
        'sidebar_nav': '导航',
        'sidebar_about': '关于',
        'nav_bestsellers': '畅销书榜',
        'nav_publishers_guide': '出版社导航',
        'nav_home_brand': 'BookRank 首页',
        'main_nav': '主导航',
        'sidebar_nav_label': '侧边导航',
        // 语言/主题切换
        'lang_switch': '切换语言',
        'lang_select': '语言选择',
        'lang_zh': '简体中文',
        'lang_en': 'English',
        'lang_coming_soon': '更多语言即将支持',
        'theme_toggle': '切换主题',
        'toggle_theme': '切换明暗主题',
        'sidebar_toggle': '切换侧边栏',
        'skip_to_content': '跳转到主要内容',
        'notification_area': '通知提示',
        // 首页
        'page_title_bestsellers': '纽约时报畅销书排行榜',
        'filter_category': '图书分类',
        'filter_search': '搜索',
        'search_placeholder': '搜索书名或作者...',
        'search_clear': '清除搜索',
        'btn_search': '搜索',
        'btn_reset': '重置',
        'view_grid': '网格视图',
        'view_list': '列表视图',
        'view_switch': '视图切换',
        'view_grid_label': '切换到网格视图',
        'view_list_label': '切换到列表视图',
        'export_all': '导出全部',
        'export_options': '导出选项',
        'books_count': '共 {count} 本图书',
        'updated_at': '更新于',
        'cache_badge': '缓存数据',
        'filter_options': '筛选选项',
        'search_history': '搜索历史',
        // 通用
        'loading': '加载中...',
        'no_data': '暂无数据',
        'error_load': '加载失败',
        'theme_dark': '已切换到深色模式',
        'theme_light': '已切换到浅色模式',
        'close': '关闭',
        'close_toast': '关闭提示',
        // 书籍卡片
        'rank': '排名',
        'rank_prefix': '第',
        'rank_suffix': '名',
        'weeks_on_list': '上榜周数',
        'week_suffix': '周',
        'author': '作者',
        'publisher': '出版社',
        'description': '简介',
        'buy_links': '购买链接',
        'favorite_add': '已添加到收藏',
        'favorite_remove': '已取消收藏',
        'cover': '封面',
        'new_entry': '新书上榜',
        'rank_up': '排名上升',
        'rank_down': '排名下降',
        'page_suffix': '页',
        'language_label': '语言',
        'isbn_label': 'ISBN',
        'pages_label': '页数',
        'publisher_label': '出版社',
        'default_category': '虚构类',
        // 周报
        'weekly_report': '畅销书周报',
        'report_summary': '周报摘要',
        'top_changes': '重要变化',
        'new_books_list': '新上榜书籍',
        'top_risers': '排名上升最快',
        'longest_running': '持续上榜最久',
        'featured_books': '推荐书籍',
        // 页脚/关于
        'about_title': '关于 BookRank',
        'about_intro': '项目介绍',
        'data_sources': '数据来源',
        'tech_stack': '技术栈',
        'contact_us': '联系我们',
        'disclaimer': '免责声明',
        // 图书网格/列表视图
        'books_grid_view': '图书网格视图',
        'books_list_view': '图书列表视图',
    },
    en: {
        // Navigation
        'nav_home': 'Home',
        'nav_awards': 'Awards',
        'nav_publishers': 'Publishers',
        'nav_new_books': 'New Books',
        'nav_weekly': 'Weekly Reports',
        'nav_about': 'About',
        'sidebar_nav': 'Navigation',
        'sidebar_about': 'About',
        'nav_bestsellers': 'Bestsellers',
        'nav_publishers_guide': 'Publishers Guide',
        'nav_home_brand': 'BookRank Home',
        'main_nav': 'Main Navigation',
        'sidebar_nav_label': 'Sidebar Navigation',
        // Language/Theme toggle
        'lang_switch': 'Switch Language',
        'lang_select': 'Language Selection',
        'lang_zh': '简体中文',
        'lang_en': 'English',
        'lang_coming_soon': 'More languages coming soon',
        'theme_toggle': 'Toggle Theme',
        'toggle_theme': 'Toggle Dark/Light Theme',
        'sidebar_toggle': 'Toggle Sidebar',
        'skip_to_content': 'Skip to main content',
        'notification_area': 'Notifications',
        // Home
        'page_title_bestsellers': 'NYT Bestsellers',
        'filter_category': 'Category',
        'filter_search': 'Search',
        'search_placeholder': 'Search title or author...',
        'search_clear': 'Clear search',
        'btn_search': 'Search',
        'btn_reset': 'Reset',
        'view_grid': 'Grid View',
        'view_list': 'List View',
        'view_switch': 'View Toggle',
        'view_grid_label': 'Switch to grid view',
        'view_list_label': 'Switch to list view',
        'export_all': 'Export All',
        'export_options': 'Export Options',
        'books_count': '{count} books total',
        'updated_at': 'Updated at',
        'cache_badge': 'Cached',
        'filter_options': 'Filter Options',
        'search_history': 'Search History',
        // Common
        'loading': 'Loading...',
        'no_data': 'No data',
        'error_load': 'Failed to load',
        'theme_dark': 'Switched to dark mode',
        'theme_light': 'Switched to light mode',
        'close': 'Close',
        'close_toast': 'Close notification',
        // Book card
        'rank': 'Rank',
        'rank_prefix': '#',
        'rank_suffix': '',
        'weeks_on_list': 'Weeks on List',
        'week_suffix': ' weeks',
        'author': 'Author',
        'publisher': 'Publisher',
        'description': 'Description',
        'buy_links': 'Buy Links',
        'favorite_add': 'Added to favorites',
        'favorite_remove': 'Removed from favorites',
        'cover': 'Cover',
        'new_entry': 'New',
        'rank_up': 'Rank up',
        'rank_down': 'Rank down',
        'page_suffix': ' pages',
        'language_label': 'Language',
        'isbn_label': 'ISBN',
        'pages_label': 'Pages',
        'publisher_label': 'Publisher',
        'default_category': 'Fiction',
        // Weekly
        'weekly_report': 'Weekly Report',
        'report_summary': 'Summary',
        'top_changes': 'Top Changes',
        'new_books_list': 'New on List',
        'top_risers': 'Top Risers',
        'longest_running': 'Longest Running',
        'featured_books': 'Featured',
        // About
        'about_title': 'About BookRank',
        'about_intro': 'Introduction',
        'data_sources': 'Data Sources',
        'tech_stack': 'Tech Stack',
        'contact_us': 'Contact Us',
        'disclaimer': 'Disclaimer',
        // Books grid/list view
        'books_grid_view': 'Books Grid View',
        'books_list_view': 'Books List View',
    }
};

/**
 * 获取翻译文本
 * @param {string} key - 翻译键
 * @param {string} lang - 语言代码
 * @param {Object} params - 插值参数
 * @returns {string} 翻译后的文本
 */
function t(key, lang = null, params = {}) {
    const currentLang = lang || localStorage.getItem('app_language') || 'zh';
    const dict = TRANSLATIONS[currentLang] || TRANSLATIONS['zh'];
    let text = dict[key] || TRANSLATIONS['zh'][key] || key;

    // 简单的插值替换 {count}
    Object.keys(params).forEach(param => {
        text = text.replace(`{${param}}`, params[param]);
    });

    return text;
}

/**
 * 应用页面翻译
 * 查找所有带有 data-i18n 属性的元素并替换文本
 * @param {string} lang - 目标语言
 */
function applyPageTranslation(lang) {
    // 翻译所有带 data-i18n 属性的元素
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const translated = t(key, lang);
        if (translated !== key) {
            // 保留子元素（如图标），只替换文本节点
            const textNode = Array.from(el.childNodes).find(
                n => n.nodeType === Node.TEXT_NODE && n.textContent.trim()
            );
            if (textNode) {
                textNode.textContent = translated;
            } else if (!el.querySelector('svg, img, i')) {
                el.textContent = translated;
            } else {
                // 有图标时，找到第一个文本节点替换
                for (let i = 0; i < el.childNodes.length; i++) {
                    if (el.childNodes[i].nodeType === Node.TEXT_NODE) {
                        el.childNodes[i].textContent = translated;
                        break;
                    }
                }
            }
        }
    });

    // 翻译 placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key, lang);
    });

    // 翻译 title 属性
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        el.title = t(key, lang);
    });

    // 翻译 aria-label 属性
    document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
        const key = el.getAttribute('data-i18n-aria-label');
        el.setAttribute('aria-label', t(key, lang));
    });

    // 更新页面标题（如果 html 有 data-i18n-title）
    const pageTitleEl = document.querySelector('title[data-i18n]');
    if (pageTitleEl) {
        pageTitleEl.textContent = t(pageTitleEl.getAttribute('data-i18n'), lang);
    }
}

/**
 * 切换全局语言
 * @param {string} lang - 语言代码 'zh' 或 'en'
 */
function setGlobalLanguage(lang) {
    if (!['zh', 'en'].includes(lang)) return;

    localStorage.setItem('app_language', lang);
    localStorage.setItem('bookrank_language', lang);

    if (typeof updateLangDropdown === 'function') {
        updateLangDropdown(lang);
    }

    applyPageTranslation(lang);

    if (typeof BookI18n !== 'undefined' && BookI18n.size() > 0) {
        BookI18n.applyLanguage(lang);
    }

    window.dispatchEvent(new CustomEvent('languagechange', { detail: { language: lang } }));

    const langName = lang === 'zh' ? '简体中文' : 'English';
    if (typeof showToast === 'function') {
        showToast(`已切换到 ${langName}`, 'success');
    }
}

// 暴露到全局
window.TRANSLATIONS = TRANSLATIONS;
window.t = t;
window.applyPageTranslation = applyPageTranslation;
window.setGlobalLanguage = setGlobalLanguage;