# Event check-in

Behind `FeatureFlag.EVENT_CHECK_IN`, off by default. For in-person events whose
registration runs on Matcherino.

Staff create a check-in event and give it the Matcherino bounty ID. Wizzrobe
mirrors the bounty's participant list into a local roster, matches each
registrant to a Wizzrobe account where it can, and volunteers check people in at
a phone-friendly desk. Matcherino only tells us who registered; who has *arrived*
is recorded here.

Matching to an account is a nice-to-have. An unlinked registrant checks in like
anyone else.

## The Matcherino API is unofficial

Matcherino has no public API. `application/utils/clients/matcherino_client.py`
calls the two endpoints its own web app uses, with Matcherino's go-ahead but no
support promise:

| Endpoint | Use |
|---|---|
| `GET /__api/bounties/participants?bountyId=&page=&pageSize=` | The roster. Zero-indexed pages of up to 500 |
| `GET /__api/bounties/findById?id=` | The bounty title, so staff can confirm an ID before saving |

Both answer `{"status", "body"}` envelopes; failures come back as
`{"status": 500, "error": {"message"}}`. An **unknown bounty is not an error**:
it is `200` with `contents: null`, which reads exactly like an empty bounty.

Everything downstream assumes the endpoint can break without warning:

- The parse is strict about the two fields check-in needs (`userId`,
  `displayName`) and raises `MatcherinoAPIError` rather than guessing.
- A sync that fails, **or comes back empty while the roster has live rows**,
  records `CheckInEvent.last_sync_error` and changes nothing. Withdrawing every
  registrant because one response was bad is the failure this guards against.
- The desk shows the last good sync time and the error in its header, so
  volunteers can see the roster is stale.
- Check-in itself never touches Matcherino. If the endpoint dies mid-event the
  desk keeps working on the last roster, and staff add late arrivals as walk-ups.

`MOCK_MATCHERINO` swaps in `MockMatcherinoClient` (refused under
`ENVIRONMENT=production`). `./start.sh mock` and `validate` set it.

## The model

| Model | What |
|---|---|
| `CheckInEvent` | Tenant-scoped. `name`, nullable `matcherino_bounty_id` (unique per tenant), `status` (`DRAFT`/`OPEN`/`CLOSED`), `sync_interval_minutes`, and the sync bookkeeping `last_synced_at`/`last_sync_error`/`last_sync_count` |
| `CheckInEntrant` | One person on a roster. `source` (`MATCHERINO`/`WALK_UP`), `matcherino_user_id`, `display_name`, the identity hints (`auth_provider`, `auth_id`, `twitch_login`), `registered_at`, `source_data`, the matched `user` + `link_method` + `linked_by`, `withdrawn_at`, `checked_in_at` + `checked_in_by` |
| `User.matcherino_user_id` | Matcherino's numeric account id. Global and **unique**, unlike the self-entered `matcherino_username` |

`unique_together` on the entrant is `(event, matcherino_user_id)` and
`(event, user)`: one row per registrant, and one row per account. Postgres
treats `NULL`s as distinct, so walk-ups and unlinked rows don't collide.

A registrant who leaves the bounty gets `withdrawn_at`, never a delete, so a
check-in already recorded against them survives. Rejoining clears it.

`link_method = MANUAL` with `user = NULL` means staff unlinked the row on
purpose. The sync never auto-links such a row again; staff unlink exactly when
an automatic match was wrong.

### Room for registration tiers

Matcherino may later expose registration tiers (VIP vs regular), which would
tell the desk what to hand someone. Neither endpoint serves them today. The
design leaves room without building anything speculative:

- `CheckInEntrant.source_data` holds the participant object exactly as last
  served. A field Matcherino starts sending can be backfilled from rows already
  synced.
- `MatcherinoParticipant` keeps the raw dict beside its parsed fields, so reading
  a new field is one attribute and one assignment in `sync_event`.
- The intended extension is three tables (`CheckInTier` per event,
  `CheckInTierItem` for what a tier is handed, `CheckInHandout` for what someone
  has received) plus a nullable `CheckInEntrant.tier` FK with a `tier_source`, so
  a sync never overwrites a tier staff set by hand. None of it changes a column
  that exists now.

## Matching registrants to accounts

