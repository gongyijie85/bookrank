/**
 * UI组件模块
 */

import { escapeHtml, createElement, appendElements, truncateText } from './utils.js';
import { store, actions } from './store.js';

/**
 * 图书卡片组件
 */
export class BookCard {
    constructor(book) {
        this.book = book;
        this.element = null;
    }
    
    /**
     * 渲染卡片
     * @returns {HTMLElement} 卡片元素
     */
    render() {
        const card = createElement('div', {
            className: 'book-card',
            attrs: { 'data-isbn': this.book.id }
        });
        
        // 图片容器
        const imageContainer = this._createImageContainer();
        
        // 获取当前语言
        const currentLang = store.getState().language || 'en';
        
        // 根据语言选择描述
        const description = currentLang === 'zh' && this.book.description_zh 
            ? this.book.description_zh 
            : this.book.description;
        
        // 图书信息
        const infoDiv = createElement('div', {
            className: 'book-info',
            html: `
                <div class="book-title">${escapeHtml(this.book.title)}</div>
                <div class="book-author">${escapeHtml(this.book.author)}</div>
                <div class="book-meta">
                    <span class="book-weeks">上榜${this.book.weeks_on_list}周</span>
                    ${this.book.rank_last_week && this.book.rank_last_week !== '无' 
                        ? `<span class="book-last-rank">上周: ${this.book.rank_last_week}</span>` 
                        : ''}
                </div>
                <div class="book-description">${escapeHtml(truncateText(description, 150))}</div>
            `
        });
        
        card.appendChild(imageContainer);
        card.appendChild(infoDiv);
        
        // 添加点击事件
        card.addEventListener('click', () => this._handleClick());
        
        this.element = card;
        return card;
    }
    
    /**
     * 创建图片容器
     * @returns {HTMLElement} 图片容器
     */
    _createImageContainer() {
        const container = createElement('div', { 
            className: 'book-image-container',
            attrs: { 'data-isbn': this.book.id }
        });
        
        // 占位符（显示加载动画）
        const placeholder = createElement('div', {
            className: 'image-placeholder',
            html: `
                <div class="image-placeholder-content">
                    <div class="image-spinner"></div>
                    <span class="image-loading-text">加载中...</span>
                </div>
            `
        });
        
        // 图书图片（初始不设置src，使用Intersection Observer懒加载）
        const img = createElement('img', {
            className: 'book-image',
            attrs: {
                'data-src': this.book.cover,
                alt: this.book.title,
                loading: 'lazy'
            }
        });
        img.style.opacity = '0';
        img.style.transition = 'opacity 0.3s ease';
        
        // 图片事件
        img.onerror = () => this._handleImageError(img, placeholder);
        img.onload = () => this._handleImageLoad(img, placeholder);
        
        // 分类标签
        const categoryTag = createElement('span', {
            className: 'book-category-tag',
            text: this.book.list_name
        });
        
        // 排名徽章 - 前三名使用皇冠图标
        const rank = this.book.rank;
        let rankContent = '';
        if (rank === 1) {
            rankContent = '<span class="rank-crown">👑</span>';
        } else if (rank === 2) {
            rankContent = '<span class="rank-crown">🥈</span>';
        } else if (rank === 3) {
            rankContent = '<span class="rank-crown">🥉</span>';
        } else {
            rankContent = `<span class="rank-number">${rank}</span>`;
        }
        
        const rankBadge = createElement('span', {
            className: 'book-rank-badge',
            attrs: {
                'data-rank': rank,
                title: `当前排名: 第${rank}名`
            },
            html: rankContent
        });
        
        // 排名变化指示器
        if (this.book.rank_last_week && this.book.rank_last_week !== '无') {
            const lastWeek = parseInt(this.book.rank_last_week);
            const current = parseInt(this.book.rank);
            if (!isNaN(lastWeek) && !isNaN(current)) {
                const change = lastWeek - current;
                if (change !== 0) {
                    const changeClass = change > 0 ? 'rank-up' : 'rank-down';
                    const changeIcon = change > 0 ? '↑' : '↓';
                    const changeBadge = createElement('span', {
                        className: `rank-change ${changeClass}`,
                        text: `${changeIcon}${Math.abs(change)}`,
                        title: `较上周${change > 0 ? '上升' : '下降'}${Math.abs(change)}名`
                    });
                    rankBadge.appendChild(changeBadge);
                }
            }
        }
        
        container.appendChild(placeholder);
        container.appendChild(img);
        container.appendChild(categoryTag);
        container.appendChild(rankBadge);
        
        // 使用Intersection Observer实现懒加载
        this._setupLazyLoad(img, container);
        
        return container;
    }
    
