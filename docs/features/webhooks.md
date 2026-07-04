# Webhooks

Staff configure outbound HTTP webhooks that fire when selected domain events
occur. When an event is published on the [event bus](event-system.md), the
webhook subscriber POSTs a **signed JSON body** to every enabled webhook whose
`event_types` include that event (or `'*'`).

Scope: **Staff-managed and global** — there are no per-user webhooks. All CRUD is
staff-gated; management lives in a single admin tab.

Source: [`application/services/webhook_service.py`](../../application/services/webhook_service.py),
models `Webhook` / `WebhookDelivery` in [`models.py`](../../models.py),
REST in [`api/routers/webhooks.py`](../../api/routers/webhooks.py),
UI in [`pages/admin_tabs/admin_webhooks.py`](../../pages/admin_tabs/admin_webhooks.py).

## Request format

Each delivery is `POST url` with a JSON body:

```json
{
  "event_type": "match.created",
  "occurred_at": "2026-07-03T23:25:33.739+00:00",
  "actor_id": 12,
  "actor_username": "alice",
  "data": { "match_id": 5, "tournament_id": 2, "player_ids": [1, 2] }
}
```

Headers:

| Header | Meaning |
|---|---|
| `X-SGL-Event` | The event name |
| `X-SGL-Delivery` | Unique delivery UUID |
| `X-SGL-Timestamp` | Unix seconds; part of the signed string (replay defense) |
| `X-SGL-Signature` | `sha256=<hex>` — HMAC-SHA256 of `"{timestamp}.{body}"` using the webhook secret |

### Verifying the signature (receiver side)

```python
import hmac, hashlib
signed = f"{request.headers['X-SGL-Timestamp']}.{raw_body}".encode()
expected = "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers['X-SGL-Signature'])
```

Sign the **raw body bytes** exactly as received — the app signs the exact bytes it
sends. Reject requests whose timestamp is too old to defend against replay.

## Delivery, retries, logging

- Runs on the event dispatch worker (off the request path), using
  `httpx.AsyncClient` with a 10s timeout.
- Bounded retry: up to `MAX_ATTEMPTS` (3) with exponential backoff (`2**attempt`
  seconds) on any non-2xx or transport error.
- Every delivery writes one `WebhookDelivery` row (final status, attempt count,
  success, error, `delivered_at`) for observability — visible in the admin tab's
  "Recent deliveries" view.

## Security

- **Secret**: `secrets.token_urlsafe(32)`, stored plaintext because it must be
  reproducible to sign each request. Shown **once** on create/regenerate; never
  returned by list/GET and never logged.
- **SSRF**: on create/update the URL must be `https://`; in production the host is
  resolved and rejected if it maps to loopback / RFC-1918 / link-local /
  `169.254.169.254` (cloud metadata). Outside production, `http://` and localhost
  are allowed so a developer can point at a local receiver.

## Managing webhooks

- **Admin UI**: Admin dashboard → **Webhooks** tab (Staff only). Add/edit (name,
  URL, event multiselect, active toggle), regenerate secret, view recent
  deliveries, delete.
- **REST**: `/api/webhooks` — `GET` (staff), `POST` (staff-write, returns the
  secret once), `GET/PUT/DELETE /{id}`, `POST /{id}/regenerate-secret`,
  `GET /{id}/deliveries`. See [rest-api.md](../reference/rest-api.md).

## Events available

Everything in `EventType.ALL` — match lifecycle (`match.created`, `match.updated`,
`match.rescheduled`, `match.seated/started/finished/confirmed`, `match.seed_rolled`,
`match.stream_candidate_set/_cleared`), crew (`crew.signup_created/signup_removed/
approval_changed/acknowledged`), and volunteer (`volunteer.assigned/unassigned/
acknowledged`). Select `*` to receive all events. See [event-system.md](event-system.md).

## Tests

[`tests/services/test_webhook_service.py`](../../tests/services/test_webhook_service.py)
(CRUD/auth/validation, HMAC signing, delivery logging, retry-then-give-up) and
[`tests/test_api_webhooks.py`](../../tests/test_api_webhooks.py) (endpoint auth,
CRUD, secret-once).
