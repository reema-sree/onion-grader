// Kisan Setu Service Worker (PWA Offline-First App Shell Caching)
const CACHE_NAME = 'kisan-setu-v2.0';
const APP_SHELL = [
  '/',
  '/static/index.html',
  '/static/styles.css',
  '/static/i18n.js',
  '/static/api.js',
  '/static/app.js',
  '/static/db.js',
  '/static/grading_engine.js',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[ServiceWorker] Caching Kisan Setu app shell...');
      return cache.addAll(APP_SHELL);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[ServiceWorker] Removing old cache:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // For navigation and static files, use Cache-First with Network Fallback
  if (event.request.mode === 'navigate' || url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        }).catch(() => caches.match('/static/index.html'));
      })
    );
    return;
  }

  // For API calls, use Network-First
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