Each participant carries the account they signed in to Matcherino with:
`authProvider` + `authId`. For `discord` the id is the Discord snowflake; for
`twitch` it is the Twitch user id. In a 164-person sample, 133 had one of the
two.

`CheckInService._auto_link` tries these in order and takes the first hit:

| Rule | Matches |
|---|---|
| `MATCHERINO_ID` | `User.matcherino_user_id` = the participant's `userId` (a link remembered from an earlier event) |
| `DISCORD_ID` | Discord sign-in, `authId` = `User.discord_id` |
| `TWITCH_ID` | Twitch sign-in, `authId` = `User.twitch_user_id` |
| `TWITCH_LOGIN` | a Twitch login in `socials` = `User.twitch_username` |
| `MATCHERINO_HANDLE` | the `#id` suffix of a self-entered `User.matcherino_username` = `userId` |

Exact identifiers only, matched across all of Wizzrobe: a registrant's Discord or
Twitch id is already public on the bounty, so finding its account reveals
nothing. Name similarity is only ever **suggested** (`suggest_users`, ranked
`difflib` against community members) for staff to confirm.

Two registrations that resolve to one account link only the first.

**What a link writes to the account.** `matcherino_username` is where prize money
is sent, so this is deliberately narrow (`_remember_matcherino_account`):

- Only a `DISCORD_ID`, `TWITCH_ID` or `TWITCH_LOGIN` match (OAuth-verified ids)
  or a manual link (a person at the desk confirmed it) records anything. A
  `MATCHERINO_HANDLE` match is **not** promoted: the handle is self-typed, and it
  keeps matching on its own.
- It fills `User.matcherino_user_id` and `matcherino_username` **only when
  empty**, never takes an id another account holds, and writes a
  `user.profile_updated` audit row with `source: check_in`.
- Unlinking undoes it (`_forget_matcherino_account`): staff unlink when a match
  was wrong, and a wrong id left in place would re-link that person at every
  later event and lock the real owner out. The id is cleared if it matches the
  row; the handle only if it is still exactly the one check-in filled in.

## Who may do what

| Action | Who |
|---|---|
| Create, edit, open/close, delete events; look up a bounty | `STAFF` (`AuthService.can_manage_check_in`) |
| Check in, undo, link, unlink, sync | `STAFF` or `CHECK_IN_DESK` (`can_run_check_in_desk`); the system user for the worker |
| Add a walk-up, remove a walk-up | `STAFF` only |

`Role.CHECK_IN_DESK` is a per-tenant role for check-in volunteers. It appears in
the Users dialog and the Discord role-mapping picker on its own (both read
`Role.tenant_grantable()`).

Only walk-ups can be removed: a Matcherino row would come back on the next sync.
An event's bounty can't change once it has a Matcherino roster (the next sync
would withdraw everyone); create a new event instead.

## Concurrency

Several phones work one event, and the worker polls it too:

- **Check-in and undo are conditional updates** (`claim_check_in` /
  `release_check_in`). Two phones tapping the same person record one check-in,
  one audit row and one event; the second gets "already checked in by …".
- **One sync per event at a time.** An in-process `asyncio.Lock` per event
  serialises the worker, staff and every desk's Sync (single process, see
  [scaling-roadmap.md](../scaling-roadmap.md)). The roster is read *after* the
  Matcherino fetch, so desk actions made during it are seen.
- **Auto-links are conditional** (`claim_auto_link`): a row a desk linked or
  unlinked mid-sync is left as the desk set it.
- **The sync writes only its bookkeeping columns** on the event
  (`record_sync`), so a staff edit made during a slow fetch is not reverted.
- **A short read is a failure.** The client compares the distinct participants
  it got with page 0's `itemCount` and raises on a shortfall or on hitting the
  page cap, so a dropped page never looks like people leaving.
- A unique-constraint race that slips through anyway (a walk-up, an event's
  bounty, a link) surfaces as a `ValueError` message, not a raw error.

## The service

`application/services/check_in_service.py`. Every public method carries
`@requires_feature(FeatureFlag.EVENT_CHECK_IN)`.

