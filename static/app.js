// DOM元素
const listTypeSelect = document.getElementById('listType');
const fetchButton = document.getElementById('fetchBooks');
const exportButton = document.getElementById('exportBooks');
const searchInput = document.getElementById('searchInput');
const searchButton = document.getElementById('searchBtn');
const toggleViewButton = document.getElementById('toggleView');
const booksContainer = document.getElementById('booksContainer');
const loader = document.getElementById('loader');
const errorDiv = document.getElementById('error');
const infoDiv = document.getElementById('info');
const bookModal = document.getElementById('bookModal');
const bookDetail = document.getElementById('bookDetail');
const closeModal = document.getElementById('closeModal');
const lastUpdateElement = document.getElementById('lastUpdate');

// 应用状态
let appState = {
    currentView: 'grid', // 'grid' or 'list'
    currentPage: 1,
    itemsPerPage: 20,
    sessionId: generateSessionId(),
    lastSearchKeyword: '',
    allBooks: {},
    searchHistory: []
};

// 生成会话ID
function generateSessionId() {
    return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

// 显示信息提示
function showInfo(message, type = 'info') {
    infoDiv.textContent = message;
    infoDiv.className = type;
    infoDiv.style.display = 'block';
    
    setTimeout(() => {
        infoDiv.style.display = 'none';
    }, 3000);
}

// 更新最后更新时间显示
function updateLastUpdateTime(timeString) {
    lastUpdateElement.textContent = timeString;
}

// 设置加载状态
function setLoadingState(isLoading) {
    if (isLoading) {
        loader.style.display = 'block';
        fetchButton.disabled = true;
        fetchButton.innerHTML = '<i class="fa fa-spinner fa-spin"></i> 加载中...';
    } else {
        loader.style.display = 'none';
        fetchButton.disabled = false;
        fetchButton.innerHTML = '<i class="fa fa-refresh"></i> 加载图书';
    }
}

// 切换视图模式
function toggleView() {
    if (appState.currentView === 'grid') {
        appState.currentView = 'list';
        booksContainer.className = 'list-view';
        toggleViewButton.innerHTML = '<i class="fa fa-th-large"></i> 网格视图';
    } else {
        appState.currentView = 'grid';
        booksContainer.className = 'grid-view';
        toggleViewButton.innerHTML = '<i class="fa fa-th-list"></i> 列表视图';
    }
    
    // 保存用户偏好
    saveUserPreferences();
}

// 保存用户偏好
async function saveUserPreferences() {
    try {
        await fetch(`/api/user/preferences?session_id=${appState.sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                preferred_categories: [listTypeSelect.value],
                last_viewed_isbns: getRecentlyViewedBooks(),
                view_mode: appState.currentView
            })
        });
    } catch (error) {
        console.error('Failed to save user preferences:', error);
    }
}

// 获取最近查看的图书
function getRecentlyViewedBooks() {
    const recentBooks = [];
    const bookElements = booksContainer.querySelectorAll('.book-card');
    
    for (let i = 0; i < Math.min(5, bookElements.length); i++) {
        const isbn = bookElements[i].dataset.isbn;
        if (isbn) recentBooks.push(isbn);
    }
    
    return recentBooks;
}

// 加载用户偏好
async function loadUserPreferences() {
    try {
        const response = await fetch(`/api/user/preferences?session_id=${appState.sessionId}`);
        const data = await response.json();
        
        if (data.success && data.preferences) {
            const prefs = data.preferences;
            
            // 设置首选分类
            if (prefs.preferred_categories && prefs.preferred_categories.length > 0) {
                listTypeSelect.value = prefs.preferred_categories[0];
            }
            
            // 设置视图模式
            if (prefs.view_mode) {
                appState.currentView = prefs.view_mode;
                booksContainer.className = prefs.view_mode + '-view';
                toggleViewButton.innerHTML = 
                    prefs.view_mode === 'grid' 
                    ? '<i class="fa fa-th-list"></i> 列表视图' 
                    : '<i class="fa fa-th-large"></i> 网格视图';
            }
        }
    } catch (error) {
        console.error('Failed to load user preferences:', error);
    }
}

// 加载搜索历史
async function loadSearchHistory() {
    try {
        const response = await fetch(`/api/search/history?session_id=${appState.sessionId}`);
        const data = await response.json();
        
        if (data.success) {
            appState.searchHistory = data.history || [];
            updateSearchSuggestions();
        }
    } catch (error) {
        console.error('Failed to load search history:', error);
    }
}

// 更新搜索建议
function updateSearchSuggestions() {
    // 实现搜索建议下拉框
    const suggestionsContainer = document.getElementById('searchSuggestions');
    if (!suggestionsContainer) return;
    
    if (appState.searchHistory.length === 0) {
        suggestionsContainer.style.display = 'none';
        return;
    }
    
    suggestionsContainer.innerHTML = '';
    appState.searchHistory.forEach(item => {
        const suggestion = document.createElement('div');
        suggestion.className = 'search-suggestion';
        suggestion.innerHTML = `
            <span>${item.keyword}</span>
            <small>${item.result_count} 个结果</small>
        `;
        suggestion.onclick = () => {
            searchInput.value = item.keyword;
            searchBooks(item.keyword);
            suggestionsContainer.style.display = 'none';
        };
        suggestionsContainer.appendChild(suggestion);
    });
    
    suggestionsContainer.style.display = 'block';
}

// 图片加载失败处理函数
function handleImageError(imgElement, originalUrl) {
    if (!imgElement.dataset.retried) {
        imgElement.dataset.retried = "true";
        imgElement.src = originalUrl;
        return;
    }
    
    imgElement.src = "/static/default-cover.png";
    imgElement.alt = "无法加载封面图";
}

// 图片加载完成处理
function handleImageLoad(imgElement, placeholder) {
    placeholder.style.display = 'none';
    imgElement.style.display = 'block';
}

// 创建图书卡片
function createBookCard(book) {
    const card = document.createElement('div');
    card.className = 'book-card';
    card.dataset.isbn = book.id;
    card.onclick = () => showBookDetail(book);
    
    // 图片容器
    const imageContainer = document.createElement('div');
    imageContainer.className = 'book-image-container';
    
    // 占位符
    const placeholder = document.createElement('div');
    placeholder.className = 'image-placeholder';
    placeholder.innerHTML = '<div class="image-spinner"></div>';
    
    // 图书图片
    const img = document.createElement('img');
    img.className = 'book-image';
    img.style.display = 'none';
    img.src = book.cover;
    img.alt = book.title;
    img.loading = 'lazy'; // 懒加载
    
    // 图片事件处理
    img.onerror = () => handleImageError(img, book.cover);
    img.onload = () => handleImageLoad(img, placeholder);
    
    // 分类标签
    const categoryTag = document.createElement('span');
    categoryTag.className = 'book-category-tag';
    categoryTag.textContent = book.list_name;
    
    // 排名徽章
    const rankBadge = document.createElement('span');
    rankBadge.className = 'book-rank-badge';
    rankBadge.textContent = `#${book.rank}`;
    
    // 组装图片容器
    imageContainer.appendChild(placeholder);
    imageContainer.appendChild(img);
    imageContainer.appendChild(categoryTag);
    imageContainer.appendChild(rankBadge);
    
    // 图书信息
    const infoDiv = document.createElement('div');
    infoDiv.className = 'book-info';
    infoDiv.innerHTML = `
        <div class="book-title">${escapeHtml(book.title)}</div>
        <div class="book-author">${escapeHtml(book.author)}</div>
        <div class="book-meta">
            <span class="book-weeks">上榜${book.weeks_on_list}周</span>
            ${book.rank_last_week && book.rank_last_week !== '无' ? 
                `<span class="book-last-rank">上周: ${book.rank_last_week}</span>` : ''}
        </div>
        <div class="book-description">${escapeHtml(book.description || '暂无简介')}</div>
    `;
    
    // 组装卡片
    card.appendChild(imageContainer);
    card.appendChild(infoDiv);
    
    return card;
}

// HTML转义函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 加载图书
async function loadBooks(category, retries = 2) {
    booksContainer.innerHTML = '';
    errorDiv.style.display = 'none';
    infoDiv.style.display = 'none';
    
    setLoadingState(true);
    
    try {
        const response = await fetch(`/api/books/${category}?session_id=${appState.sessionId}`);
        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.message || "获取数据失败");
        }
        
        updateLastUpdateTime(data.latest_update || "未知");
        
        // 缓存所有图书数据
        if (category === 'all') {
            appState.allBooks = data.books;
        }
        
        if (category === 'all') {
            const categoryOrder = [
                'hardcover-fiction', 'hardcover-nonfiction',
                'trade-fiction-paperback', 'paperback-nonfiction'
            ];
            
            const categoryNames = {
                'hardcover-fiction': '精装小说',
                'hardcover-nonfiction': '精装非虚构',
                'trade-fiction-paperback': '平装小说',
                'paperback-nonfiction': '平装非虚构'
            };
            
            let hasBooks = false;
            
            categoryOrder.forEach(catId => {
                const books = data.books[catId] || [];
                if (books.length === 0) return;
                
                hasBooks = true;
                
                const categorySection = document.createElement('div');
                categorySection.className = 'category-section';
                
                const categoryHeader = document.createElement('div');
                categoryHeader.className = 'category-title';
                categoryHeader.innerHTML = `
                    <span>${categoryNames[catId]} (${books.length}本)</span>
                    <button class="category-toggle" data-category="${catId}">展开/收起</button>
                `;
                
                const booksGrid = document.createElement('div');
                booksGrid.className = 'books-container';
                booksGrid.id = `books-${catId}`;
                
                books.forEach(book => {
                    booksGrid.appendChild(createBookCard(book));
                });
                
                categorySection.appendChild(categoryHeader);
                categorySection.appendChild(booksGrid);
                booksContainer.appendChild(categorySection);
                
                // 添加分类切换事件
                categoryHeader.querySelector('.category-toggle').onclick = function() {
                    const booksGrid = document.getElementById(`books-${this.dataset.category}`);
                    booksGrid.style.display = booksGrid.style.display === 'none' ? 'grid' : 'none';
                };
            });
            
            if (!hasBooks) {
                showInfo('暂无数据', 'info');
            }
        } else {
            const books = data.books || [];
            if (books.length === 0) {
                showInfo('该分类暂无数据', 'info');
                return;
            }
            
            const booksGrid = document.createElement('div');
            booksGrid.className = 'books-container';
            
            books.forEach(book => {
                booksGrid.appendChild(createBookCard(book));
            });
            
            booksContainer.appendChild(booksGrid);
        }
        
        // 保存用户偏好
        saveUserPreferences();
        
    } catch (error) {
        console.error("加载失败:", error);
        errorDiv.textContent = `加载失败: ${error.message}`;
        errorDiv.style.display = 'block';
        
        if (retries > 0) {
            setTimeout(() => {
                loadBooks(category, retries - 1);
            }, 2000);
            return;
        }
    } finally {
        setLoadingState(false);
    }
}

// 搜索图书
async function searchBooks(keyword, retries = 1) {
    setLoadingState(true);
    searchButton.disabled = true;
    booksContainer.innerHTML = '';
    errorDiv.style.display = 'none';
    infoDiv.style.display = 'none';
    
    appState.lastSearchKeyword = keyword;
    
    try {
        const response = await fetch(`/api/search?keyword=${encodeURIComponent(keyword)}&session_id=${appState.sessionId}`);
        if (!response.ok) {
            throw new Error(`搜索失败: ${response.status}`);
        }
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.message || "搜索失败");
        }
        
        updateLastUpdateTime(data.latest_update || "未知");
        
        if (data.books.length === 0) {
            showInfo(`没有找到包含"${keyword}"的图书`, 'info');
            return;
        }
        
        const resultTitle = document.createElement('h2');
        resultTitle.className = 'category-title';
        resultTitle.textContent = `搜索"${keyword}"的结果 (${data.books.length}本)`;
        booksContainer.appendChild(resultTitle);
        
        const booksGrid = document.createElement('div');
        booksGrid.className = 'books-container';
        
        data.books.forEach(book => {
            booksGrid.appendChild(createBookCard(book));
        });
        
        booksContainer.appendChild(booksGrid);
        
        // 保存用户偏好
        saveUserPreferences();
        
    } catch (error) {
        console.error("搜索失败:", error);
        errorDiv.textContent = `搜索失败: ${error.message}`;
        errorDiv.style.display = 'block';
        
        if (retries > 0) {
            setTimeout(() => {
                searchBooks(keyword, retries - 1);
            }, 2000);
            return;
        }
    } finally {
        setLoadingState(false);
        searchButton.disabled = false;
    }
}

