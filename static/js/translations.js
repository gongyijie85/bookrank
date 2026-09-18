/**
 * 翻译系统
 * 提供中英文 UI 文字切换功能
 *
 * 注意：分类中英映射表（CATEGORY_LABELS / getCategoryLabel）
 * 已抽到 categories.js 共享模块。必须在 translations.js 之前加载。
 */

const TRANSLATIONS = {
    zh: {
        // 导航
        'nav_home': '首页',
        'nav_awards': '获奖书单',
        'nav_publishers': '出版社',
        'nav_rankings': '更多榜单',
        'nav_new_books': '新书速递',
        'nav_weekly': '畅销书周报',
        'nav_about': '关于我们',
        'sidebar_nav': '导航',
        'sidebar_about': '关于',
        'nav_bestsellers': '畅销书榜',
        'nav_publishers_guide': '出版社导航',
        'nav_profile': '个人中心',
        'nav_home_brand': 'BookRank 首页',
        'main_nav': '主导航',
        'nav_menu': '菜单',
        'nav_menu_close': '关闭菜单',
        'sidebar_nav_label': '侧边导航',
        // 语言/主题切换
        'lang_switch': '切换语言',
        'lang_select': '语言选择',
        'lang_zh': '简体中文',
        'lang_en': 'English',
        'lang_switched': '已切换到 {lang}',
        'lang_coming_soon': '更多语言即将支持',
        'theme_toggle': '切换主题',
        'toggle_theme': '切换明暗主题',
        'sidebar_toggle': '切换侧边栏',
        'skip_to_content': '跳转到主要内容',
        'notification_area': '通知提示',
        // 详情页
        'back_to_list': '返回榜单',
        'back': '返回',
        'book_publisher': '出版社',
        'book_pub_date': '出版日期',
        'book_pages': '页数',
        'book_category': '分类',
        'book_description': '图书简介',
        'book_details': '详细信息',
        'view_original': '查看英文原文',
        'hide_original': '收起英文原文',
        'no_description': '暂无简介',
        'no_details': '暂无详细介绍',
        // 首页
        'page_title_bestsellers': '纽约时报畅销书排行榜',
        'page_title_awards': '国际图书奖项榜单',
        'filter_category': '图书分类',
        'filter_search': '搜索',
        'filter_search_scope': '搜索全部 NYT 分类',
        'search_placeholder': '搜索书名或作者...',
        'search_clear': '清除搜索',
        'btn_search': '搜索',
        'grid_density': '网格密度',
        'grid_view_featured': '精选三列',
        'grid_view_compact': '紧凑五列',
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
        // 搜索状态条
        'search_no_results': '未找到匹配「{query}」的图书',
        'search_partial': '部分分类暂时不可用，以下为可用结果（{n} 个分类未返回）',
        'search_failed': '搜索暂时不可用，请稍后重试',
        'search_load_failed': '榜单加载失败，请稍后重试',
        'search_retry': '重试',
        'home_toolbar': '结果工具条',
        // 通用
        'loading': '加载中...',
        'no_data': '暂无数据',
        'error_load': '加载失败',
        'theme_toggle_label': '切换主题',
        'theme_switched_dark': '已切换到深色模式',
        'theme_switched_light': '已切换到浅色模式',
        'close': '关闭',
        'close_toast': '关闭提示',
        // 书籍卡片
        'rank': '排名',
        'rank_prefix': '第',
        'rank_suffix': '名',
        'weeks_on_list': '累计上榜周数',
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
        // 卡片渲染（JS 重渲染时用）
        'card_cover_alt': '{title} 封面',
        'card_rank_aria': '第 {n} 名',
        'card_badge_aria': '排名: 第 {n} 名',
        'card_rank_up_aria': '上升 {n} 名',
        'card_rank_down_aria': '下降 {n} 名',
        'card_new_aria': '新书上榜',
        'card_new_badge': '新',
        'card_weeks_suffix': '{n} 周',
        'card_pages_suffix': '{n} 页',
        'card_isbn_prefix': 'ISBN:',
        'card_no_results': '未找到匹配的图书',
        'time_updated_at': '更新于: {time}',
        'time_just_now': '刚刚',
        'monthly_list': '月榜 · 每月更新',
        'monthly_list_with_date': '月榜 · 每月更新 · 榜单日期 {date}',
        'toast_category_load_failed': '加载失败，请重试',
        'toast_view_changed_grid': '已切换到网格视图',
        'toast_view_changed_list': '已切换到列表视图',
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
        // 筛选通用
        'filter_award_label': '奖项',
        'filter_award_all': '全部奖项',
        'filter_year_label': '年份',
        'filter_year_all': '全部年份',
        'filter_category_label': '类别',
        'filter_category_all': '全部分类',
        'filter_search_label': '搜索',
        'search_placeholder_award': '搜索书名或作者...',
        'search_book_author': '搜索书名或作者',
        'btn_filter': '筛选',
        'btn_reset': '重置',
        'empty_retry_hint': '请尝试切换筛选条件或稍后重试',
        'quick_nyt_link': '查看纽约时报畅销书榜',
        'quick_nyt_desc': '实时更新的畅销图书排行榜',
        'quick_links': '快速链接',
        // 新书推介页
        'nb_header_subtitle': '追踪国际大型出版社最新出版物',
        'nb_total_pre': '共',
        'nb_total_new_books': '共 {count} 本新书',
        'nb_total_new_books_suffix': '本新书',
        'nb_active_publishers': '{count} 家出版社',
        'nb_publishers_suffix': '家出版社',
        'nb_filter_publisher_label': '出版社',
        'nb_filter_publisher_all': '全部出版社',
        'nb_filter_category_label': '分类',
        'nb_filter_category_all': '全部分类',
        'nb_filter_time_label': '时间',
        'nb_time_7': '最近7天出版',
        'nb_time_30': '最近30天出版',
        'nb_time_90': '最近90天出版',
        'nb_time_180': '最近半年出版',
        'nb_time_365': '最近一年出版',
        'nb_search_placeholder': '搜索书名、作者、',
        'nb_search_label': '搜索新书',
        'nb_export_btn': '导出',
        'nb_sync_btn': '同步新书',
        'nb_result_summary': '当前筛选结果',
        'nb_result_unit': '本',
        'nb_filtered_by_date': '筛选范围：过去 {days} 天已出版 + 未来 {preview} 天预告；含日期待确认的新发现书目',
        'nb_window_scope': '筛选窗口：过去 {days} 天已出版 + 未来 {preview} 天预告 + 日期待确认的新发现书目',
        'nb_empty_title': '暂无新书数据',
        'nb_empty_desc': '当前出版时间范围暂无新书，可放宽时间范围或稍后刷新',
        'nb_empty_refresh': '刷新',
        'nb_load_failed': '加载失败',
        'nb_retry': '重试',
        'nb_no_match': '暂无匹配结果',
        'nb_no_match_desc': '尝试放宽出版时间范围或搜索其他关键词',
        'nb_unknown': '未知',
        'nb_syncing': '同步中',
        'nb_syncing_desc': '正在从出版社获取新书数据',
        'nb_sync_done_added': '同步完成！新增 {n} 本',
        'nb_sync_done_updated': '更新 {n} 本',
        'nb_sync_failed': '同步失败',
        'nb_translate_failed': '翻译失败',
        'nb_pub_date': '出版日期',
        'nb_detail_label_isbn': 'ISBN',
        'nb_detail_description_title': '图书简介',
        'nb_detail_no_description': '暂无简介',
        // 页脚 / 面包屑 / 页面副标题（补齐模板引用但字典缺失的 data-i18n key）
        'breadcrumbs_label': '面包屑导航',
        'footer_sitemap': '站点地图',
        'footer_data_source': '数据来源：NYT Books API',
        'footer_links_label': '页脚链接',
        'footer_copyright': '© {year} BookRank. 数据仅供学习交流，版权归原作者及出版社所有。',
        'publishers_subtitle': '汇集全球知名出版社与图书行业网站，点击即可访问',
        'wr_subtitle': '纽约时报畅销书榜单的每周变化趋势',
        'nb_search_btn': '搜索',
        'nb_reset_btn': '重置',
        // 新书速递：AJAX 重绘的 chips / 结果区 / 卡片徽标。语言切换后按运行时语言取词，
        // 缺键时会被 SSR 文案兜底，但只有这里存在才能真正跟着语言走。
        'nb_chip_remove_publisher': '移除出版社筛选',
        'nb_chip_remove_category': '移除分类筛选',
        'nb_chip_remove_search': '移除搜索',
        'nb_selected_filters': '已选条件',
        'nb_clear_all': '清除全部',
        'nb_just_published': '刚上市',
        'nb_category_unpublished': '分类未公开',
        'nb_collection_total': '全库收录 {books} 本新书 · {publishers} 家出版社',
    },
    en: {
        // Filters
        'filter_award_label': 'Award',
        'filter_award_all': 'All awards',
        'filter_year_label': 'Year',
        'filter_year_all': 'All years',
        'filter_category_label': 'Category',
        'filter_category_all': 'All categories',
        'filter_search_label': 'Search',
        'search_placeholder_award': 'Search title or author...',
        'search_book_author': 'Search title or author',
        'btn_filter': 'Filter',
        'empty_retry_hint': 'Try changing filters or retry later',
        'quick_nyt_link': 'View NYT Bestsellers',
        'quick_nyt_desc': 'Updated bestseller ranking in real time',
        'quick_links': 'Quick Links',
        // Navigation
        'nav_home': 'Home',
        'nav_awards': 'Awards',
        'nav_publishers': 'Publishers',
        'nav_rankings': 'More Charts',
        'nav_new_books': 'New Books',
        'nav_weekly': 'Weekly Reports',
        'nav_about': 'About',
        'sidebar_nav': 'Navigation',
        'sidebar_about': 'About',
        'nav_bestsellers': 'Bestsellers',
        'nav_publishers_guide': 'Publishers Guide',
        'nav_profile': 'My Profile',
        'nav_home_brand': 'BookRank Home',
        'main_nav': 'Main Navigation',
        'nav_menu': 'Menu',
        'nav_menu_close': 'Close menu',
        'sidebar_nav_label': 'Sidebar Navigation',
        // Language/Theme toggle
        'lang_switch': 'Switch Language',
        'lang_select': 'Language Selection',
        'lang_zh': '简体中文',
        'lang_en': 'English',
        'lang_switched': 'Switched to {lang}',
        'lang_coming_soon': 'More languages coming soon',
        'theme_toggle': 'Toggle Theme',
        'toggle_theme': 'Toggle Dark/Light Theme',
        'sidebar_toggle': 'Toggle Sidebar',
        'skip_to_content': 'Skip to main content',
        'notification_area': 'Notifications',
        // Detail page
        'back_to_list': 'Back to list',
        'back': 'Back',
        'book_publisher': 'Publisher',
        'book_pub_date': 'Published',
        'book_pages': 'Pages',
        'book_category': 'Category',
        'book_description': 'Description',
        'book_details': 'Details',
        'view_original': 'View Original',
        'hide_original': 'Hide Original',
        'no_description': 'No description',
        'no_details': 'No detailed description available',
        // Home
        'page_title_bestsellers': 'NYT Bestsellers',
        'page_title_awards': 'International Book Awards',
        'filter_category': 'Category',
        'filter_search': 'Search',
        'filter_search_scope': 'Search all NYT categories',
        'search_placeholder': 'Search title or author...',
        'search_clear': 'Clear search',
        'btn_search': 'Search',
        'grid_density': 'Grid density',
        'grid_view_featured': 'Featured 3-col',
        'grid_view_compact': 'Compact 5-col',
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
        // Search state banners
        'search_no_results': 'No books found for "{query}"',
        'search_partial': 'Some categories are temporarily unavailable. Showing available results ({n} categories did not respond)',
        'search_failed': 'Search is temporarily unavailable. Please try again later',
        'search_load_failed': 'Failed to load the chart. Please try again later',
        'search_retry': 'Retry',
        'home_toolbar': 'Results toolbar',
        // Common
        'loading': 'Loading...',
        'no_data': 'No data',
        'error_load': 'Failed to load',
        'theme_toggle_label': 'Toggle theme',
        'theme_switched_dark': 'Switched to dark mode',
        'theme_switched_light': 'Switched to light mode',
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
        // Card rendering keys (used during JS re-render on language switch)
        'card_cover_alt': '{title} cover',
        'card_rank_aria': 'Rank {n}',
        'card_badge_aria': 'Rank: #{n}',
        'card_rank_up_aria': 'Up {n} positions',
        'card_rank_down_aria': 'Down {n} positions',
        'card_new_aria': 'New on the list',
        'card_new_badge': 'NEW',
        'card_weeks_suffix': '{n} wk',
        'card_pages_suffix': '{n} pp',
        'card_isbn_prefix': 'ISBN:',
        'card_no_results': 'No matching books found',
        'time_updated_at': 'Updated: {time}',
        'time_just_now': 'Just now',
        'monthly_list': 'Monthly list · Updates monthly',
        'monthly_list_with_date': 'Monthly list · Updates monthly · List date {date}',
        'toast_category_load_failed': 'Load failed, please retry',
        'toast_view_changed_grid': 'Switched to grid view',
        'toast_view_changed_list': 'Switched to list view',
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
        // New Books page
        'nb_header_subtitle': 'Tracking latest publications from major international publishers',
        'nb_total_pre': '',
        'nb_total_new_books': '{count} new books',
        'nb_total_new_books_suffix': 'new books',
        'nb_active_publishers': '{count} publishers',
        'nb_publishers_suffix': 'publishers',
        'nb_filter_publisher_label': 'Publishers',
        'nb_filter_publisher_all': 'All publishers',
        'nb_filter_category_label': 'Category',
        'nb_filter_category_all': 'All categories',
        'nb_filter_time_label': 'Time',
        'nb_time_7': 'Last 7 days',
        'nb_time_30': 'Last 30 days',
        'nb_time_90': 'Last 90 days',
        'nb_time_180': 'Last 6 months',
        'nb_time_365': 'Last year',
        'nb_search_placeholder': 'Search title, author, ',
        'nb_search_label': 'Search new books',
        'nb_export_btn': 'Export',
        'nb_sync_btn': 'Sync new books',
        'nb_result_summary': 'Current filtered results',
        'nb_result_unit': 'books',
        'nb_filtered_by_date': 'Filtered to the past {days} days published, plus {preview} days ahead; includes recent discoveries with undated publication',
        'nb_window_scope': 'Filter window: published within the past {days} days, plus a {preview}-day preview of upcoming titles and recently discovered undated entries',
        'nb_empty_title': 'No new book data',
        'nb_empty_desc': 'No new books in this time range. Try widening the range or refresh later.',
        'nb_empty_refresh': 'Refresh',
        'nb_load_failed': 'Failed to load',
        'nb_retry': 'Retry',
        'nb_no_match': 'No matching results',
        'nb_no_match_desc': 'Try widening the time range or search with other keywords',
        'nb_unknown': 'Unknown',
        'nb_syncing': 'Syncing',
        'nb_syncing_desc': 'Fetching new book data from publishers',
        'nb_sync_done_added': 'Sync complete! Added {n} books',
        'nb_sync_done_updated': 'Updated {n} books',
        'nb_sync_failed': 'Sync failed',
        'nb_translate_failed': 'Translation failed',
        'nb_pub_date': 'Published',
        'nb_detail_label_isbn': 'ISBN',
        'nb_detail_description_title': 'Description',
        'nb_detail_no_description': 'No description available',
        // Footer / breadcrumb / page subtitles (template data-i18n keys missing from the dict)
        'breadcrumbs_label': 'Breadcrumb',
        'footer_sitemap': 'Sitemap',
        'footer_data_source': 'Data source: NYT Books API',
        'footer_links_label': 'Footer links',
        'footer_copyright':
            '© {year} BookRank. For learning and reference only. All rights belong to the original authors and publishers.',
        'publishers_subtitle': 'A collection of world-renowned publishers and book industry websites',
        'wr_subtitle': 'NYT Bestsellers',
        'nb_search_btn': 'Search',
        'nb_reset_btn': 'Reset',
        // New Books: AJAX-rendered chips / result area / card badges. Read at render
        // time so a language-only switch re-labels them without refetching.
        'nb_chip_remove_publisher': 'Remove publisher filter',
        'nb_chip_remove_category': 'Remove category filter',
        'nb_chip_remove_search': 'Remove search',
        'nb_selected_filters': 'Selected filters',
        'nb_clear_all': 'Clear all',
        'nb_just_published': 'Just published',
        'nb_category_unpublished': 'Category not published',
        'nb_collection_total': '{books} new books across the collection · {publishers} publishers',
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
 * 替换元素里的可见文本，保留图标等子元素。
 *
 * 单独抽出来是为了让 `data-i18n`（静态 chrome 文案）与 `data-zh/data-en`（数据型文案）
 * 两条支路共用同一套替换语义 —— 否则"带图标时文本落在哪个节点"会各写一遍、各漏一遍。
 * @param {Element} el - 目标元素
 * @param {string} text - 新文本
 */
function setVisibleText(el, text) {
    const textNode = Array.from(el.childNodes).find(
        n => n.nodeType === Node.TEXT_NODE && n.textContent.trim()
    );
    if (textNode) {
        textNode.textContent = text;
    } else if (!el.querySelector('svg, img, i')) {
        el.textContent = text;
    } else {
        // 有图标时，找到第一个文本节点替换
        for (let i = 0; i < el.childNodes.length; i++) {
            if (el.childNodes[i].nodeType === Node.TEXT_NODE) {
                el.childNodes[i].textContent = text;
                break;
            }
        }
    }
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
        // 收集 data-i18n-params-* 占位符
        const params = {};
        for (const attr of el.attributes) {
            if (attr.name.startsWith('data-i18n-params-')) {
                params[attr.name.replace('data-i18n-params-', '')] = attr.value;
            }
        }
        const translated = t(key, lang, params);
        if (translated !== key) {
            // 保留子元素（如图标），只替换文本节点
            setVisibleText(el, translated);
        }
    });

    // 双语属性：模板用 data-zh / data-en 同时携带两侧文案（服务端按 SSR 语言渲染可见文本），
    // 客户端按用户偏好择一覆盖。
    //
    // 为什么必须有这一支：`data-i18n` 只能处理**静态 chrome 文案**（有字典键），
    // 而分类名、书名、奖项名、周报标题这类**数据型**文案没有、也不该有字典键。它们此前
    // 只靠服务端按 SSR 语言择一渲染，于是浏览器内切换语言时**冻结在原语言**
    // （实测残留：面包屑三项 + 侧边栏导航段等共 48 处，用户报的就是这个）。
    // 模板里的 data-zh/data-en 一直存在、却没有任何 JS 消费它 —— 这一支把该约定变成真机制，
    // 顺带覆盖了所有已按此约定书写的模板（奖项详情、新书详情等 60+ 处）。
    document.querySelectorAll('[data-zh][data-en]').forEach(el => {
        const text = lang === 'zh' ? el.getAttribute('data-zh') : el.getAttribute('data-en');
        if (text === null || text === '') return;
        // 只有元素**自己**带文本节点时才替换。
        //
        // 这一条是硬要求，不是优化：模板里有容器把可见文案放在子元素里，例如
        //   <div class="book-title" data-zh="…" data-en="…"><a href="…">书名</a></div>
        // （_macros.html / awards.html / new_books.html 共 4 处）。若在这里直接
        // setVisibleText，`el.textContent = text` 会把整个 <a> 子元素抹掉 ——
        // 卡片上的书名链接就没了。容器内的文案由各自的页面级重渲染（applyNewBooksLanguage /
        // BookI18n）负责，这里不越权。
        const hasOwnText = Array.from(el.childNodes).some(
            n => n.nodeType === Node.TEXT_NODE && n.textContent.trim()
        );
        if (!hasOwnText) return;
        setVisibleText(el, text);
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

    // 翻译 select option（option 内的 data-i18n 自动被 querySelectorAll 捕获，
    // 但部分浏览器渲染的 select 选择项会显示原生文本，已在上面循环处理）

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

    // 同步 html lang，便于屏幕阅读器正确发音
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';

    // 设置语言 cookie，服务端后续请求保持同一语言
    const host = window.location.hostname;
    const cookieDomain = (host && host !== 'localhost' && host.includes('.')) ? host : '';
    document.cookie = 'lang=' + lang + '; path=/; max-age=31536000; SameSite=Lax;' + (cookieDomain ? ' domain=' + cookieDomain : '');

    if (typeof updateLangDropdown === 'function') {
        try { updateLangDropdown(lang); } catch(e) { console.warn('updateLangDropdown error:', e); }
    }

    var labelEl = document.getElementById('lang-current');
    if (labelEl) { labelEl.textContent = lang === 'zh' ? '\u4e2d' : 'EN'; }

    applyPageTranslation(lang);

    if (typeof BookI18n !== 'undefined' && BookI18n.size() > 0) {
        try { BookI18n.applyLanguage(lang); } catch(e) { console.warn('BookI18n error:', e); }
    }

    window.dispatchEvent(new CustomEvent('languagechange', { detail: { language: lang } }));

    var langName = lang === 'zh' ? '\u7b80\u4f53\u4e2d\u6587' : 'English';
    if (typeof showToast === 'function') {
        // 提示语按**新**语言生成：此前是写死的中文前缀（"已切换到 English"），
        // 于是切到英文后反倒弹出一句中文。
        showToast(t('lang_switched', lang, { lang: langName }), 'success');
    }
}

// 暴露到全局
window.TRANSLATIONS = TRANSLATIONS;
window.t = t;
window.applyPageTranslation = applyPageTranslation;
window.setGlobalLanguage = setGlobalLanguage;
window.switchLanguage = setGlobalLanguage;