| Method | Does |
|---|---|
| `create_event` / `update_event` / `delete_event` | Event CRUD. One event per bounty per community |
| `preview_bounty` | Fetches the bounty title for the admin dialog |
| `list_events` / `list_open_events` / `get_event` / `has_open_event` | Reads |
| `sync_event(actor, event_id, audit=True)` | Upsert by `matcherino_user_id`, withdraw/rejoin, auto-link. Returns `SyncResult`. `audit=False` is the worker's poll |
| `roster` / `get_entrant` | Reads |
| `suggest_users` / `search_members(event, query)` | Candidate accounts for the link and walk-up dialogs, community members not already on the roster |
| `check_in` → `CheckInOutcome(entrant, already)` / `undo_check_in` | The desk's main actions |
| `link` / `unlink` | Manual matching |
| `add_walk_up(event_id, user_id= or name=, check_in=True)` / `remove_entrant` | Walk-ups (staff) |

Module-level `summarize(entrants) -> RosterCounts` gives the desk's headline
numbers; withdrawn rows count only as withdrawn.

## Sync worker

`application/services/check_in_sync_worker.py`, a 60 s `run_worker_loop` tick.
It scans open events with a bounty (cross-tenant), and syncs each one inside its
tenant's scope as the system user once `sync_interval_minutes` has passed. After
a failure it backs off from the failure time rather than retrying every tick.
Tenants with the flag off are skipped. No environment switch: it only touches
events staff have opened. Run one tick by hand with
`poetry run python scripts/run_worker_tick.py check_in_sync`.

## Audit and events

| Action | Audit | Event |
|---|---|---|
| `check_in_event.created` / `updated` / `deleted` | yes | no (tenant-internal config) |
| `check_in_event.synced` | manual syncs only | yes, polls included |
| `check_in_entrant.checked_in` / `check_in_undone` | yes | yes |
| `check_in_entrant.linked` / `unlinked` | yes | yes |
| `check_in_entrant.walk_up_added` / `removed` | yes | yes |

## The desk

`pages/check_in.py`, gated on `roles=[STAFF, CHECK_IN_DESK]` and the flag.

- `/checkin` lists open events and redirects straight to the one when there is
  only one. The **Check-in** nav item appears for desk roles while an event is
  open (`BaseLayout` via `AuthService.can_view_check_in_desk`).
- `/checkin/{event_id}` is the desk. It's phone-first: the search box, progress
  bar, filter chips (All / Not yet / Checked in / Unlinked / Walk-ups /
  Withdrawn, with counts) and sync status stick under the app header. Below
  `md` each person is a card with a full-width 48 px Check in button;
  Link/Unlink/Undo/Remove sit behind a ⋮ menu. On desktop it's a table with the
  same actions.
- Search runs in the browser (Quasar `filter-method`), so it doesn't wait on the
  server.
- After a check-in an Undo bar shows for eight seconds.
- Staff get a floating **Add walk-up** button.
- Export CSV downloads the whole roster, not just the filtered view.

**Several phones at once.** Every roster change publishes on
`application/events/check_in_live.py`. Each open desk subscribes through
`theme/realtime.register_view(..., channel=check_in_live)`, ignores other
events, re-reads its roster and flashes the changed card. A sync sends one
`ROSTER` signal, not one per row. `theme/realtime.refresh_on_reconnect`
re-reads after a socket blip, so a phone that was locked catches up. Both are
in-process and share the match board's single-worker constraint
([scaling-roadmap.md](../scaling-roadmap.md)).

## Admin

Admin → **Check-in** (Operations group, STAFF + flag): the events table, a
New/Edit dialog with a **Look up** button that confirms the bounty by title, and
a **Desk** shortcut per event.

## Dev seed

`scripts/seed_check_in.py` syncs the `MOCK_MATCHERINO` roster through the real
service, so pressing Sync in dev changes nothing. The roster is lined up with
fixtures so one sync produces every link method (see the comment above
`MOCK_PARTICIPANTS`), and the seed adds a manual link, a withdrawn registrant, a
check-in by `checkin_desk` (the fixture holding only `CHECK_IN_DESK`), a member
walk-up and a named walk-up, a draft event and a closed one. Tenants without the
flag are skipped.

## Tests

- `tests/services/test_check_in_service.py`: matching rules and precedence, sync
  idempotency, withdraw/rejoin, the empty-response and API-error guards,
  permissions, walk-ups, the worker.
- `tests/utils/test_matcherino_client.py`: the wire shape through
  `httpx.MockTransport`.
- `tests/tenancy/test_check_in_tenant_isolation.py`: both models.
