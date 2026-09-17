/**
 * 封面地址规范化 + 冷缓存重试。
 *
 * 与 app/utils/cover_urls.py 的规则保持一致：境外图床国内不可直连，
 * 也不在 CSP img-src 白名单里，直接下发等于渲染占位图。统一改写成
 * 同源 /cover?src= 代理。
 *
 * /cover 热路径是 block=False：缓存未命中时立刻 302 到 default-cover.png
 * （见 app/routes/main.py:cover_proxy）。图片「成功」加载的是占位图，
 * error 事件不会触发。这里在 load 时识别占位图并隔一会再请求 /cover，
 * 等后台预取落盘后用户不用整页刷新。
 */
(function (root) {
    'use strict';

    const COVER_PROXY_PATH = '/cover';
    const DEFAULT_COVER = '/static/default-cover.png';
    const LOCAL_COVER_PREFIXES = ['/static/', '/cache/images/', COVER_PROXY_PATH];
    const RETRY_DELAYS_MS = [800, 2000, 5000, 12000];

    function coverToSrc(raw) {
        const value = (raw === null || raw === undefined) ? '' : String(raw).trim();
        if (!value) return '';
        if (LOCAL_COVER_PREFIXES.some(function (prefix) { return value.indexOf(prefix) === 0; })) {
            return value;
        }
        return COVER_PROXY_PATH + '?src=' + encodeURIComponent(value);
    }

    function originOf() {
        return (root.location && root.location.origin) || 'http://local.test';
    }

    function parseCoverUrl(url) {
        if (!url) return null;
        try {
            return url.charAt(0) === '/' ? new URL(url, originOf()) : new URL(url);
        } catch (err) {
            return null;
        }
    }

    function isSameOrigin(url, parsed) {
        return url.charAt(0) === '/' || parsed.origin === originOf();
    }

    function isPlaceholderSrc(url) {
        const parsed = parseCoverUrl(url);
        return !!parsed && parsed.pathname === DEFAULT_COVER && isSameOrigin(url, parsed);
    }

    function isProxySrc(url) {
        const parsed = parseCoverUrl(url);
        return !!parsed && parsed.pathname === COVER_PROXY_PATH && isSameOrigin(url, parsed);
    }

    function cleanProxySrc(src) {
        if (!src) return '';
        try {
            const u = new URL(src, originOf());
            u.searchParams.delete('_r');
            u.searchParams.delete('_t');
            if (src.charAt(0) === '/') return u.pathname + u.search;
            return u.toString();
        } catch (err) {
            return src;
        }
    }

    function withRetryQuery(src, attempt, now) {
        const u = new URL(src, originOf());
        u.searchParams.set('_r', String(attempt));
        u.searchParams.set('_t', String(now()));
        if (src.charAt(0) === '/') return u.pathname + u.search;
        return u.toString();
    }

    function resolveProxySrc(img) {
        if (img.dataset && img.dataset.coverProxy) return img.dataset.coverProxy;
        const attr = (img.getAttribute && img.getAttribute('src')) || img.src || '';
        const original = (img.getAttribute && img.getAttribute('data-original')) || '';
        if (isProxySrc(attr)) return cleanProxySrc(attr);
        if (isProxySrc(original)) return cleanProxySrc(original);
        if (isProxySrc(img.src)) return cleanProxySrc(img.src);
        return '';
    }

    function scheduleRetry(img, options) {
        if (!img) return false;
        const delays = (options && options.delays) || RETRY_DELAYS_MS;
        const wait = (options && options.setTimeout) || root.setTimeout;
        const now = (options && options.now) || function () { return Date.now(); };
        const current = img.currentSrc || img.src || '';
        if (!isPlaceholderSrc(current)) return false;
        const proxy = resolveProxySrc(img);
        if (!isProxySrc(proxy)) return false;
        const n = parseInt((img.dataset && img.dataset.coverRetryCount) || '0', 10);
        if (n >= delays.length) return false;
        if (img.dataset && img.dataset.coverRetrying === '1') return false;
        if (img.dataset) {
            img.dataset.coverProxy = proxy;
            img.dataset.coverRetrying = '1';
            img.dataset.coverRetryCount = String(n + 1);
        }
        wait(function () {
            if (img.dataset) img.dataset.coverRetrying = '';
            img.src = withRetryQuery(proxy, n, now);
        }, delays[n]);
        return true;
    }

    function bind(doc) {
        if (!doc || typeof doc.addEventListener !== 'function') return;
        if (bind.boundDocs && bind.boundDocs.indexOf(doc) !== -1) return;
        bind.boundDocs = bind.boundDocs || [];
        bind.boundDocs.push(doc);
        doc.addEventListener('load', function (e) {
            const el = e.target;
            if (!el || el.tagName !== 'IMG') return;
            scheduleRetry(el);
        }, true);
        if (!doc.querySelectorAll) return;
        const imgs = doc.querySelectorAll('img');
        for (let i = 0; i < imgs.length; i++) {
            if (imgs[i].complete) scheduleRetry(imgs[i]);
        }
    }

    root.BookRankCover = {
        toSrc: coverToSrc,
        isPlaceholderSrc: isPlaceholderSrc,
        isProxySrc: isProxySrc,
        scheduleRetry: scheduleRetry,
        bind: bind,
        DEFAULT_COVER: DEFAULT_COVER,
        RETRY_DELAYS_MS: RETRY_DELAYS_MS
    };
})(typeof window !== 'undefined' ? window : globalThis);