    /**
     * 设置图片懒加载
     * @param {HTMLImageElement} img - 图片元素
     * @param {HTMLElement} container - 容器元素
     */
    _setupLazyLoad(img, container) {
        // 如果浏览器支持IntersectionObserver
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const src = img.getAttribute('data-src');
                        if (src) {
                            img.src = src;
                            img.removeAttribute('data-src');
                        }
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                rootMargin: '50px 0px', // 提前50px开始加载
                threshold: 0.01
            });
            
            imageObserver.observe(container);
        } else {
            // 降级处理：直接加载
            img.src = img.getAttribute('data-src');
        }
    }
    
    /**
     * 处理图片加载错误
     * @param {HTMLImageElement} img - 图片元素
     * @param {HTMLElement} placeholder - 占位符
     */
    _handleImageError(img, placeholder) {
        // 重试机制
        if (!img.dataset.retryCount) {
            img.dataset.retryCount = '1';
            setTimeout(() => {
                img.src = img.src; // 重试
            }, 1000);
            return;
        }
        
        // 显示默认封面
        placeholder.innerHTML = `
            <div class="image-fallback">
                <i class="fa fa-book" style="font-size: 48px; color: #ccc;"></i>
                <span>暂无封面</span>
            </div>
        `;
        img.style.display = 'none';
        img.src = '/static/default-cover.png';
    }
    
    /**
     * 处理图片加载完成
     * @param {HTMLImageElement} img - 图片元素
     * @param {HTMLElement} placeholder - 占位符
     */
    _handleImageLoad(img, placeholder) {
        placeholder.style.opacity = '0';
        img.style.opacity = '1';
        
        // 延迟隐藏占位符，确保过渡平滑
        setTimeout(() => {
            placeholder.style.display = 'none';
        }, 300);
    }
    
    /**
     * 处理卡片点击
     */
    _handleClick() {
        // 触发自定义事件
        const event = new CustomEvent('book:click', { 
            detail: { book: this.book },
            bubbles: true 
        });
        this.element.dispatchEvent(event);
    }
}

/**
 * 图书详情弹窗组件
 */
export class BookDetailModal {
    constructor() {
        this.modal = null;
        this.content = null;
        this.detailContainer = null;
        this.closeBtn = null;
        this.currentBook = null;
        this.isTranslated = false;
        this.isTranslating = false;
        this._initModal();
    }
    
