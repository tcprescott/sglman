# Event System

An in-process publish/subscribe bus that centralizes notifications. Services
publish a domain **event** after they commit a change; any number of subscribers
react. It generalizes the older, match-only [`application/match_events.py`](../../application/match_events.py)
(which still powers UI live-refresh) into a typed, named bus that anything in the
app can subscribe to.

Source: [`application/events/`](../../application/events/).

## Why it lives at `application/events/`

The package sits at the `application/` root — a peer of `services/`,
`repositories/`, and `utils/` — so it is **unconstrained** by the
architecture-enforcement hook and importable by both the service layer
(publishers) and the presentation layer (a future UI subscriber), exactly like
`match_events.py`. It imports nothing from `application.services`, so there is no
import cycle.

## Pieces

| Module | Role |
|---|---|
| `event.py` | The immutable `Event` value object: `event_type`, `payload`, snapshotted `actor_id`/`actor_username`, `occurred_at` (UTC). `Event.create(type, payload, actor)` builds one; `to_wire()` is the JSON shape delivered to webhooks. |
| `event_types.py` | `EventType` — the `object.verb` name registry (mirrors `AuditActions`). `EventType.ALL` drives the webhook UI multiselect + validation; `'*'` is the wildcard. Names are an **external contract** — treat renames as breaking. |
| `dispatch_queue.py` | A background worker (clone of `discord_queue`) that runs async subscribers off the request path. |
| `bus.py` | The core: `subscribe_sync`, `subscribe_async`, `unsubscribe`, `publish`. |

## Two kinds of subscriber

- **Sync** (`subscribe_sync`) run **inline** during `publish` and must be fast and
  non-blocking — schedule work, never await (same rule as `match_events`). This is
  the fast-path for UI live-refresh.
- **Async** (`subscribe_async`) do I/O (webhook POSTs, and — in a later phase —
  Discord DMs). Their coroutine is scheduled onto the dispatch worker so `publish`
  never blocks the mutating service call.

`publish` filters each subscriber by its `event_types` (`None` = all) and swallows
every subscriber error, so one bad listener can't break the others or the caller.
`publish` itself is synchronous, never raises, and never blocks.

## Publishing (in a service, after commit)

```python
from application.events import Event, EventType, event_bus

# ...after the DB write + audit, fire-and-forget, last:
event_bus.publish(Event.create(EventType.MATCH_CREATED, {
    'match_id': match.id, 'tournament_id': tournament_id, 'player_ids': player_ids,
}, actor))
```

Publishers today (co-published alongside the existing `match_events.publish` and
Discord fan-out, which are unchanged): `match_service` (create/update/reschedule/
stream-candidate), `match_schedule_service` (`_transition` → seat/start/finish/
confirm, and `generate_seed`), `crew_service` (signup/undo/approval/ack),
`volunteer_schedule_service` (assign/unassign/ack).

## Registering a subscriber at startup

Subscribers are registered in the FastAPI lifespan in
[`main.py`](../../main.py), alongside starting the dispatch worker:

```python
event_dispatch_queue.start()
event_bus.subscribe_async(WebhookService().deliver_event)
event_bus.subscribe_async(TelemetryService().record_event)  # no filter: mirror all
```

Current async subscribers: **webhooks** (`WebhookService.deliver_event`, fans
each event out to staff-configured endpoints) and **[engagement telemetry](telemetry.md)**
(`TelemetryService.record_event`, mirrors every event into the `TelemetryEvent`
log with no `event_types` filter). A new non-UI subscriber follows the same
shape: import its module and call `event_bus.subscribe_async(...)` (or
`subscribe_sync`) in the lifespan.

## Adding a new event

1. Add a constant to `EventType` and to `EventType.ALL`.
2. `event_bus.publish(Event.create(EventType.NEW_THING, {...}, actor))` at the
   commit point in the relevant service.
3. It is immediately available to webhook subscribers and shows up in the
   webhook admin multiselect.

## Relationship to Discord notifications

Phase 1 (current): the event bus is **additive**. Discord DMs still fan out through
`discord_queue` exactly as before; events are published alongside for the new
consumers (webhooks). Migrating the Discord fan-out to be a bus subscriber is a
possible Phase 2 (see [current-state.md](../current-state.md)).

## Tests

[`tests/services/test_event_bus.py`](../../tests/services/test_event_bus.py):
inline sync delivery, event-type filtering, async enqueue onto the dispatch
worker, and subscriber-error isolation.
