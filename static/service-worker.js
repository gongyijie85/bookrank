const CACHE_NAME = 'nytimes-books-cache-v1';
const STATIC_ASSETS = [
    '/',
    '/static/default-cover.png',
    '/static/manifest.json',
    '/templates/index.html'
];

// 安装Service Worker：缓存静态资源
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// 激活：清理旧缓存
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((name) => {
                    if (name !== CACHE_NAME) {
                        return caches.delete(name);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

//  fetch事件：优先从缓存获取，失败则请求网络
self.addEventListener('fetch', (event) => {
    // 对API请求特殊处理（只缓存GET请求）
    if (event.request.url.includes('/api/') && event.request.method === 'GET') {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return fetch(event.request)
                    .then((response) => {
                        // 更新缓存
                        cache.put(event.request, response.clone());
                        return response;
                    })
                    .catch(() => {
                        // 网络失败时返回缓存
                        return cache.match(event.request);
                    });
            })
        );
    } 
    // 图片缓存
    else if (event.request.url.includes('/cache/images/')) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.match(event.request)
                    .then((response) => {
                        // 缓存优先，同时后台更新
                        const fetchPromise = fetch(event.request).then((newResponse) => {
                            cache.put(event.request, newResponse.clone());
                            return newResponse;
                        });
                        return response || fetchPromise;
                    });
            })
        );
    }
    // 其他静态资源
    else {
        event.respondWith(
            caches.match(event.request)
                .then((response) => {
                    // 缓存优先，同时后台请求网络更新
                    const fetchPromise = fetch(event.request).then((newResponse) => {
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, newResponse.clone());
                        });
                        return newResponse;
                    });
                    return response || fetchPromise;
                })
        );
    }
});