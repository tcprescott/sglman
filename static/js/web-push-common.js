// Shared between the page helper (static/js/web-push.js) and the service worker
// (static/sw.js), so it attaches to `self` rather than `window`.
//
// The service worker's 'pushsubscriptionchange' handler wakes with no page and
// no session, and the browser is not obliged to hand it the retired
// subscription's keys — Chrome has shipped that event with both
// oldSubscription and newSubscription null. So everything the worker needs to
// re-subscribe (the application server key) and to prove to the server which
// subscription it is rotating (the old auth secret) has to already be on disk
// when the event fires. This is that disk: the page writes the record the
// moment a user subscribes, the worker reads it much later.

self.wizWebPushKey = function (base64url) {
  const padded = base64url + '='.repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

self.wizWebPushStore = (() => {
  const DB_NAME = 'wiz-web-push';
  const STORE = 'state';
  const KEY = 'subscription';

  function open() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function run(mode, action) {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const request = action(db.transaction(STORE, mode).objectStore(STORE));
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    } finally {
      db.close();
    }
  }

  // Every method is best-effort: private-browsing modes and storage-pressure
  // eviction can make IndexedDB unavailable, and none of this is worth failing
  // a subscribe (or an unrelated push) over.
  return {
    async load() {
      try {
        return (await run('readonly', (store) => store.get(KEY))) || null;
      } catch (e) {
        return null;
      }
    },
    async save(record) {
      try {
        await run('readwrite', (store) => store.put(record, KEY));
      } catch (e) { /* rotation will fall back to whatever the event carries */ }
    },
    async clear() {
      try {
        await run('readwrite', (store) => store.delete(KEY));
      } catch (e) { /* stale record is harmless: rotation authenticates on it */ }
    },
  };
})();
