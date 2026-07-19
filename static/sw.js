// Minimal service worker for Wizzrobe.
//
// Two jobs, deliberately nothing more:
//
// 1. Satisfy Android/Chrome's PWA installability requirement: the "Install
//    app" / "Add to Home screen" prompt is only offered when a service worker
//    with a fetch handler is registered. It caches NOTHING — every request
//    passes straight through to the network, so the app is always fresh and
//    there is no stale-asset class of bug to reason about.
//
// 2. Display Web Push messages on browsers without Declarative Web Push
//    (Chrome/Android). The server always sends the declarative JSON shape
//    ({web_push: 8030, notification: {...}}); Safari 18.4+/iOS 18.4+ renders
//    it natively without ever waking this worker, while the handlers below
//    render the same payload everywhere else.

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

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { notification: { body: event.data ? event.data.text() : '' } };
  }
  const n = data.notification || {};
  event.waitUntil(self.registration.showNotification(n.title || 'Wizzrobe', {
    body: n.body || '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    lang: n.lang,
    dir: n.dir,
    silent: !!n.silent,
    data: { navigate: n.navigate || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL((event.notification.data || {}).navigate || '/', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const win of windows) {
      if (win.url === target && 'focus' in win) return win.focus();
    }
    return self.clients.openWindow(target);
  })());
});
