# Engagement Telemetry

Captures **how people actually use the tool** — page views, feature
interactions, and a mirror of every domain event — so post-event analysis can
go beyond the in-app [feedback](feedback.md) form. It answers "which pages and
reports did people use, how often, and who was active?" rather than "what
deliberate admin action was taken" (that is [audit logging](audit-logging.md)).

Source: model `TelemetryEvent` in [`models.py`](../../models.py);
[`application/services/telemetry_service.py`](../../application/services/telemetry_service.py);
[`application/repositories/telemetry_repository.py`](../../application/repositories/telemetry_repository.py);
report at [`pages/admin_tabs/reports/telemetry.py`](../../pages/admin_tabs/reports/telemetry.py).

## Data captured

Every row is one `TelemetryEvent` (append-only; see the
[schema](../reference/data-model.md#telemetryevent)). The load-bearing columns:

| Column | Meaning |
|---|---|
| `category` | `page` (a page load), `interaction` (a curated UI action), or `domain` (a bus event) |
| `event_type` | `page.view`, `report.viewed`, `report.exported`, or the `EventType` string for domain rows |
| `path` | the route/report the event happened on (null for domain events) |
| `session_id` | the NiceGUI `app.storage.browser` id — lets a single user's activity be reconstructed as an ordered session |
| `user` | resolved actor FK (`SET_NULL`); `username` is also snapshotted into `details` so attribution survives a user deletion |
| `details` | JSON: page query params, event payload |

`user` is resolved even for **deactivated** accounts — telemetry is about who
did something, not who may still act — which is why capture resolves the user
directly rather than through `get_user_from_discord_id` (that helper hides
inactive users on purpose for authorization).

## Three capture points

All capture is **best-effort and non-blocking**: a telemetry failure is logged
and swallowed so it can never break a page render or a mutating call. All three
honor the `TELEMETRY_ENABLED` kill-switch.

1. **Domain-event mirror** — `TelemetryService.record_event` is registered on
   the [event bus](event-system.md) as an async subscriber in the `main.py`
   lifespan (`event_bus.subscribe_async(TelemetryService().record_event)`, no
   `event_types` filter). Every published `Event` becomes a `domain` row on the
   dispatch worker, off the request path. This piggybacks on events services
   already publish — no new instrumentation in the domain services.
2. **Page views** — the `protected_page` decorator
   ([`middleware/auth.py`](../../middleware/auth.py)) records a `page.view` for
   every authenticated page load. It reads the session identity + browser id
   during page building and hands the write to `background_tasks.create`.
   (Unauthenticated users are redirected by `AuthMiddleware` before the page
   function runs, so only real usage is captured.)
3. **Interactions** — presentation code calls `TelemetryService.track_interaction`
   for specific high-value actions. Currently wired: `report.viewed` in the
   reports dispatcher (fired only for an explicit `?report=` so a plain `/admin`
   load — where all tab panels render eagerly — does not manufacture a view).
   To add another, call `track_interaction(event_type=…, path=…, discord_id=…,
   session_id=…)` from the presentation layer, reading identity from
   `app.storage`.

## Why not just reuse the event bus / audit log?

- **Event bus** carries an **external contract** (`EventType.ALL`) that webhook
  subscribers match on. Routing high-volume page views/clicks through it would
  flood webhook receivers and bloat that contract. Telemetry instead *consumes*
  the bus (mirrors domain events) and captures engagement events on its own
  side channel that only it reads.
- **AuditLog** is a deliberate, low-volume record of privileged actions. Mixing
  high-volume behavioral signal into it would drown the audit trail and change
  its meaning. `TelemetryEvent` is a separate append-only table with its own
  aggregation indexes.

## The report

`Reports → Engagement Telemetry` (Staff only). Reads are Staff-gated at the
service boundary (mirroring `WebhookService`); the page also pre-checks so a
non-Staff admin gets a clear message rather than a raw error. It shows, for the
selected date window:

- **KPIs** — total events, unique users, unique sessions, page views.
- **Leaderboards** — most-viewed pages (with distinct users), most-frequent
  events, most-active users (with distinct sessions; click to filter).
- **Raw event log** — filterable (category, path substring, user) and
  server-paginated, with expandable JSON details and CSV export.

Aggregations run in the database (`GROUP BY` / `COUNT DISTINCT` via
`TelemetryRepository`), never by loading the table into memory.

## Configuration

`TELEMETRY_ENABLED` (default on) is a runtime kill-switch for **capture** — set
it to `0`/`false`/`no`/`off` to stop recording without a code change. Reads are
unaffected; the report just shows whatever was already captured. See the
[env-var table](../deployment.md#environment-variables).

## Tests

[`tests/services/test_telemetry_service.py`](../../tests/services/test_telemetry_service.py):
the three capture paths (including the disabled no-op and anonymous fallback),
the aggregation SQL against SQLite, list/count filters, and the Staff-only read
boundary.
