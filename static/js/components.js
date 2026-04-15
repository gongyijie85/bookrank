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
        
        // 获取图书描述（暂时只支持英文）
        const description = this.book.description;
        
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
        
        // 排名徽章 - 前三名使用皇冠徽章
        const rank = this.book.rank;
        let rankBadge;
        
        if (rank <= 3) {
            // 前三名：皇冠徽章
            const crownColors = ['gold', 'silver', 'bronze'];
            const crownColor = crownColors[rank - 1];
            rankBadge = createElement('span', {
                className: `book-rank-badge crown-badge ${crownColor}`,
                attrs: {
                    'data-rank': rank,
                    title: `当前排名: 第${rank}名`
                },
                html: `
                    <svg class="crown-svg" viewBox="0 0 36 24">
                        <defs>
                            <linearGradient id="${crownColor}Grad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:${crownColor === 'gold' ? '#FFD700' : crownColor === 'silver' ? '#F5F5F5' : '#D4A574'}"/>
                                <stop offset="50%" style="stop-color:${crownColor === 'gold' ? '#FFA500' : crownColor === 'silver' ? '#C0C0C0' : '#B87333'}"/>
                                <stop offset="100%" style="stop-color:${crownColor === 'gold' ? '#FF8C00' : crownColor === 'silver' ? '#A0A0A0' : '#8B4513'}"/>
                            </linearGradient>
                        </defs>
                        <path d="M2 22 L2 8 L8 13 L14 3 L18 10 L22 3 L28 13 L34 8 L34 22 Q34 24 31 24 L5 24 Q2 24 2 22 Z" 
                              fill="url(#${crownColor}Grad)" stroke="${crownColor === 'gold' ? '#B8860B' : crownColor === 'silver' ? '#808080' : '#8B4513'}" stroke-width="0.8"/>
                        <circle cx="8" cy="13" r="2.5" fill="${crownColor === 'gold' ? '#FF4444' : '#E8E8E8'}" stroke="${crownColor === 'gold' ? '#B8860B' : '#808080'}" stroke-width="0.5"/>
                        <circle cx="14" cy="3" r="2.5" fill="${crownColor === 'gold' ? '#4444FF' : '#C0C0C0'}" stroke="${crownColor === 'gold' ? '#B8860B' : '#808080'}" stroke-width="0.5"/>
                        <circle cx="18" cy="10" r="3" fill="${crownColor === 'gold' ? '#FFD700' : '#F5F5F5'}" stroke="${crownColor === 'gold' ? '#B8860B' : '#808080'}" stroke-width="0.5"/>
                        <circle cx="22" cy="3" r="2.5" fill="${crownColor === 'gold' ? '#44FF44' : '#C0C0C0'}" stroke="${crownColor === 'gold' ? '#B8860B' : '#808080'}" stroke-width="0.5"/>
                        <circle cx="28" cy="13" r="2.5" fill="${crownColor === 'gold' ? '#FF4444' : '#E8E8E8'}" stroke="${crownColor === 'gold' ? '#B8860B' : '#808080'}" stroke-width="0.5"/>
                        <rect x="2" y="19" width="32" height="3" fill="${crownColor === 'gold' ? '#B8860B' : crownColor === 'silver' ? '#808080' : '#8B4513'}"/>
                    </svg>
                    <span class="crown-rank-number">${rank}</span>
                `
            });
        } else {
            // 第4名+：普通圆形徽章
            rankBadge = createElement('span', {
                className: 'book-rank-badge',
                attrs: {
                    'data-rank': rank,
                    title: `当前排名: 第${rank}名`
                },
                html: `<span class="rank-number">${rank}</span>`
            });
        }
        
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
// BookDetailModal component removed to avoid conflict with existing modal implementation in index.html

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
