# Feature: Device Notifications (Declarative Web Push)

_Status: New_

## What It Does

Users can enable native push notifications on their phones and desktops
(**Profile → Edit Your Information → Device Notifications**). Every Discord DM
the app sends — match scheduled/rescheduled, acknowledgment requests, crew
signups, seed URLs, watcher updates, volunteer reminders — is mirrored to the
user's subscribed devices, so iOS and Android users get notifications without
the Discord app installed.

The feature is **off until VAPID keys are configured** (see Setup); without
them the settings section hides itself and every send is a silent no-op.

## Why "Declarative" Web Push

Classic Web Push requires a service worker to wake up, parse the payload, and
call `showNotification()` — historically fragile on iOS, where the OS
aggressively kills workers. **Declarative Web Push** (WebKit, Safari/iOS
18.4+) removes the JavaScript hop: if the (decrypted) push payload is JSON of
the shape below, the browser renders the notification natively, with no
service worker involvement:

```json
{
  "web_push": 8030,
  "notification": {
    "title": "SGL On Site",
    "body": "Your match has been scheduled for 2026-07-04 18:00 EST",
    "navigate": "https://sgl.example.com/"
  }
}
```

`"web_push": 8030` is the magic member that opts the message into declarative
parsing; `title` and `navigate` (the URL opened on tap) are required.

The same payload is **backwards compatible**: browsers without declarative
support (Chrome, Android, Firefox) fire the classic `push` event, and the
handler in [`static/sw.js`](../../static/sw.js) renders the identical JSON via
`showNotification()`. One payload format serves every platform.

### Platform support

| Platform | Mechanism | Caveats |
|---|---|---|
| iOS / iPadOS 16.4+ | Web Push via home-screen web app | The app **must be added to the Home Screen** (Share → Add to Home Screen); Safari exposes no push API in a plain tab. 18.4+ renders declaratively; 16.4–18.3 uses the `sw.js` fallback. |
| Android (Chrome, etc.) | Classic Web Push via `sw.js` | Works in the browser and as an installed PWA. |
| macOS Safari 18.4+ | Declarative Web Push | Works for regular websites in-browser. |
| Desktop Chrome / Edge / Firefox | Classic Web Push via `sw.js` | |

## Architecture

```
DiscordService.send_dm  ──(mirror, never raises)──▶  WebPushService.mirror_dm
                                                            │ lookup subscriptions by discord_id
                                                            ▼
                                              encrypt (RFC 8291 aes128gcm)
                                              + VAPID JWT (RFC 8292)
                                                            │ httpx POST per device
                                                            ▼
                                              push service ──▶ device notification
```

- **Send path.** `DiscordService.send_dm` is the chokepoint every notification
  fan-out flows through (match lifecycle, crew, watchers, volunteers, seeds),
  so mirroring there gives device notifications exactly the coverage DMs have —
  including future notification types, with no per-call-site wiring. The mirror
  is **enqueued fire-and-forget onto the event dispatch worker**, so neither
  the serial `discord_queue` worker nor a UI handler awaiting `send_dm` inline
  (the admin Send Message dialog) ever waits on push-service round-trips. It
  fires before the bot-readiness checks (pushes still go out when the bot is
  down), never raises, and creates no coroutine at all while VAPID is
  unconfigured. Corollaries: recipients are filtered by the existing
  `User.dm_notifications` flag upstream, so pushes follow the DM opt-in; and a
  `(False, ...)` return from `send_dm` means the *Discord* send failed —
  subscribed devices may already have been notified, so re-sending after a
  failure can double-notify them. **Mock mode sends nothing**:
  `MockDiscordService.send_dm` deliberately skips the mirror so
  [`MOCK_DISCORD`](mock-discord.md) keeps its no-external-side-effects
  guarantee (a dev with a prod DB snapshot and prod VAPID keys must not push
  to real phones).
- **Protocol.** Implemented natively (no `pywebpush`, which is
  blocking/`requests`-based) in
  [`application/utils/web_push.py`](../../application/utils/web_push.py):
  `aes128gcm` payload encryption per RFC 8291 (pinned to the spec's Appendix A
  test vector in tests) and ES256 VAPID authorization per RFC 8292, using the
  already-present `cryptography` package. Delivery goes through a shared
  `httpx.AsyncClient` (keep-alive to the push hosts, closed in the app
  lifespan), devices are delivered concurrently, VAPID headers are cached per
  push-service origin for the token lifetime, and the per-message encryption
  runs in a worker thread off the event loop.
