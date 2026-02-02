document.addEventListener("DOMContentLoaded", () => {
    // 元素引用
    const booksContainer = document.getElementById("books-container");
    const categoryBtns = document.querySelectorAll(".category-btn");
    const loading = document.getElementById("loading");
    const emptyState = document.getElementById("empty-state");
    const status = document.getElementById("status");
    const searchInput = document.getElementById("search-input");
    const searchBtn = document.getElementById("search-btn");
    const exportBtn = document.getElementById("export-btn");

    // 当前选中的分类
    let currentCategory = "all";

    // 加载图书数据
    const loadBooks = async (category) => {
        // 显示加载状态
        booksContainer.innerHTML = "";
        loading.style.display = "block";
        emptyState.style.display = "none";
        status.textContent = `加载 ${category === "all" ? "全部图书" : getCategoryName(category)} 中...`;

        try {
            // 调用API
            const response = await fetch(`/api/books/${category}`);
            const data = await response.json();

            if (!data.success || !data.books) {
                throw new Error("获取数据失败");
            }

            // 渲染图书
            renderBooks(data.books, category);
            status.textContent = `加载完成（${getTotalBooks(data.books, category)}本）`;
        } catch (error) {
            console.error("加载失败:", error);
            emptyState.innerHTML = `<p>加载失败: ${error.message}</p><button onclick="loadBooks('${category}')">重试</button>`;
            emptyState.style.display = "block";
            status.textContent = "加载失败";
        } finally {
            loading.style.display = "none";
        }
    };

    // 渲染图书列表
    const renderBooks = (books, category) => {
        if (category === "all") {
            // 全部分类：按分类分组渲染
            for (const [catId, catBooks] of Object.entries(books)) {
                if (catBooks.length === 0) continue;
                
                // 添加分类标题
                const catTitle = document.createElement("h3");
                catTitle.className = "category-title";
                catTitle.textContent = CATEGORIES[catId];
                booksContainer.appendChild(catTitle);

                // 添加该分类的图书
                catBooks.forEach(book => {
                    booksContainer.appendChild(createBookCard(book));
                });
            }
        } else {
            // 单个分类：直接渲染
            if (books.length === 0) {
                emptyState.style.display = "block";
                return;
            }
            books.forEach(book => {
                booksContainer.appendChild(createBookCard(book));
            });
        }
    };

    // 创建图书卡片（新增分类显示）
    const createBookCard = (book) => {
        const card = document.createElement("div");
        card.className = "book-card";
        
        // 从list_name中提取分类名称（如"精装小说"）
        const categoryName = book.list_name || "未知分类";
        
        card.innerHTML = `
            <img src="${book.cover}" alt="${book.title}" class="book-cover">
            <div class="book-info">
                <h3 class="book-title">${book.title}</h3>
                <p class="book-author">作者: ${book.author}</p>
                <p class="book-meta">分类: ${categoryName}</p>  <!-- 新增分类显示 -->
                <p class="book-meta">排名: ${book.rank} | 上榜: ${book.weeks_on_list}周</p>  <!-- 修复weeks_on_list变量名 -->
                <p class="book-meta">出版社: ${book.publisher}</p>
                ${book.url ? `<a href="${book.url}" target="_blank" class="btn">查看详情</a>` : ""}
            </div>
        `;
        return card;
    };

    // 搜索图书
    const searchBooks = async () => {
        const keyword = searchInput.value.trim();
        if (!keyword) return;

        loading.style.display = "block";
        status.textContent = `搜索 "${keyword}" 中...`;
        booksContainer.innerHTML = "";
        emptyState.style.display = "none";

        try {
            const response = await fetch(`/api/search?keyword=${encodeURIComponent(keyword)}`);
            const data = await response.json();

            if (!data.success) {
                throw new Error(data.message || "搜索失败");
            }

            if (data.books.length === 0) {
                emptyState.textContent = `没有找到包含 "${keyword}" 的图书`;
                emptyState.style.display = "block";
                status.textContent = `搜索完成（0本）`;
            } else {
                data.books.forEach(book => {
                    booksContainer.appendChild(createBookCard(book));
                });
                status.textContent = `搜索完成（${data.books.length}本）`;
            }
        } catch (error) {
            console.error("搜索失败:", error);
            emptyState.innerHTML = `<p>搜索失败: ${error.message}</p>`;
            emptyState.style.display = "block";
        } finally {
            loading.style.display = "none";
        }
    };

    // 导出CSV
    const exportCSV = () => {
        const url = `/api/export/${currentCategory}`;
        window.open(url, "_blank");
        status.textContent = `正在导出 ${currentCategory === "all" ? "全部图书" : getCategoryName(currentCategory)}...`;
    };

    // 辅助函数：获取分类名称
    const getCategoryName = (categoryId) => {
        return window.CATEGORIES ? window.CATEGORIES[categoryId] : categoryId;
    };

    // 辅助函数：计算总图书数量
    const getTotalBooks = (books, category) => {
        if (category === "all") {
            return Object.values(books).reduce((total, catBooks) => total + catBooks.length, 0);
        }
        return books.length;
    };

    // 初始化分类数据（从后端获取）
    const initCategories = async () => {
        try {
            const response = await fetch("/api/categories");
            const data = await response.json();
            if (data.success) {
                window.CATEGORIES = data.categories;
            }
        } catch (error) {
            console.error("获取分类失败:", error);
            window.CATEGORIES = {};
        }
    };

    // 事件监听：分类切换
    categoryBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const category = btn.dataset.category;
            if (category === currentCategory) return;

            // 更新选中状态
            categoryBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentCategory = category;

            // 加载对应分类
            loadBooks(category);
            searchInput.value = ""; // 清空搜索框
        });
    });

    // 事件监听：搜索
    searchBtn.addEventListener("click", searchBooks);
    searchInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") searchBooks();
    });

    // 事件监听：导出
    exportBtn.addEventListener("click", exportCSV);

    // 初始化
    initCategories().then(() => {
        loadBooks(currentCategory);
    });
});