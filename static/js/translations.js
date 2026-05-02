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
        // 首页
        'page_title_bestsellers': '纽约时报畅销书排行榜',
        'filter_category': '图书分类',
        'filter_search': '搜索',
        'search_placeholder': '搜索书名或作者...',
        'btn_search': '搜索',
        'btn_reset': '重置',
        'view_grid': '网格视图',
        'view_list': '列表视图',
        'export_all': '导出全部',
        'books_count': '共 {count} 本图书',
        'updated_at': '更新于',
        'cache_badge': '缓存数据',
        // 通用
        'loading': '加载中...',
        'no_data': '暂无数据',
        'error_load': '加载失败',
        'theme_dark': '已切换到深色模式',
        'theme_light': '已切换到浅色模式',
        'lang_zh': '简体中文',
        'lang_en': 'English',
        // 书籍卡片
        'rank': '排名',
        'weeks_on_list': '上榜周数',
        'author': '作者',
        'publisher': '出版社',
        'description': '简介',
        'buy_links': '购买链接',
        'favorite_add': '已添加到收藏',
        'favorite_remove': '已取消收藏',
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
        // Home
        'page_title_bestsellers': 'NYT Bestsellers',
        'filter_category': 'Category',
        'filter_search': 'Search',
        'search_placeholder': 'Search title or author...',
        'btn_search': 'Search',
        'btn_reset': 'Reset',
        'view_grid': 'Grid View',
        'view_list': 'List View',
        'export_all': 'Export All',
        'books_count': '{count} books total',
        'updated_at': 'Updated at',
        'cache_badge': 'Cached',
        // Common
        'loading': 'Loading...',
        'no_data': 'No data',
        'error_load': 'Failed to load',
        'theme_dark': 'Switched to dark mode',
        'theme_light': 'Switched to light mode',
        'lang_zh': '简体中文',
        'lang_en': 'English',
        // Book card
        'rank': 'Rank',
        'weeks_on_list': 'Weeks on List',
        'author': 'Author',
        'publisher': 'Publisher',
        'description': 'Description',
        'buy_links': 'Buy Links',
        'favorite_add': 'Added to favorites',
        'favorite_remove': 'Removed from favorites',
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

    // 更新下拉菜单 UI
    if (typeof updateLangDropdown === 'function') {
        updateLangDropdown(lang);
    }

    // 应用页面翻译
    applyPageTranslation(lang);

    // 触发语言切换事件，供各页面监听
    window.dispatchEvent(new CustomEvent('languagechange', { detail: { language: lang } }));

    // 显示提示
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