- **Subscription lifecycle.** Push services answer `404`/`410` for dead
  subscriptions; `WebPushService` prunes the row on either status. Users can
  also remove devices from the settings UI.
- **Subscribing (client).** Browser permission prompts must happen inside the
  click gesture (Safari enforces this), so the enable/disable buttons in
  [`pages/home_tabs/web_push_section.py`](../../pages/home_tabs/web_push_section.py)
  run [`static/js/web-push.js`](../../static/js/web-push.js) client-side via
  NiceGUI `js_handler` and report back through `emitEvent` → `ui.on`. The
  helper prefers `window.pushManager` (declarative, no service worker) and
  falls back to the service-worker registration's `pushManager`. On iOS
  without home-screen install it reports `ios_needs_install`, which the UI
  turns into instructions.

## Key Files

| File | Role |
|---|---|
| `models.py` → `WebPushSubscription` | User × device: `endpoint` (unique), `p256dh`, `auth`, `user_agent` |
| `application/repositories/web_push_repository.py` | Data access; endpoint upsert re-binds a device to the latest user |
| `application/services/web_push_service.py` | Subscribe/unsubscribe (audited), DM mirror, encrypted delivery, pruning |
| `application/utils/web_push.py` | Pure protocol: RFC 8291 encryption, RFC 8292 VAPID, key generation |
| `application/services/discord_service.py` | `send_dm` calls `_mirror_dm_to_web_push` (real and mock service) |
| `pages/home_tabs/web_push_section.py` | Settings UI: enable/disable buttons, subscribed-device list |
| `static/js/web-push.js` | Client-side subscribe/unsubscribe/status helpers |
| `static/sw.js` | `push` + `notificationclick` handlers for non-declarative browsers |
| `scripts/generate_vapid_keys.py` | One-time VAPID keypair generation |

## Setup

1. Generate a keypair once: `poetry run python scripts/generate_vapid_keys.py`
2. Set in the environment (see [deployment.md](../deployment.md)):
   - `VAPID_PRIVATE_KEY` — base64url raw 32-byte P-256 scalar. **Keep secret
     and stable**: rotating it silently invalidates every existing
     subscription.
   - `VAPID_SUBJECT` — `mailto:` or `https:` contact sent to push services;
     defaults to `BASE_URL` when that is https.
3. Users enable notifications per device from their profile page.

Web Push requires a secure context: `https://` in production (`localhost` is
exempt for development).

## Audit

`web_push.subscribed` / `web_push.unsubscribed` (`AuditActions`), actor = the
user, details = subscription id + endpoint host (full endpoints are
capability URLs and are not logged).

## Limitations / Future Work

- **Pushes follow the DM opt-in.** A user with `dm_notifications` off gets
  neither DMs nor pushes. Decoupling (push-only users) means moving recipient
  filtering out of the DM fan-out — the natural follow-up is an event-bus
  subscriber with its own preference model.
- **`navigate` always opens the home page** — there are no per-match deep-link
  pages yet.
- **`pushsubscriptionchange` is not handled**: if a push service rotates a
  subscription, the old row 410-prunes and the user re-enables manually.
- **Interactive DM buttons don't translate**: pushes mirror the DM text only;
  acknowledge/signup actions still happen in Discord or the web UI.
- **A failed DM does not mean an unsent push**: the mirror is independent of
  the Discord send, so retrying a "Failed to send message" (e.g. bot down)
  re-notifies subscribed devices.
- **Markdown stripping covers `**` only** — the only token the DM templates
  emit. New template markdown needs `_MARKDOWN_TOKENS` updated (blindly
  stripping more would corrupt usernames/URLs containing `__` or backticks).

## Tests

[`tests/test_web_push_protocol.py`](../../tests/test_web_push_protocol.py)
(RFC 8291 Appendix A byte-exact vector, round-trip decrypt, VAPID JWT
signature verification) and
[`tests/services/test_web_push_service.py`](../../tests/services/test_web_push_service.py)
(config gating, subscription CRUD/auth/audit, declarative payload contents,
410 pruning, mirror never-raises).
