// ══════════════════════════════════════
// مُراسِل — Service Worker
// Cache Strategy: App Shell = Cache-First, API = Stale-While-Revalidate
// ══════════════════════════════════════

const CACHE_NAME = 'murrasil-v2';
const APP_SHELL = [
    '/',
    '/static/index.html',
    '/static/style.css',
    '/static/app.js',
    '/static/manifest.json',
];

// Install: Pre-cache app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('[SW] Pre-caching app shell');
            return cache.addAll(APP_SHELL);
        })
    );
    self.skipWaiting();
});

// Activate: Clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(names => {
            return Promise.all(
                names
                    .filter(name => name !== CACHE_NAME)
                    .map(name => caches.delete(name))
            );
        })
    );
    self.clients.claim();
});

// Fetch: Strategy based on request type
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests
    if (event.request.method !== 'GET') return;

    // API requests: Network-first with cache fallback
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    // Clone and cache the response
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, clone);
                    });
                    return response;
                })
                .catch(() => {
                    // Fallback to cache when offline
                    return caches.match(event.request);
                })
        );
        return;
    }

    // Static assets & pages: Cache-first
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) {
                // Return cached, but also update in background
                fetch(event.request).then(response => {
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, response);
                    });
                }).catch(() => {});
                return cached;
            }

            // Not cached: fetch from network
            return fetch(event.request).then(response => {
                // Only cache same-origin resources
                if (url.origin === location.origin) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            });
        })
    );
});
