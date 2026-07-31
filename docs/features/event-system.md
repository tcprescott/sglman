# Event System

An in-process publish/subscribe bus. Services publish a domain **event** after
they commit a change; any number of subscribers react. The publishing rules —
publish after commit, prefer `write_and_publish`, `EventType` names are an
external contract — are in CLAUDE.md; this doc is the machinery.

Source: [`application/events/`](../../application/events/). The package sits at the
`application/` root as a peer of `services/`, so both publishers (services) and
subscribers (presentation) can import it with no cycle.

## Pieces

| Module | Role |
|---|---|
| `event.py` | The immutable `Event` value object: `event_type`, `payload`, snapshotted `actor_id`/`actor_username`/`tenant_id`, `occurred_at` (UTC). `Event.create(type, payload, actor)` builds one; `to_wire()` is the JSON shape delivered to webhooks. |
| `event_types.py` | `EventType` — the `object.verb` name registry (mirrors `AuditActions`). `EventType.ALL` drives the webhook UI multiselect + validation; `'*'` is the wildcard. |
| `dispatch_queue.py` | A background worker (clone of `discord_queue`) that runs async subscribers off the request path. |
| `bus.py` | The core: `subscribe_sync`, `subscribe_async`, `unsubscribe`, `publish`. |
| `match_live.py` | The narrow predecessor: `(match_id, change_type)` nudges to open UI views. Deliberately **not** re-exported from `__init__.py`, so reaching for it takes an explicit `from application.events import match_live` and can never be mistaken for the bus. |

## Two kinds of subscriber

- **Sync** (`subscribe_sync`) run **inline** during `publish` and must be fast and
  non-blocking — schedule work, never await. This is the fast path for UI
  live-refresh; [`theme/brackets/live.py`](../../theme/brackets/live.py) is the
  live example, repainting a bracket on `BRACKET_*` and `MATCH_*` events.
- **Async** (`subscribe_async`) do I/O (webhook POSTs, the telemetry mirror).
  Their coroutine is scheduled onto the dispatch worker, wrapped in
  `tenant_scope(event.tenant_id)` so a subscriber can use scoped services.

`publish` filters each subscriber by its `event_types` (`None` = all) and swallows
every subscriber error, so one bad listener cannot break the others or the caller.

A cancelled match emits **both** `match.cancelled` and `match.deleted`:
cancellation deletes the row, so a subscriber listening for the deletion keeps
working, while `match.cancelled` carries the `reason` and marks the difference
between "called off" and "shouldn't have existed".

## Who publishes what

| Family | Published by |
|---|---|
| `match.*` | `match/match_service.py`, `match_schedule_service.py`, `match_cancellation.py`, `match_request.py` |
| `crew.*` | `crew_service.py` |
| `volunteer.*` | `volunteer/volunteer_schedule_service.py` |
| `bracket.*` | the `_bracket/` mixins (generation, advancement, completion, multistage, scheduling, series) |
| `race_room.*` | `race_room_service.py` |
| `sg_sync.*` | `speedgaming_etl_service.py` |
| `discord_event.*` | `discord/discord_event_reconciler_service.py` |
| `async_qualifier.*` | `async_qualifier/` (run submitted/reviewed, live race recorded) |
| `service_health.alert` | `service_health_service.py` — platform-level (no tenant), so tenant-scoped webhooks never receive it |
| `tenant.member_*`, `tenant.join_*` | `tenant_membership_service.py` — who belongs to a community and who is asking to, which is what an external roster subscriber mirrors (and what routes "someone wants in" to a staff channel). The rest of `tenant.*` stays audit-only: it is platform-level super-admin work a tenant's own subscriber cannot see |

## Registering a subscriber at startup

Subscribers are registered in the FastAPI lifespan in [`main.py`](../../main.py),
alongside starting the dispatch worker:

```python
event_dispatch_queue.start()
event_bus.subscribe_async(WebhookService().deliver_event)
event_bus.subscribe_async(TelemetryService().record_event)  # no filter: mirror all
```

Current async subscribers: **[webhooks](webhooks.md)** (fans each event out to
staff-configured endpoints) and **[engagement telemetry](telemetry.md)** (mirrors
every event into `TelemetryEvent`). A new non-UI subscriber follows the same
shape.

## Adding a new event

1. Add a constant to `EventType` **and** to `EventType.ALL`.
2. Publish it at the commit point — normally via `write_and_publish`.
3. It is immediately selectable in the webhook admin multiselect.

## The three remaining hand-rolled pairs

`check_dry_regressions.py` blocks a *new* `write_log` + `event_bus.publish`
sequence, and every site that could be converted has been. Three keep the pair,
because collapsing them into one call would change behaviour rather than just
shape:

| Site | Why it stays |
|---|---|
| `CrewService.set_approval` | audits **inside** `async with in_transaction()`, publishes outside it. `write_and_publish` would move the publish inside the transaction, where a subscriber could read pre-commit state. |
| `CrewService.acknowledge` | same transaction boundary. |
| `VolunteerScheduleService.assign` | audits every assignment, publishes only when `not auto_generated` — an unpublished draft is deliberately silent. One call cannot express the conditional half. |

If a future change moves the audit write out of the transaction, or makes the
draft assignment publish too, convert the site then.

### Converting a site without breaking its tests

Service unit tests hand-build their subject and hang a double off it. A blanket
`MagicMock()` swallows `write_and_publish` whole, so a converted service silently
stops publishing *under test only* — which is what kept this backlog open. Use
`tests.factories.make_audit_double()` instead: it mocks `write_log` (so existing
call-args assertions and DB-free tests keep working) while binding the real
`write_and_publish` body to the double, so the event still reaches the bus.

## Tests

[`tests/services/test_event_bus.py`](../../tests/services/test_event_bus.py):
inline sync delivery, event-type filtering, async enqueue onto the dispatch
worker, and subscriber-error isolation.

[`tests/services/test_event_audit_parity.py`](../../tests/services/test_event_audit_parity.py)
is a **drift guard**: because `EventType` names mirror `AuditActions` verbatim,
every audited action must either be emitted (in `EventType.ALL`) or listed in an
explicit eventless ledger (`_EVENT_CANDIDATES` / `_EXCLUDED_BY_DESIGN`). Adding a
new `AuditAction` without triaging it fails the test, so audit/event drift cannot
recur silently.
