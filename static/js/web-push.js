// Client-side half of Device Notifications (Web Push).
//
// Subscribing MUST happen inside the click gesture (Safari refuses permission
// prompts outside one), so these helpers are called from NiceGUI js_handler
// click handlers and report back to the server via emitEvent().
//
// Declarative Web Push (Safari 18.4+ / iOS 18.4+) exposes a PushManager on
// window and needs no service worker; everywhere else the PushManager hangs
// off the service worker registration that theme/base.py installs on every
// page. On iOS the APIs only exist once the app is added to the Home Screen.
window.sglWebPush = {
  async _manager() {
    if (window.pushManager) return window.pushManager;
    if ('serviceWorker' in navigator) {
      // .ready never settles if registration failed; don't hang the caller.
      const reg = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise((resolve) => setTimeout(() => resolve(null), 3000)),
      ]);
      if (reg && reg.pushManager) return reg.pushManager;
    }
    return null;
  },

  _applicationServerKey(base64url) {
    const padded = base64url + '='.repeat((4 - (base64url.length % 4)) % 4);
    const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  },

  _isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  },

  async status() {
    const manager = await this._manager();
    if (!manager) {
      return { supported: false, ios: this._isIOS(), standalone: !!navigator.standalone };
    }
    let endpoint = null;
    try {
      const sub = await manager.getSubscription();
      endpoint = sub ? sub.endpoint : null;
    } catch (e) { /* treated as not subscribed */ }
    return {
      supported: true,
      permission: (typeof Notification !== 'undefined') ? Notification.permission : 'default',
      endpoint: endpoint,
    };
  },

  async subscribe(publicKey) {
    const manager = await this._manager();
    if (!manager) {
      return { error: this._isIOS() && !navigator.standalone ? 'ios_needs_install' : 'unsupported' };
    }
    try {
      const sub = await manager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this._applicationServerKey(publicKey),
      });
      return { subscription: sub.toJSON(), userAgent: navigator.userAgent };
    } catch (e) {
      if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
        return { error: 'permission_denied' };
      }
      if (e && e.name === 'NotAllowedError') {
        // Prompt dismissed (permission still 'default') or the user gesture
        // expired — not the hard "blocked in settings" state.
        return { error: 'permission_dismissed' };
      }
      return { error: String(e) };
    }
  },

  async unsubscribe() {
    const manager = await this._manager();
    if (!manager) return { endpoint: null };
    try {
      const sub = await manager.getSubscription();
      if (!sub) return { endpoint: null };
      const endpoint = sub.endpoint;
      await sub.unsubscribe();
      return { endpoint: endpoint };
    } catch (e) {
      return { endpoint: null, error: String(e) };
    }
  },
};