    /**
     * 初始化弹窗 - 使用HTML中已有的元素
     */
    _initModal() {
        // 获取HTML中已存在的模态框元素
        this.modal = document.getElementById('bookModal');
        this.content = this.modal?.querySelector('.modal-content');
        this.detailContainer = document.getElementById('bookDetail');
        this.closeBtn = document.getElementById('closeModal');
        
        if (!this.modal || !this.detailContainer) {
            console.error('Modal elements not found in DOM');
            return;
        }
        
        // 事件绑定
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.hide());
        }
        
        // 点击模态框外部关闭
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.hide();
        });
        
        // ESC键关闭
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.classList.contains('show')) {
                this.hide();
            }
        });
    }
    
    /**
     * 显示图书详情
     * @param {Object} book - 图书数据
     */
    show(book) {
        if (!this.detailContainer) {
            console.error('Detail container not found');
            return;
        }
        
        // 保存当前图书数据
        this.currentBook = book;
        this.isTranslated = false;
        this.isTranslating = false;
        
        // 根据当前语言设置渲染内容
        const currentLang = window.bookStore?.getState().language || 'en';
        this.detailContainer.innerHTML = this._renderDetail(book, currentLang);
        
        // 显示模态框（使用CSS类）
        this.modal.classList.add('show');
        document.body.style.overflow = 'hidden';
        
        // 滚动到顶部
        if (this.content) {
            this.content.scrollTop = 0;
        }
    }
    
    /**
     * 绑定翻译按钮事件
     */
    _bindTranslateEvent() {
        const translateBtn = this.detailContainer.querySelector('.translate-btn');
        if (translateBtn) {
            translateBtn.addEventListener('click', () => this._handleTranslate());
        }
    }
    
    /**
     * 处理翻译
     */
    async _handleTranslate() {
        if (this.isTranslating || !this.currentBook) return;
        
        const translateBtn = this.detailContainer.querySelector('.translate-btn');
        const descContent = this.detailContainer.querySelector('.desc-content');
        const detailsContent = this.detailContainer.querySelector('.details-content');
        
        // 如果已经翻译过，切换显示
        if (this.isTranslated) {
            this._toggleTranslation();
            return;
        }
        
        // 检查是否有预翻译内容
        const hasPreTranslation = this.currentBook.description_zh || this.currentBook.details_zh;
        
        if (hasPreTranslation) {
            // 使用预翻译内容，直接切换显示
            this._applyPreTranslation();
            return;
        }
        
        // 没有预翻译内容，调用API进行实时翻译
        this.isTranslating = true;
        if (translateBtn) {
            translateBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 翻译中...';
            translateBtn.disabled = true;
        }
        
        try {
            // 调用翻译API
            const response = await fetch('/api/translate/book/' + this.currentBook.id, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ target_lang: 'zh' })
            });
            
            const result = await response.json();
            
            if (result.success && result.data.book) {
                const translatedBook = result.data.book;
                
                // 更新内容
                if (descContent && translatedBook.description_zh) {
                    descContent.innerHTML = `<p>${escapeHtml(translatedBook.description_zh)}</p>`;
                    descContent.dataset.translated = translatedBook.description_zh;
                }
                
                if (detailsContent && translatedBook.details_zh) {
                    detailsContent.innerHTML = `<p>${escapeHtml(translatedBook.details_zh)}</p>`;
                    detailsContent.dataset.translated = translatedBook.details_zh;
                }
                
                this.isTranslated = true;
                
                if (translateBtn) {
                    translateBtn.innerHTML = '<i class="fa fa-language"></i> 显示原文';
                    translateBtn.disabled = false;
                }
            } else {
                throw new Error(result.message || '翻译失败');
            }
        } catch (error) {
            console.error('翻译失败:', error);
            if (translateBtn) {
                translateBtn.innerHTML = '<i class="fa fa-exclamation-triangle"></i> 翻译失败';
                translateBtn.disabled = false;
            }
            
            // 显示错误提示
            const toast = document.querySelector('.message-toast-container');
            if (toast) {
                const errorToast = document.createElement('div');
                errorToast.className = 'message-toast message-toast--error';
                errorToast.textContent = '翻译失败，请稍后重试';
                toast.appendChild(errorToast);
                setTimeout(() => errorToast.remove(), 3000);
            }
        } finally {
            this.isTranslating = false;
        }
    }
    
    /**
     * 应用预翻译内容
     */
    _applyPreTranslation() {
        const descContent = this.detailContainer.querySelector('.desc-content');
        const detailsContent = this.detailContainer.querySelector('.details-content');
        const translateBtn = this.detailContainer.querySelector('.translate-btn');
        const btnText = translateBtn?.querySelector('.translate-btn-text');
        
        // 切换到中文显示
        if (descContent && this.currentBook.description_zh) {
            descContent.innerHTML = `<p>${escapeHtml(this.currentBook.description_zh)}</p>`;
            descContent.dataset.showing = 'translated';
        }
        
        if (detailsContent && this.currentBook.details_zh) {
            detailsContent.innerHTML = `<p>${escapeHtml(this.currentBook.details_zh)}</p>`;
            detailsContent.dataset.showing = 'translated';
        }
        
        this.isTranslated = true;
        
        if (translateBtn) {
            translateBtn.setAttribute('title', '切换到原文');
        }
        if (btnText) {
            btnText.textContent = '原文';
        }
    }
    
    /**
     * 切换原文/译文显示
     */
    _toggleTranslation() {
        const descContent = this.detailContainer.querySelector('.desc-content');
        const detailsContent = this.detailContainer.querySelector('.details-content');
        const translateBtn = this.detailContainer.querySelector('.translate-btn');
        const btnText = translateBtn?.querySelector('.translate-btn-text');
        
        const isShowingTranslated = descContent?.dataset.showing === 'translated';
        
        // 获取预翻译内容（优先使用当前图书数据）
        const descZh = this.currentBook?.description_zh || descContent?.dataset.translated;
        const detailsZh = this.currentBook?.details_zh || detailsContent?.dataset.translated;
        const hasTranslation = this.currentBook?.description_zh || this.currentBook?.details_zh;
        
        if (isShowingTranslated) {
            // 切换到原文
            if (descContent) {
                descContent.innerHTML = `<p>${escapeHtml(descContent.dataset.original || '暂无简介')}</p>`;
                descContent.dataset.showing = 'original';
            }
            if (detailsContent) {
                detailsContent.innerHTML = `<p>${escapeHtml(detailsContent.dataset.original || '暂无详细介绍')}</p>`;
                detailsContent.dataset.showing = 'original';
            }
            if (translateBtn) {
                translateBtn.setAttribute('title', hasTranslation ? '切换到中文' : '翻译图书介绍');
            }
            if (btnText) {
                btnText.textContent = hasTranslation ? '中文' : '翻译';
            }
            this.isTranslated = false;
        } else {
            // 切换到译文
            if (descContent && descZh) {
                descContent.innerHTML = `<p>${escapeHtml(descZh)}</p>`;
                descContent.dataset.showing = 'translated';
            }
            if (detailsContent && detailsZh) {
                detailsContent.innerHTML = `<p>${escapeHtml(detailsZh)}</p>`;
                detailsContent.dataset.showing = 'translated';
            }
            if (translateBtn) {
                translateBtn.setAttribute('title', '切换到原文');
            }
            if (btnText) {
                btnText.textContent = '原文';
            }
            this.isTranslated = true;
        }
    }
    
    /**
     * 隐藏弹窗
     */
    hide() {
        if (this.modal) {
            this.modal.classList.remove('show');
        }
        document.body.style.overflow = '';
    }
    
    /**
     * 渲染详情内容
     * @param {Object} book - 图书数据
     * @param {string} lang - 语言设置 ('en' 或 'zh')
     * @returns {string} HTML字符串
     */
    _renderDetail(book, lang = 'en') {
        // 购买链接
        let buyLinksHtml = '';
        if (book.buy_links && book.buy_links.length > 0) {
            buyLinksHtml = '<div class="buy-links">' +
                book.buy_links.map(link => `
                    <a href="${escapeHtml(link.url)}" target="_blank" class="buy-link">
                        <i class="fa fa-shopping-cart"></i> ${escapeHtml(link.name)}
                    </a>
                `).join('') +
                '</div>';
        }
        
        // 根据语言选择显示内容
        const description = lang === 'zh' && book.description_zh 
            ? book.description_zh 
            : (book.description || '暂无简介');
        const details = lang === 'zh' && book.details_zh 
            ? book.details_zh 
            : (book.details || '暂无详细介绍');
        
        return `
            <div class="book-detail">
                <div class="detail-image-container">
                    <img src="${book.cover}" alt="${escapeHtml(book.title)}" class="detail-image"
                         onerror="this.src='/static/default-cover.png'">
                    ${buyLinksHtml}
                </div>
                <div class="detail-info">
                    <div class="detail-header">
                        <h2>${escapeHtml(book.title)}</h2>
                    </div>
                    <div class="detail-author">作者: ${escapeHtml(book.author)}</div>
                    
                    <div class="detail-meta">
                        <div class="meta-item">
                            <span class="meta-label">出版社:</span> ${escapeHtml(book.publisher || '未知')}
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">排名:</span> 第${book.rank}名
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">上榜时间:</span> ${book.weeks_on_list}周
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">上周排名:</span> ${book.rank_last_week || '无'}
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">出版日期:</span> ${escapeHtml(book.publication_dt || '未知')}
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">页数:</span> ${book.page_count || '未知'}
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">语言:</span> ${escapeHtml(book.language || '未知')}
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">ISBN:</span> ${book.id || '未知'}
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">价格:</span> ${escapeHtml(book.price || '未知')}
                        </div>
                    </div>
                    
                    <div class="detail-section">
                        <h3>简介</h3>
                        <div class="expandable-content desc-content">
                            <p>${escapeHtml(description)}</p>
                        </div>
                        ${description.length > 200 ? '<button class="expand-btn">展开/收起</button>' : ''}
                    </div>
                    
                    <div class="detail-section">
                        <h3>详细介绍</h3>
                        <div class="expandable-content details-content">
                            <p>${escapeHtml(details)}</p>
                        </div>
                        ${details.length > 200 ? '<button class="expand-btn">展开/收起</button>' : ''}
                    </div>
                    
                    <div class="detail-section">
                        <h3>榜单信息</h3>
                        <p>${escapeHtml(book.list_name)}（数据发布日期: ${book.published_date}）</p>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * 绑定展开/收起事件
     * @param {HTMLElement} container - 容器元素
     */
    _bindExpandEvents(container) {
        const buttons = container.querySelectorAll('.expand-btn');
        buttons.forEach(btn => {
            btn.addEventListener('click', function() {
                const content = this.previousElementSibling;
                content.classList.toggle('expanded');
                this.textContent = content.classList.contains('expanded') ? '收起' : '展开';
            });
        });
    }
}

/**
 * 消息提示组件
 */
export class MessageToast {
    constructor() {
        this.container = null;
        this._createContainer();
    }
    
    _createContainer() {
        this.container = createElement('div', { className: 'message-toast-container' });
        document.body.appendChild(this.container);
    }
    
    /**
     * 显示消息
     * @param {string} message - 消息内容
     * @param {string} type - 消息类型 ('info' | 'success' | 'warning' | 'error')
     * @param {number} duration - 显示时长（毫秒）
     */
    show(message, type = 'info', duration = 3000) {
        const toast = createElement('div', {
            className: `message-toast message-toast--${type}`,
            text: message
        });
        
        this.container.appendChild(toast);
        
        // 动画显示
        requestAnimationFrame(() => {
            toast.classList.add('message-toast--show');
        });
        
        // 自动移除
        setTimeout(() => {
            toast.classList.remove('message-toast--show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
}

/**
 * 加载指示器组件
 */
export class LoadingIndicator {
    constructor() {
        this.element = null;
    }
    
    show() {
        if (!this.element) {
            this.element = createElement('div', {
                className: 'loader',
                html: '<div class="spinner"></div>'
            });
        }
        this.element.style.display = 'block';
        return this.element;
    }
    
    hide() {
        if (this.element) {
            this.element.style.display = 'none';
        }
    }
}

/**
 * 搜索建议组件
 */
export class SearchSuggestions {
    constructor(inputElement, onSelect) {
        this.input = inputElement;
        this.onSelect = onSelect;
        this.container = null;
        this._createContainer();
        this._bindEvents();
    }
    
    _createContainer() {
        this.container = createElement('div', { className: 'search-suggestions' });
        this.container.style.display = 'none';
        this.input.parentNode.appendChild(this.container);
    }
    
    _bindEvents() {
        // 点击外部关闭
        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target) && !this.container.contains(e.target)) {
                this.hide();
            }
        });
    }
    
    /**
     * 显示搜索建议
     * @param {Array} history - 搜索历史数组
     */
    show(history) {
        if (!history || history.length === 0) {
            this.hide();
            return;
        }
        
        this.container.innerHTML = '';
        
        history.forEach(item => {
            const suggestion = createElement('div', {
                className: 'search-suggestion',
                html: `
                    <span>${escapeHtml(item.keyword)}</span>
                    <small>${item.result_count} 个结果</small>
                `
            });
            
            suggestion.addEventListener('click', () => {
                this.onSelect(item.keyword);
                this.hide();
            });
            
            this.container.appendChild(suggestion);
        });
        
        this.container.style.display = 'block';
    }
    
    hide() {
        this.container.style.display = 'none';
    }
}
