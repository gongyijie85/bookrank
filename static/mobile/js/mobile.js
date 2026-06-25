/* BookRank 移动端交互脚本
   - 卡片点击下沉动效
   - CSRF token 懒加载（收藏等写操作时获取） */
'use strict';

(function () {
    // 卡片点击动效：通过 CSS :active 已实现，此处仅处理导航跳转
    document.addEventListener('click', function (e) {
        const card = e.target.closest('[data-href]');
        if (!card) return;
        const href = card.getAttribute('data-href');
        if (href) window.location.href = href;
    });

    // CSRF token 缓存（写操作前懒加载）
    let cachedCsrfToken = null;

    /**
     * 获取 CSRF token（懒加载，带缓存）
     * @returns {Promise<string>}
     */
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

    // 暴露给全局，供页面脚本调用
    window.MobileApp = {
        getCsrfToken: getCsrfToken,
        /** 获取 session_id（从 cookie） */
        getSessionId: function () {
            const m = document.cookie.match(/(?:^|; )session_id=([^;]*)/);
            return m ? m[1] : 'anonymous';
        }
    };
})();
