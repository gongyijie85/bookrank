/* BookRank 移动端交互脚本
   - 卡片点击导航
   - CSRF token 懒加载
   - Toast 通知
   - 30 秒轮询（周报生成） */
'use strict';

(function () {
    // ===== 1. 卡片点击导航 =====
    document.addEventListener('click', function (e) {
        if (e.target.closest('select, input, button')) {
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

    // ===== 4. 周报生成轮询 =====
    let pollingTimer = null;
    function startPolling(intervalMs) {
        if (pollingTimer) clearInterval(pollingTimer);
        pollingTimer = setInterval(function () {
            fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function () { window.location.reload(); })
                .catch(function () {});
        }, intervalMs || 30000);
    }

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
