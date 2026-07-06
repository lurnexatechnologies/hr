const CACHE_NAME = 'lurnexa-hrms-cache-v1';
const OFFLINE_URL = '/offline/';

// Assets to cache immediately on installation
const ASSETS_TO_CACHE = [
  OFFLINE_URL,
  '/static/img/namelesslogolurnexa.png?v=2',
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
    })
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

  // Check if it's a page navigation request
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .catch(() => {
          // If network fails, return cached offline page
          return caches.match(OFFLINE_URL);
        })
    );
  } else {
    // For static files (CSS, JS, images, fonts), try cache first, fall back to network
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((networkResponse) => {
          // Don't cache dynamic pages, only cache static assets
          if (event.request.url.includes('/static/')) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        });
      })
    );
  }
});
