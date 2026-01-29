document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const listTypeSelect = document.getElementById('listType');
    const fetchButton = document.getElementById('fetchBooks');
    const exportButton = document.getElementById('exportBooks');
    const searchInput = document.getElementById('searchInput');
    const searchButton = document.getElementById('searchBtn');
    const booksContainer = document.getElementById('booksContainer');
    const loader = document.getElementById('loader');
    const errorDiv = document.getElementById('error');
    const infoDiv = document.getElementById('info');
    const lastUpdateElement = document.getElementById('lastUpdate');

    // Modals
    const bookModal = document.getElementById('bookModal');
    const bookDetail = document.getElementById('bookDetail');
    const closeModal = document.getElementById('closeModal');
    const xhsModal = document.getElementById('xhsModal');
    const xhsContent = document.getElementById('xhsContent');
    const xhsLoading = document.getElementById('xhsLoading');
    const xhsContentBody = document.getElementById('xhsContentBody');
    const xhsError = document.getElementById('xhsError');
    const closeXhsModal = document.getElementById('closeXhsModal');

    const LANGUAGE_MAP = {
        'en': 'English', 'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean',
        'fr': 'French', 'de': 'German', 'es': 'Spanish', 'ru': 'Russian', 'un': 'Unknown'
    };

    // --- UI Functions ---
    const showMessage = (element, message, duration = 3000) => {
        element.textContent = message;
        element.style.display = 'block';
        if (duration) {
            setTimeout(() => { element.style.display = 'none'; }, duration);
        }
    };

    const toggleLoader = (show) => {
        loader.style.display = show ? 'block' : 'none';
        fetchButton.disabled = show;
        searchButton.disabled = show;
        fetchButton.innerHTML = show ? '<i class="fa fa-spinner fa-spin"></i> 加载中...' : '<i class="fa fa-refresh"></i> 加载图书';
    };

    // --- Data Rendering ---
    const createBookCard = (book) => {
        const card = document.createElement('div');
        card.className = 'book-card';
        card.onclick = () => showBookDetail(book);

        card.innerHTML = `
            <div class="book-image-container">
                <img src="${book.cover}" alt="${book.title_zh || book.title}" class="book-image" onerror="this.onerror=null;this.src='/static/default-cover.png';">
                <span class="book-category-tag">${book.list_name_zh || book.list_name}</span>
            </div>
            <div class="book-info">
                <div class="book-title" title="${book.title_zh || book.title}">${book.title_zh || book.title}</div>
                <div class="book-author">${book.author_zh || book.author}</div>
                <div class="book-meta">
                    <span class="book-rank">第${book.rank}名</span>
                    上榜${book.weeks_on_list}周
                </div>
                <div class="book-description">${book.description_zh || '暂无简介'}</div>
            </div>
        `;
        return card;
    };

    const displayBooks = (data, isSearch = false, keyword = '') => {
        booksContainer.innerHTML = '';
        if (isSearch) {
            const resultTitle = document.createElement('h2');
            resultTitle.className = 'category-title';
            resultTitle.textContent = `搜索"${keyword}"的结果 (${data.length}本)`;
            booksContainer.appendChild(resultTitle);

            const grid = document.createElement('div');
            grid.className = 'books-grid';
            data.forEach(book => grid.appendChild(createBookCard(book)));
            booksContainer.appendChild(grid);
        } else { // Category view
            const categoryOrder = ['hardcover-fiction', 'hardcover-nonfiction', 'trade-fiction-paperback', 'paperback-nonfiction'];
            categoryOrder.forEach(catId => {
                const books = data[catId] || [];
                if (books.length === 0) return;

                const categoryTitle = document.createElement('h2');
                categoryTitle.className = 'category-title';
                categoryTitle.textContent = books[0].category_name_zh || books[0].category_name;
                booksContainer.appendChild(categoryTitle);

                const grid = document.createElement('div');
                grid.className = 'books-grid';
                books.forEach(book => grid.appendChild(createBookCard(book)));
                booksContainer.appendChild(grid);
            });
        }
    };
    
    const showBookDetail = (book) => {
        const buyLinksHtml = book.buy_links.map(link => `<a href="${link.url}" target="_blank" class="buy-link">${link.name}</a>`).join('');
        const langName = LANGUAGE_MAP[book.language] || book.language.toUpperCase();

        bookDetail.innerHTML = `
            <div class="book-detail">
                <div class="detail-image-container">
                    <img src="${book.cover}" alt="${book.title_zh || book.title}" class="detail-image" onerror="this.src='/static/default-cover.png'">
                    <div class="buy-links">${buyLinksHtml}</div>
                    <button id="generateXhsBtn"><i class="fa fa-pencil"></i> 生成小红书文案</button>
                </div>
                <div class="detail-info">
                    <h2>${book.title_zh || book.title}</h2>
                    <div class="detail-author">作者: ${book.author_zh || book.author}</div>
                    <div class="detail-meta">
                        <div><span class="meta-label">出版社:</span> ${book.publisher || '未知'}</div>
                        <div><span class="meta-label">排名:</span> 第${book.rank}名</div>
                        <div><span class="meta-label">上榜时间:</span> ${book.weeks_on_list}周</div>
                        <div><span class="meta-label">出版日期:</span> ${book.publication_dt || '未知'}</div>
                        <div><span class="meta-label">页数:</span> ${book.page_count || '-'}</div>
                        <div><span class="meta-label">语言:</span> ${langName}</div>
                        <div><span class="meta-label">ISBN:</span> ${book.id || '未知'}</div>
                    </div>
                    <div class="detail-section"><h3>图书简介</h3><p>${book.description_zh || book.description_en || '暂无简介'}</p></div>
                    <div class="detail-section"><h3>详细介绍</h3><p>${book.details_zh || book.details_en || '暂无详细介绍'}</p></div>
                </div>
            </div>`;
        bookModal.style.display = 'block';
        document.getElementById('generateXhsBtn').addEventListener('click', () => generateXhsContent(book.id));
    };

    const renderXhsContent = (data) => {
        const { titles, body, tags } = data;
        xhsContentBody.innerHTML = `
            <div class="xhs-title-group">
                <div class="xhs-title-type">✨ Emoji类标题</div>
                <ul class="xhs-title-list">${titles.emoji.map(t => `<li>${t}</li>`).join('')}</ul>
            </div>
            <div class="xhs-title-group">
                <div class="xhs-title-type">❓ 问题类标题</div>
                <ul class="xhs-title-list">${titles.question.map(t => `<li>${t}</li>`).join('')}</ul>
            </div>
            <div class="detail-section"><h3>📝 正文内容</h3><div class="xhs-body">${body}</div></div>
            <div class="detail-section"><h3>🏷️ 话题标签</h3><div class="xhs-tags">${tags.map(t => `<span class="xhs-tag">${t}</span>`).join('')}</div></div>
            <div class="xhs-actions"><button class="copy-btn" id="copyXhsBtn"><i class="fa fa-copy"></i> 复制全部文案</button></div>`;
        
        document.getElementById('copyXhsBtn').addEventListener('click', (e) => {
            const fullText = `${titles.emoji[0]}\n\n${body}\n\n${tags.join(' ')}`;
            navigator.clipboard.writeText(fullText).then(() => {
                showMessage(infoDiv, "文案已复制到剪贴板！");
                const btn = e.currentTarget;
                btn.innerHTML = '<i class="fa fa-check"></i> 已复制';
                setTimeout(() => { btn.innerHTML = '<i class="fa fa-copy"></i> 复制全部文案'; }, 2000);
            });
        });
    };

    // --- API Calls ---
    const fetchData = async (url) => {
        errorDiv.style.display = 'none';
        infoDiv.style.display = 'none';
        toggleLoader(true);
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            const data = await response.json();
            if (!data.success) throw new Error(data.message || "获取数据失败");
            lastUpdateElement.textContent = data.latest_update || "未知";
            return data;
        } catch (error) {
            showMessage(errorDiv, `加载失败: ${error.message}`, 0);
            return null;
        } finally {
            toggleLoader(false);
        }
    };

    const loadBooks = async () => {
        const category = listTypeSelect.value;
        const data = await fetchData(`/api/books/${category}`);
        if (data) {
            const books = category === 'all' ? data.books : { [category]: data.books };
            const bookCount = Object.values(books).reduce((acc, val) => acc + val.length, 0);
            if (bookCount === 0) {
                showMessage(infoDiv, '该分类下暂无图书信息。');
                booksContainer.innerHTML = '';
            } else {
                displayBooks(books);
            }
        }
    };

    const searchBooks = async () => {
        const keyword = searchInput.value.trim();
        if (keyword.length < 2) {
            showMessage(infoDiv, '请输入至少2个字符进行搜索。');
            return;
        }
        const data = await fetchData(`/api/search?keyword=${encodeURIComponent(keyword)}`);
        if (data && data.books) {
            if (data.books.length === 0) {
                showMessage(infoDiv, `没有找到与"${keyword}"相关的图书。`);
                booksContainer.innerHTML = '';
            } else {
                displayBooks(data.books, true, keyword);
            }
        }
    };

    const generateXhsContent = async (isbn) => {
        xhsModal.style.display = 'block';
        xhsLoading.style.display = 'block';
        xhsContentBody.style.display = 'none';
        xhsError.style.display = 'none';

        try {
            const response = await fetch(`/api/xhs/content?isbn=${isbn}`);
            const result = await response.json();
            if (!result.success) throw new Error(result.message);
            renderXhsContent(result.data);
            xhsContentBody.style.display = 'block';
        } catch (error) {
            xhsError.textContent = `文案生成失败: ${error.message}`;
            xhsError.style.display = 'block';
        } finally {
            xhsLoading.style.display = 'none';
        }
    };

    // --- Event Listeners ---
    fetchButton.addEventListener('click', loadBooks);
    searchButton.addEventListener('click', searchBooks);
    searchInput.addEventListener('keypress', (e) => e.key === 'Enter' && searchBooks());
    exportButton.addEventListener('click', () => {
        window.location.href = `/api/export/${listTypeSelect.value}`;
    });
    
    // Modal closing logic
    [closeModal, closeXhsModal].forEach(btn => btn.addEventListener('click', () => {
        bookModal.style.display = 'none';
        xhsModal.style.display = 'none';
    }));
    window.addEventListener('click', (e) => {
        if (e.target === bookModal) bookModal.style.display = 'none';
        if (e.target === xhsModal) xhsModal.style.display = 'none';
    });

    // --- Initial Load ---
    loadBooks();
});