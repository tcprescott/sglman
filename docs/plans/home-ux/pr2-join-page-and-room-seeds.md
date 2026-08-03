# PR 2 — the join page, and the tournament-room seeds view

**Status: shipped.** PR 1 ([pr1-four-tabs.md](pr1-four-tabs.md)) was the
prerequisite. Read [README.md](README.md) first for the decisions both PRs share.

What landed matches the plan below, with three additions the browser loop
forced: the match preview drops finished matches, caps at twelve rows with an
"…and N more today" line, and abbreviates a roster longer than two — an event day
put thirty-four rows and a ten-racer play-in on the door, burying the Request
access button. Reference docs:
[frontend.md § the join page](../../reference/frontend.md#the-join-page) and
[§ the tournament-room seeds board](../../reference/frontend.md#the-tournament-room-seeds-board).

Two independent pieces that ship together because both are about what someone
outside the member surface can see.

---

## Part 1 — the join page

`theme/join_page.py` is what `enforce_membership` renders for anyone who is not a
member of the community, anonymous visitors included. Today it says "Sign in to
ask to join this community" and offers nothing else, which is the whole
first impression a new attendee gets.

### Browse brackets

A link into the existing public bracket pages (`/tournament/{id}/brackets`),
shown when `FeatureFlag.BRACKETS` is on. Those pages already work signed out and
are already `public_page`; they are simply unreachable unless you know the URL.

### Today's matches, behind a staff opt-in

Times **and player names**, for matches on the community's current day.

This is deliberately gated, because it re-opens exactly what the membership gate
was added to close: the audit's symptom was a non-member loading a new
community's home schedule and seeing its first match with both players' names.
Public bracket pages do publish entrant names anonymously, but only where staff
enabled the flag *and* made the stage visible — a controlled opt-in. The join
page is not, so it gets its own.

- **Key:** `KEY_JOIN_PREVIEW`, a new `SystemConfiguration` key. Per-tenant already
  (`SystemConfiguration` is unique on `(tenant, name)`), so **no migration**.
- **Not a `FeatureFlag`.** One display toggle does not need two-tier availability,
  a `FeatureFlagSpec`, `service_modules`, or `@requires_feature`.
- **Default off.** A community that never touches it keeps the gate's original
  guarantee.
- **Edited on** Admin → Settings (`pages/admin_tabs/admin_system_config.py`),
  audited through `SystemConfigService.set_raw` like every other key there.
  `SystemConfigService` gains a `get_bool` alongside `get_int` / `get_date`.
- **Timezone:** the community's pinned zone via
  `TimezoneService.tenant_timezone_name()` + `tz_scope`, **not** the visitor's.
  "Today" here means the event's day, and a visitor two zones over should not see
  a different list.

---

## Part 2 — the room seeds view

A tournament-room PC needs to pull up the seed for a match that is rolled but not
yet started, without anyone signing in on a shared machine.

### The route

`GET /t/<slug>/room/<token>/seeds` — **inside** the tenant prefix, so the existing
middleware resolves the tenant and binds the display clock and the token only
authorizes. Outside the prefix, the page would have to resolve the tenant from
the token itself and enter `tenant_scope` by hand, or `require_tenant_id()` raises
on every read.

A live NiceGUI page, **read-only**. Lists matches where `generated_seed` is set
and `started_at` is null. Columns: players, scheduled time, stage, tournament,
seed link.

Rolling and re-rolling stay signed-in staff work. An unauthenticated token that
can spend randomizer API calls and replace the seed for a match about to be
played is not a trade worth making for a machine sitting in a public room.

### Live updates

Build it on `MatchTableView` with a fixed filter, readonly slots
(`SEED_SLOT_READONLY`, `state_readonly_slot`) and no action callbacks. The live
wiring is already inside the component at `theme/tables/match.py:529` —
`register_view(self._on_remote_change)`, the same helper the On Air timeline uses
— so the room view reacts to `match_live` through the identical path as the admin
board: `CREATED` refreshes, `changed`/`deleted` go through `update_row_by_id`
with the row flash. A seed rolled at the desk appears on the room PC untouched.

Reusing the component also settles the `check_table_grid` hook, since
`MatchTableView` is one of the four family tables with its own `item` slot.

Two characteristics to know rather than fix:

- `match_live.publish` notifies every subscriber on the instance with no tenant
  filter, and `update_row_by_id` no-ops when the id is not on the board. No
  cross-tenant leak, but every open room PC wakes briefly on every match change
  platform-wide. Fine at current scale.
- `register_view` captures `context.client` and releases on disconnect, so a room
  PC that loses the venue network and reconnects re-subscribes cleanly.

The websocket-per-tab cost that `pages/static_brackets.py` exists to avoid is
bounded here in a way it is not for brackets: a handful of room PCs, not a stream
audience.

### Table preferences

**Exempt**, with a `# table-prefs: exempt` comment naming the anonymous-kiosk
reason so `check_table_prefs` passes. Columns are hardcoded. Per-viewer layouts
persist through `TablePreferenceService`, keyed to a user row; an anonymous kiosk
has none, and building a second localStorage-backed persistence backend for one
page is not worth it. If staff later want to rearrange the room view, the honest
fix is a general anonymous-preferences path.

### `RoomToken`

A new tenant-scoped model: hashed value, label, `created_by`, `last_used_at`,
`revoked_at`. **Needs a migration.**

Deliberately **not** `ApiToken`, which acts with its owner's full permissions. A
token taped to a room PC should unlock one page and nothing else.

- `RoomTokenRepository` for data access; `RoomTokenService` for issue, resolve
  and revoke, with `AuditActions.ROOM_TOKEN_CREATED` / `ROOM_TOKEN_REVOKED`.
- Managed on **Admin → Settings**, beside the join-preview toggle: URL with a
  copy button, label, last used, rotate. No new admin tab.
- **No feature flag.** The table is empty until staff issue a token, so the
  feature already defaults to off for every community. A flag would gate
  something that gates itself.
- An unknown, revoked, or malformed token renders a **plain 404**,
  indistinguishable from a route that never existed, so guessing reveals nothing.

**Not linked from the join page.** A token URL that is publicly linked is not
unlisted. The room PC gets it by bookmark.

---

## Tests

- Token resolution: valid, revoked, unknown, and **wrong-tenant** — the last is
  the leak test the multitenancy rules require for any new tenant-scoped model.
- The seeds query excludes started matches and unseeded ones.
- Join page across three states: preview off, preview on, and `BRACKETS` off.
- `scripts/seed_dev.py` gains a tenant with the preview on and a token issued, so
  both surfaces are visible in dev and reachable from `/ui-validation`.

## Docs to update when it lands

`docs/reference/frontend.md` (the new route + the join page),
`docs/reference/data-model.md` (`RoomToken`),
`docs/features/multitenancy.md` (the new scoped model),
`docs/reference/services.md` (`RoomTokenService`), and this file's status line.
