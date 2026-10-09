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
        // 真实浏览器里，图片经 302 重定向后 currentSrc 仍保持原始代理 URL，
        // 因此不能靠“斜杠开头”判断同源——那会放行 //foreign.test 这类协议相对外链。
        // 只信任已解析出的绝对 origin（含合法的 protocol-relative 同源写法）。
        return parsed.origin === originOf();
    }

    function isPlaceholderSrc(url) {
        const parsed = parseCoverUrl(url);
        return !!parsed && parsed.pathname === DEFAULT_COVER && isSameOrigin(url, parsed);
    }

    function isProxySrc(url) {
        const parsed = parseCoverUrl(url);
        if (!parsed) return false;
        const origin = originOf();
        if (!origin || parsed.origin !== origin) return false;
        const path = parsed.pathname;
        return path === '/cover' || /^\/award-book\/\d+\/cover$/.test(path);
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
        // 默认行为不变：只有 currentSrc 已经是占位图才走同步重试调度。
        // 新增内部选项 confirmedPlaceholder=true —— 由严格校验过的 HEAD 探测确认
        // “代理 GET 因 302 落到占位图、但 currentSrc 仍是原代理 URL”这一真实缝隙时传入，
        // 让 scheduleRetry 在 currentSrc 非占位图的情况下也能继续后续守卫与重试。
        const confirmed = !!(options && options.confirmedPlaceholder);
        if (!confirmed && !isPlaceholderSrc(current)) return false;
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

    // 缓存热路径严格匹配：仅允许 /cache/images/<32 hex>.jpg，拒绝外部/双斜杠/malformed/query。
    const CACHE_PATH_RE = /^\/cache\/images\/[a-f0-9]{32}\.jpg$/;

    function isSafeCachePath(pathname) {
        return CACHE_PATH_RE.test(pathname);
    }

    // 每个 IMG 的 HEAD 探测去重标记 + pending 状态；失败/超时也要清理，不留永久标记。
    function probeProxyHead(img, proxy) {
        if (!root.fetch || typeof root.AbortController !== 'function') {
            // 环境不支持 fetch/AbortController：优雅降级，保留可用图片，不产生未处理 Promise。
            return;
        }
        if (img.dataset && img.dataset.coverProbing === '1') return; // dedup：同一张图并发 load 只发一次 HEAD
        // 已有排期中的重试则不再额外 HEAD，避免不必要的请求。
        if (img.dataset && img.dataset.coverRetrying === '1') return;
        const retryCount = img.dataset ? parseInt(img.dataset.coverRetryCount || '0', 10) : 0;
        if (retryCount > RETRY_DELAYS_MS.length) return;
        if (retryCount === RETRY_DELAYS_MS.length) {
            if (img.dataset && img.dataset.coverFinalProbed === '1') return;
            if (img.dataset) img.dataset.coverFinalProbed = '1';
        }

        const controller = new root.AbortController();
        const originalSrc = img.src; // 捕获发起探测时的源，用于忽略迟到的响应
        let settled = false;

        const nextGen = Number((img && img.dataset && img.dataset.coverProbeGeneration) || '0') + 1;
        if (img.dataset) {
            img.dataset.coverProbeGeneration = String(nextGen);
            img.dataset.coverProbing = '1'; // 先置 pending，再发请求
        }
        const capturedGen = nextGen;

        const timer = root.setTimeout(function () {
            settled = true;
            try { controller.abort(); } catch (err) { /* noop */ }
            cleanupProbe();
        }, 8000); // 硬上限 <=8s，超时即 abort 并清理，不做正向 pending 记录

        function cleanupProbe() {
            root.clearTimeout(timer);
            if (img.dataset && img.dataset.coverProbeGeneration === String(capturedGen)) {
                img.dataset.coverProbing = '';
            }
        }

        root.fetch(proxy, {
            method: 'HEAD',
            redirect: 'follow',
            credentials: 'same-origin',
            cache: 'no-store',
            signal: controller.signal
        }).then(function (response) {
            if (settled) return; // 已被超时/abort 接管
            settled = true;
            // 若期间该 IMG 已被换成别的封面，丢弃这次迟到结果，绝不覆盖新封面。
            if (img.src !== originalSrc) return;

            // 最终 URL 必须严格同源（parse 校验，不信字符串前缀）。
            const finalParsed = parseCoverUrl(response.url);
            if (!finalParsed || !isSameOrigin(response.url, finalParsed)) return;

            // 404 / 非 ok / 网络异常：不重试、不记 pending，清理后允许后续 load 再探测。
            if (!response.ok) return;

            // 情形 A：HEAD 跟随 302 落到了占位图 —— 证实了“currentSrc 仍是代理 URL、
            // 但实际渲染的是 default-cover”这条真实缝隙。用内部选项把确认信息交给
            // scheduleRetry，走既有 4 次有界重试，不改公共 API、不改目标 toSrc。
            if (isPlaceholderSrc(response.url)) {
                scheduleRetry(img, { confirmedPlaceholder: true });
                return;
            }

            // 情形 B：缓存已预热（real race：初始 GET 还在 302 到占位图时，后台已落盘）。
            // 仅当两个头都严格合规时，才把 src 一次性替换成安全的缓存公开路径。
            const sourceHeader = response.headers.get('X-Cover-Source');
            const pathHeader = response.headers.get('X-Cover-Path');
            if (sourceHeader === 'cache' && pathHeader && isSafeCachePath(pathHeader)) {
                img.src = pathHeader; // 之后该缓存图 load 时 currentSrc 已是缓存，不会再触发探测/重试
                return;
            }
            // 成功但未带有效头：不臆造 pending、不循环，直接结束本次探测。
        }).catch(function () {
            // 网络 reject / abort：NO retry、NO positive pending state，仅清理。
            if (settled) return;
            settled = true;
        }).finally(function () {
            cleanupProbe();
        });
    }

    function findNeutralPlaceholder(img) {
        let sibling = img.nextElementSibling;
        if (sibling && sibling.classList && (sibling.classList.contains('neutral-cover-placeholder') || sibling.classList.contains('m-neutral-cover-placeholder'))) {
            return sibling;
        }
        sibling = img.previousElementSibling;
        if (sibling && sibling.classList && (sibling.classList.contains('neutral-cover-placeholder') || sibling.classList.contains('m-neutral-cover-placeholder'))) {
            return sibling;
        }
        return null;
    }

    function applyNeutralCoverFeedback(img) {
        if (!img.dataset || img.dataset.neutralCoverFeedback !== '1') return false;
        const placeholder = findNeutralPlaceholder(img);
        const current = img.currentSrc || img.src || '';
        const parsed = parseCoverUrl(current);
        const isReal = !!parsed && isSameOrigin(current, parsed) && !isPlaceholderSrc(current) && !isProxySrc(current) && img.naturalWidth > 0;
        img.hidden = !isReal;
        if (placeholder) placeholder.hidden = isReal;
        return isReal;
    }

    function handleCoverLoad(img) {
        if (applyNeutralCoverFeedback(img)) return;

        // 旧分支保持不变：currentSrc 直接就是占位图时，同步走 scheduleRetry（此路无法 HEAD）。
        if (scheduleRetry(img)) return;

        // 新缝隙：load 事件里 currentSrc 仍是原始代理 URL（重定向不改 currentSrc），
        // 且该代理是同源合法封面路由 —— 做一次去重的 HEAD 探测来判定真实现状。
        const current = img.currentSrc || img.src || '';
        const parsed = parseCoverUrl(current);
        if (!parsed || !isSameOrigin(current, parsed)) return;
        if (!isProxySrc(current)) return;
        const proxy = resolveProxySrc(img);
        if (!isProxySrc(proxy)) return;
        probeProxyHead(img, proxy);
    }

    function bind(doc) {
        if (!doc || typeof doc.addEventListener !== 'function') return;
        if (bind.boundDocs && bind.boundDocs.indexOf(doc) !== -1) return;
        bind.boundDocs = bind.boundDocs || [];
        bind.boundDocs.push(doc);
        doc.addEventListener('load', function (e) {
            const el = e.target;
            if (!el || el.tagName !== 'IMG') return;
            handleCoverLoad(el);
        }, true);
        doc.addEventListener('error', function (e) {
            const el = e.target;
            if (!el || el.tagName !== 'IMG') return;
            if (el.dataset && el.dataset.neutralCoverFeedback === '1') {
                el.hidden = true;
                const placeholder = findNeutralPlaceholder(el);
                if (placeholder) placeholder.hidden = false;
            }
        }, true);
        if (!doc.querySelectorAll) return;
        const imgs = doc.querySelectorAll('img');
        for (let i = 0; i < imgs.length; i++) {
            if (imgs[i].complete) handleCoverLoad(imgs[i]);
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
