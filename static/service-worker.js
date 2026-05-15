const CACHE_NAME = 'nytimes-books-cache-v2';
const STATIC_ASSETS = [
    '/static/default-cover.png',
    '/static/css/all.min.css',
    '/static/js/utils.js',
    '/static/js/base.js',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.url.includes('/api/') && event.request.method === 'GET') {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return fetch(event.request)
                    .then((response) => {
                        cache.put(event.request, response.clone());
                        return response;
                    })
                    .catch(() => cache.match(event.request));
            })
        );
    } else if (event.request.url.includes('/cache/images/')) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.match(event.request)
                    .then((cachedResponse) => {
                        const fetchPromise = fetch(event.request).then((newResponse) => {
                            cache.put(event.request, newResponse.clone());
                            return newResponse;
                        });
                        return cachedResponse || fetchPromise;
                    });
            })
        );
    } else {
        event.respondWith(
            caches.match(event.request)
                .then((cachedResponse) => {
                    const fetchPromise = fetch(event.request).then((newResponse) => {
                        if (newResponse.ok) {
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, newResponse.clone());
                            });
                        }
                        return newResponse;
                    });
                    return cachedResponse || fetchPromise;
                })
        );
    }
});