# Device Notifications (Web Push)

Users enable native push notifications per device from **Profile → Edit Your
Information → Device Notifications**. Every Discord DM the app sends — match
scheduled/rescheduled, acknowledgment requests, crew signups, seed URLs, watcher
updates, volunteer reminders — is mirrored to that user's subscribed devices, so
iOS and Android users get notified without the Discord app installed.

The feature is **off until VAPID keys are configured** (see Setup); without them
the settings section hides itself and every send is a silent no-op.

## One payload, two rendering paths

The encrypted payload is JSON in WebKit's **Declarative Web Push** shape:

```json
{
  "web_push": 8030,
  "notification": {
    "title": "Wizzrobe",
    "body": "Your match has been scheduled for 2026-07-04 18:00 EST",
    "navigate": "https://wizzrobe.example.com/"
  }
}
```

`"web_push": 8030` is the magic member that opts the message into declarative
parsing (Safari/iOS 18.4+ renders it with no service worker); `title` and
`navigate` are required. Browsers without declarative support fire the classic
`push` event and [`static/sw.js`](../../static/sw.js) renders the *same* JSON via
`showNotification()`, so there is one payload format for every platform.

The one platform caveat that changes what a user must do: on **iOS/iPadOS the app
must be added to the Home Screen** — Safari exposes no push API in a plain tab.

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
  fan-out flows through (match lifecycle, crew, watchers, volunteers, seeds), so
  mirroring there gives device notifications exactly the coverage DMs have, future
  notification types included, with no per-call-site wiring. The mirror is
  **enqueued fire-and-forget onto the event dispatch worker**, so neither the
  serial `discord_queue` nor a UI handler awaiting `send_dm` inline ever waits on
  push-service round-trips. It fires *before* the bot-readiness checks (pushes
  still go out when the bot is down), never raises, and creates no coroutine at
  all while VAPID is unconfigured. Two corollaries: recipients are filtered
  upstream by `User.dm_notifications`, so **pushes follow the DM opt-in**; and a
  `(False, ...)` return from `send_dm` means the *Discord* send failed — devices
  may already have been notified, so re-sending can double-notify them.
- **Mock mode sends nothing.** `MockDiscordService.send_dm` deliberately skips the
  mirror so [`MOCK_DISCORD`](discord.md#mock-mode) keeps its
  no-external-side-effects guarantee: a dev with a prod DB snapshot and prod VAPID
  keys must not push to real phones.
- **Protocol.** Implemented natively on `cryptography` (not `pywebpush`, which is
  blocking/`requests`-based) in
  [`application/utils/web_push.py`](../../application/utils/web_push.py):
  `aes128gcm` encryption per RFC 8291 and ES256 VAPID authorization per RFC 8292.
  Delivery uses a shared `httpx.AsyncClient` (keep-alive, closed in the app
  lifespan) with devices delivered concurrently, VAPID headers cached per
  push-service origin for the token lifetime, and encryption run in a worker
  thread off the event loop.
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

Source: model `WebPushSubscription` in [`models/user.py`](../../models/user.py)
(user × device: unique `endpoint`, `p256dh`, `auth`, `user_agent`; the repository's
endpoint upsert re-binds a device to the latest user),
[`web_push_service.py`](../../application/services/web_push_service.py),
[`application/utils/web_push.py`](../../application/utils/web_push.py),
[`pages/home_tabs/web_push_section.py`](../../pages/home_tabs/web_push_section.py),
[`static/js/web-push.js`](../../static/js/web-push.js),
[`static/sw.js`](../../static/sw.js),
[`scripts/generate_vapid_keys.py`](../../scripts/generate_vapid_keys.py).

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

## Limitations

- **`navigate` always opens the home page** — there are no per-match deep-link
  pages yet.
- **`pushsubscriptionchange` is not handled**: if a push service rotates a
  subscription, the old row 410-prunes and the user re-enables manually.
- **Interactive DM buttons don't translate**: pushes mirror the DM text only;
  acknowledge/signup actions still happen in Discord or the web UI.
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