// 显示图书详情
function showBookDetail(book) {
    let buyLinksHtml = '';
    if (book.buy_links && book.buy_links.length > 0) {
        buyLinksHtml = '<div class="buy-links">';
        book.buy_links.forEach(link => {
            if (link.url) {
                buyLinksHtml += `
                    <a href="${link.url}" target="_blank" class="buy-link">
                        <i class="fa fa-shopping-cart"></i> ${link.name}
                    </a>`;
            }
        });
        buyLinksHtml += '</div>';
    }
    
    // 处理长文本的展开/收起功能
    const description = book.description || '暂无简介';
    const details = book.details || '暂无详细介绍';
    
    bookDetail.innerHTML = `
        <div class="book-detail">
            <div class="detail-image-container">
                <img src="${book.cover}" alt="${book.title}" class="detail-image"
                     onerror="this.src='/static/default-cover.png'">
                ${buyLinksHtml}
            </div>
            <div class="detail-info">
                <h2>${escapeHtml(book.title)}</h2>
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
                    <div class="expandable-content">
                        <p>${escapeHtml(description)}</p>
                    </div>
                    ${description.length > 200 ? '<button class="expand-btn">展开/收起</button>' : ''}
                </div>
                
                <div class="detail-section">
                    <h3>详细介绍</h3>
                    <div class="expandable-content">
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
    
    // 添加展开/收起功能
    const expandButtons = bookDetail.querySelectorAll('.expand-btn');
    expandButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const content = this.previousElementSibling;
            content.classList.toggle('expanded');
            this.textContent = content.classList.contains('expanded') ? '收起' : '展开';
        });
    });
    
    bookModal.style.display = 'block';
    
    // 保存用户最近查看的图书
    saveUserPreferences();
}

// 事件监听器
fetchButton.addEventListener('click', () => {
    const category = listTypeSelect.value;
    loadBooks(category);
});

exportButton.addEventListener('click', () => {
    const category = listTypeSelect.value;
    window.location.href = `/api/export/${category}`;
});

searchButton.addEventListener('click', () => {
    const keyword = searchInput.value.trim();
    if (keyword) {
        searchBooks(keyword);
    }
});

searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const keyword = searchInput.value.trim();
        if (keyword) {
            searchBooks(keyword);
        }
    }
});

searchInput.addEventListener('focus', () => {
    updateSearchSuggestions();
});

searchInput.addEventListener('input', () => {
    const suggestionsContainer = document.getElementById('searchSuggestions');
    if (suggestionsContainer) {
        suggestionsContainer.style.display = 'none';
    }
});

toggleViewButton.addEventListener('click', toggleView);

closeModal.addEventListener('click', () => {
    bookModal.style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target === bookModal) {
        bookModal.style.display = 'none';
    }
});

// 页面加载完成后初始化
window.addEventListener('DOMContentLoaded', () => {
    // 生成或获取会话ID
    const savedSessionId = localStorage.getItem('session_id');
    if (savedSessionId) {
        appState.sessionId = savedSessionId;
    } else {
        localStorage.setItem('session_id', appState.sessionId);
    }
    
    // 创建搜索建议容器
    const searchContainer = document.querySelector('.search-container');
    const suggestionsContainer = document.createElement('div');
    suggestionsContainer.id = 'searchSuggestions';
    suggestionsContainer.className = 'search-suggestions';
    searchContainer.appendChild(suggestionsContainer);
    
    // 加载用户偏好和搜索历史
    Promise.all([loadUserPreferences(), loadSearchHistory()]).then(() => {
        // 加载默认分类
        loadBooks('all');
    });
});

// 添加服务工作者进行缓存（可选）
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then(registration => {
            console.log('SW registered: ', registration);
        }).catch(registrationError => {
            console.log('SW registration failed: ', registrationError);
        });
    });
}