const CACHE_NAME = 'kyro-people-cache-v10';
const OFFLINE_URL = '/offline/';

// Assets to cache immediately on installation
const ASSETS_TO_CACHE = [
  OFFLINE_URL,
  '/manifest.json?v=10',
  '/static/img/kyro-logo-192.png',
  '/static/img/kyro-logo-512.png',
  '/static/img/kyro-logo.png',
  '/static/vendor/google-fonts/inter.css',
  '/static/vendor/bootstrap/css/bootstrap.min.css',
  '/static/vendor/fontawesome/css/all.min.css',
  '/static/vendor/bootstrap/js/bootstrap.bundle.min.js',
  '/static/css/lurnexastyles.css?v=1.3'
];

// Install Event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Pre-caching offline page and static assets');
      return cache.addAll(ASSETS_TO_CACHE);
    }).catch(err => console.error('[Service Worker] Pre-cache failed:', err))
  );
  self.skipWaiting();
});

// Activate Event
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log('[Service Worker] Clearing old cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch Event
self.addEventListener('fetch', (event) => {
  // Only handle GET requests and local requests
  if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) {
    return;
  }

  const acceptHeader = event.request.headers.get('accept') || '';
  const isHtmlPage = event.request.mode === 'navigate' || acceptHeader.includes('text/html');

  if (isHtmlPage) {
    // Network-First for HTML Pages
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          return response;
        })
        .catch(() => {
          console.warn('[Service Worker] Network failed for HTML page, serving offline fallback:', event.request.url);
          return caches.match(OFFLINE_URL).then(offlineRes => {
            return offlineRes || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
          });
        })
    );
  } else {
    // Cache-First for static assets (CSS, JS, images, fonts)
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((networkResponse) => {
          if (event.request.url.includes('/static/') && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        }).catch((err) => {
          console.warn('[Service Worker] Fetch failed for asset:', event.request.url);
          return new Response('', { status: 408, headers: { 'Content-Type': 'text/plain' } });
        });
      })
    );
  }
});
