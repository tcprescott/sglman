// Minimal service worker for SGL On Site.
//
// This exists solely to satisfy Android/Chrome's PWA installability requirement:
// the "Install app" / "Add to Home screen" prompt is only offered when a service
// worker with a fetch handler is registered. It deliberately caches NOTHING —
// every request passes straight through to the network, so the app is always
// fresh and there is no stale-asset class of bug to reason about.

self.addEventListener('install', () => {
  // Activate immediately instead of waiting for existing tabs to close.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Take control of any already-open pages as soon as we activate.
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Network-only pass-through: no caching, ever.
  event.respondWith(fetch(event.request));
});
