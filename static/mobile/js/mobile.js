/* BookRank 移动端交互脚本 v0.9.71
   - 卡片点击导航
   - CSRF token 懒加载
   - Toast 通知
   - Tab 切换
   - 筛选面板折叠
   - 分享按钮
   - 30 秒轮询（周报生成）
   - 统一收藏按钮处理 */
'use strict';

(function () {
    // ===== 1. 卡片点击导航 =====
    document.addEventListener('click', function (e) {
        // 收藏/分享按钮的点击不触发卡片导航
        if (e.target.closest('.m-fav-btn, .m-fav-remove, .m-share-btn, .m-filter-toggle, .m-tab-trigger, .m-filter-select, select, input, button')) {
            return;
        }
        const card = e.target.closest('[data-href]');
        if (!card) return;
        const href = card.getAttribute('data-href');
        if (href) window.location.href = href;
    });

    // ===== 2. CSRF token 缓存 =====
    let cachedCsrfToken = null;

    function getCsrfToken() {
        if (cachedCsrfToken) return Promise.resolve(cachedCsrfToken);
        return fetch('/api/csrf-token')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                cachedCsrfToken = (data && data.data && data.data.csrf_token) || '';
                return cachedCsrfToken;
            })
            .catch(function () { return ''; });
    }

    // ===== 3. Toast 通知 =====
    function toast(msg, type) {
        const container = document.getElementById('m-toast-container');
        if (!container) {
            // 兜底：若无容器，使用 alert
            alert(msg);
            return;
        }
        const el = document.createElement('div');
        el.className = 'm-toast' + (type ? ' ' + type : '');
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(function () {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.3s';
            setTimeout(function () {
                if (el.parentNode) el.parentNode.removeChild(el);
            }, 300);
        }, 2500);
    }

    // ===== 4. Tab 切换 =====
    document.addEventListener('click', function (e) {
        const trigger = e.target.closest('.m-tab-trigger');
        if (!trigger) return;
        const group = trigger.closest('.m-tab-group');
        if (!group) return;
        group.querySelectorAll('.m-tab-trigger').forEach(function (t) {
            t.classList.remove('active');
        });
        trigger.classList.add('active');
        const target = trigger.getAttribute('data-tab');
        group.querySelectorAll('.m-tab-panel').forEach(function (panel) {
            panel.classList.toggle('active', panel.getAttribute('data-tab') === target);
        });
    });

    // ===== 5. 筛选面板折叠 =====
    document.addEventListener('click', function (e) {
        const toggle = e.target.closest('.m-filter-toggle');
        if (!toggle) return;
        e.preventDefault();
        const target = toggle.getAttribute('data-target');
        const panel = target ? document.getElementById(target) : null;
        if (panel) {
            panel.classList.toggle('show');
            toggle.classList.toggle('expanded', panel.classList.contains('show'));
        }
    });

    // ===== 6. 分享按钮 =====
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.m-share-btn');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const url = btn.getAttribute('data-url') || window.location.href;
        const title = btn.getAttribute('data-title') || document.title;
        if (navigator.share) {
            navigator.share({ title: title, url: url }).catch(function () {});
        } else if (navigator.clipboard) {
            navigator.clipboard.writeText(url).then(function () {
                toast('链接已复制', 'success');
            }, function () {
                toast('复制失败，请手动复制', 'error');
            });
        } else {
            toast('当前浏览器不支持分享', 'error');
        }
    });

    // ===== 7. 统一收藏按钮处理（事件委托） =====
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.m-fav-btn[data-isbn]:not(#m-fav-btn)');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const isbn = btn.getAttribute('data-isbn');
        if (!isbn) return;
        const active = btn.classList.contains('active');
        getCsrfToken().then(function (token) {
            const method = active ? 'DELETE' : 'POST';
            const url = active
                ? '/api/favorites/' + encodeURIComponent(isbn)
                : '/api/favorites';
            const opts = {
                method: method,
                headers: { 'X-CSRF-Token': token }
            };
            if (!active) {
                opts.headers['Content-Type'] = 'application/json';
                opts.body = JSON.stringify({ isbn: isbn });
            }
            fetch(url, opts)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data && data.success) {
                        btn.classList.toggle('active', !active);
                        const span = btn.querySelector('span');
                        if (span) span.textContent = active ? '收藏' : '已收藏';
                        toast(active ? '已取消收藏' : '已加入收藏', 'success');
                    } else {
                        toast(data && data.message ? data.message : '操作失败', 'error');
                    }
                })
                .catch(function () { toast('网络错误', 'error'); });
        });
    });

    // ===== 8. 周报生成轮询 =====
    let pollingTimer = null;
    function startPolling(intervalMs) {
        if (pollingTimer) clearInterval(pollingTimer);
        pollingTimer = setInterval(function () {
            fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function () { window.location.reload(); })
                .catch(function () {});
        }, intervalMs || 30000);
    }

    // ===== 9. 周报列表日期 + 搜索筛选（前端过滤） =====
    let _reportDateFilter = '';
    let _reportSearchFilter = '';

    function _applyReportFilters() {
        const now = new Date();
        const items = document.querySelectorAll('.m-report-list > [data-report-date]');
        const kw = _reportSearchFilter.trim().toLowerCase();
        items.forEach(function (item) {
            const dateStr = item.getAttribute('data-report-date');
            const title = (item.getAttribute('data-report-title') || '').toLowerCase();
            const summary = (item.getAttribute('data-report-summary') || '').toLowerCase();
            let show = true;
            // 日期筛选
            if (dateStr && _reportDateFilter) {
                const d = new Date(dateStr);
                if (_reportDateFilter === 'month') {
                    show = d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
                } else if (_reportDateFilter === 'last_month') {
                    const lm = new Date(now.getFullYear(), now.getMonth() - 1, 1);
                    show = d.getMonth() === lm.getMonth() && d.getFullYear() === lm.getFullYear();
                } else if (_reportDateFilter === 'year') {
                    show = d.getFullYear() === now.getFullYear();
                }
            }
            // 搜索筛选
            if (show && kw) {
                show = title.indexOf(kw) >= 0 || summary.indexOf(kw) >= 0;
            }
            item.style.display = show ? '' : 'none';
        });
    }

    window.filterByDate = function (filter) {
        _reportDateFilter = filter || '';
        _applyReportFilters();
    };

    window.filterBySearch = function (keyword) {
        _reportSearchFilter = keyword || '';
        _applyReportFilters();
    };

    // 兼容旧调用
    window.filterReports = window.filterByDate;

    // ===== 暴露 API =====
    window.MobileApp = {
        getCsrfToken: getCsrfToken,
        toast: toast,
        startPolling: startPolling,
        getSessionId: function () {
            const m = document.cookie.match(/(?:^|; )session_id=([^;]*)/);
            return m ? m[1] : 'anonymous';
        }
    };
})();
