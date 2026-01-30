/**
 * Service Worker - 缓存策略优化
 * 提供离线访问能力和性能优化
 */

const CACHE_NAME = 'bookrank-v1';
const STATIC_CACHE = 'bookrank-static-v1';
const IMAGE_CACHE = 'bookrank-images-v1';
const API_CACHE = 'bookrank-api-v1';

// 静态资源缓存列表
const STATIC_ASSETS = [
  '/',
  '/static/js/app.js',
  '/static/js/components.js',
  '/static/js/store.js',
  '/static/js/api.js',
  '/static/js/config.js',
  '/static/js/utils.js',
  '/static/default-cover.png'
];

// 安装时缓存静态资源
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .catch((err) => {
        console.error('[SW] Failed to cache static assets:', err);
      })
  );
  self.skipWaiting();
});

// 激活时清理旧缓存
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => {
            return name.startsWith('bookrank-') && 
                   name !== STATIC_CACHE && 
                   name !== IMAGE_CACHE && 
                   name !== API_CACHE;
          })
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    })
  );
  self.clients.claim();
});

// 拦截请求并应用缓存策略
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 策略1: 静态资源 - Cache First
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // 策略2: 图片资源 - Cache First with Network Fallback
  if (isImage(request)) {
    event.respondWith(cacheFirstWithNetworkFallback(request, IMAGE_CACHE));
    return;
  }

  // 策略3: API请求 - Network First with Cache Fallback
  if (isAPI(request)) {
    event.respondWith(networkFirstWithCacheFallback(request, API_CACHE));
    return;
  }

  // 策略4: 其他请求 - Network First
  event.respondWith(networkFirst(request));
});

/**
 * 判断是否为静态资源
 */
function isStaticAsset(url) {
  return url.pathname.startsWith('/static/') ||
         url.pathname === '/' ||
         url.pathname.endsWith('.js') ||
         url.pathname.endsWith('.css');
}

/**
 * 判断是否为图片
 */
function isImage(request) {
  return request.destination === 'image' ||
         request.url.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i);
}

/**
 * 判断是否为API请求
 */
function isAPI(request) {
  return request.url.includes('/api/');
}

/**
 * Cache First 策略
 * 优先从缓存获取，缓存未命中则请求网络并缓存
 */
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  
  if (cached) {
    console.log('[SW] Cache hit:', request.url);
    return cached;
  }

  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.error('[SW] Fetch failed:', error);
    // 返回离线页面或默认响应
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Cache First with Network Fallback
 * 优先缓存，同时后台更新缓存
 */
async function cacheFirstWithNetworkFallback(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  // 后台更新缓存
  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);

  // 立即返回缓存（如果有）
  return cached || fetchPromise;
}

/**
 * Network First with Cache Fallback
 * 优先网络，失败时回退到缓存
 */
async function networkFirstWithCacheFallback(request, cacheName) {
  const cache = await caches.open(cacheName);

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    throw error;
  }
}

/**
 * Network First 策略
 */
async function networkFirst(request) {
  try {
    return await fetch(request);
  } catch (error) {
    const cache = await caches.open(STATIC_CACHE);
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    throw error;
  }
}

/**
 * 后台同步 - 用于离线时的数据同步
 */
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-translations') {
    event.waitUntil(syncTranslations());
  }
});

async function syncTranslations() {
  // 同步离线时的翻译请求
  console.log('[SW] Syncing translations...');
}

/**
 * 推送通知支持
 */
self.addEventListener('push', (event) => {
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icon.png',
      badge: '/static/badge.png'
    })
  );
});

console.log('[SW] Service Worker loaded');
