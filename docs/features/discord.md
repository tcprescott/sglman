# Discord Integration

What the Discord integration does for users: match DMs, guild-role → app-role sync,
and the mock mode that makes all of it developable offline. Implementation mechanics
(bot singleton, DM queue, button handlers, `custom_id` formats) are in
[reference/discord-integration.md](../reference/discord-integration.md).

## Match notifications

DMs fire on match lifecycle transitions:

| Event | Recipients |
|---|---|
| Scheduled | both players |
| Confirmed | players, when the second player confirms a submitted match |
| Seated / checked in | players and approved crew |
| Started | watchers |
| Finished | players and crew, with the result |
| Stage assigned | players |
| Stream candidate | tournament subscribers, with crew-signup buttons |
| Matchup ready to schedule | both entrants of a bracket matchup (also re-sent as a *rebook* if its game is later called off) |

That last one is the only bracket-specific message — there are deliberately no
advancement or elimination DMs. See
[brackets.md → Notifications](brackets.md#notifications). Its button opens the
schedule dialog directly; see [Calls to action](#calls-to-action).

**Series context.** A match that is one game of a bracket matchup leads its info
block with `Round: Semifinals · Game 2 of 3 · Series 1-0`, resolved once by
`BracketService.match_dm_context` and threaded through `_match_descriptor`. Empty
for the vast majority of matches, which no bracket scheduled.

## Calls to action

Every DM that asks the recipient to do something carries a **link button** to the
control that does it. `DMLink(label, url)` goes to `send_dm(..., link=...)`, which
appends a Discord link button to whatever buttons the DM already has — a player
gets **Acknowledge** and **View your matches** side by side — and hands the same
URL to the web-push mirror as its `navigate` target, so the phone notification
opens the same place.

Build the URL with `application/services/notification_links.py`. It resolves the
tenant in scope and returns an absolute, tenant-qualified link (a custom domain
wins over the platform's `/t/<slug>` prefix). It **never raises**: an unresolvable
tenant costs the button, not the DM.

| DM | Button | Lands on |
|---|---|---|
| Matchup ready to schedule | Pick a time | `/home/player?schedule=<matchup id>` — the picker, open |
| …its rebook variant | Pick a new time | the same |
| Match scheduled / rescheduled (players) | View your matches | `/home/player`, beside Acknowledge |
| Match scheduled (subscribers), stream candidate | View the schedule | `/home/schedule`, beside the crew buttons |
| Seed ready | Open your seed | the randomizer — the one deliberately off-site link |
| Crew assignment | View the schedule | `/home/schedule`, beside Acknowledge |
| Crew withdrew (to admins) | Fill the slot | `/admin/schedule?match_id=<id>` |
| Volunteer released (to coordinators) | Find cover | `/admin/vol-schedule?day=<shift day>` |
| Reschedule request (to staff) | Review the request | `/admin/schedule?reschedule_request=<id>` — the decision dialog, open. Not the board filtered to the match: the proposed time and the player's reason are the whole message and live in the dialog |
| Reschedule request (to the opponent) | Agree · View your matches | the Agree button *is* the control; the link is their own schedule |
| Reschedule declined (to the requester) | Ask again | `/home/player?reschedule=<match id>` — the request form, open, because a different time is the real next step after a refusal |
| Join request (to staff) | Review the request | `/admin/users` |
| Join approved (to requester) | Open the community | the tenant home |
| Qualifier reviewed / expiring / expired / reattempt | Submit or forfeit · View the leaderboard · Start your next run | `/qualifiers/<id>` |

A DM with no ask gets no button — checked in, cancelled, state changed, volunteer
unassigned, and an **approved** reschedule (the match moved, and the reschedule
notice both players already got is the news). A button there is noise, not help.

Two things that are easy to get wrong:

**The embed suppresses the text.** `send_dm` sends the embed *instead of* the
content, so a markdown link written into the message string never renders on
Discord. It still reaches the web-push mirror (which strips the markdown), so a
text link is a fallback, never the route.

**Link the surface the recipient can use.** The matchup-ready DM pointed at
`/brackets/<id>` for a long time. That page's Schedule button is `is_staff`-gated,
so the two entrants it addressed arrived at a dialog whose only control was Close.
Check the role gate on a target before linking it.

The `?schedule=` param is honoured by `pages/home_tabs/player.py`, which opens the
dialog from the same handler the on-page button uses and matches the id against
that viewer's *own* open matchups — a forwarded link cannot open somebody else's.
A matchup that has since been booked, cancelled, or finished gets
"That matchup is no longer waiting to be scheduled." rather than a silent no-op:
a DM outlives what it points at, and a dead button reads as a broken app.

### Fan-out and dedup

`MatchScheduleService.notify_*` gathers the match's players, its `MatchWatcher`
rows, and tournament subscribers, then deduplicates — someone who is both a player
and a subscriber gets one DM, not two.

**Cancellation is the exception.** `notify_match_cancelled` takes a pre-resolved
`{discord_id: is_watcher}` map rather than a `Match`. Cancelling deletes the row,
and every other notifier re-queries its recipients when the queue worker finally
awaits it — by which point the cascade has removed them and the DM would reach
nobody. So `MatchService._cancel_match` resolves recipients and builds the message
*before* the delete. Recipients get a plain DM rather than the watcher variant,
whose Unwatch button would carry the id of a match that no longer exists. The card
uses `COLOR_CANCELLED`, the palette's only negative colour.

## Guild-role → app-role sync

Maps a user's Discord guild roles onto application roles at login, granting what
they should have and revoking what they should not — without disturbing roles a
staff member granted by hand. The bot reads guild membership directly via the
`members` intent, so login keeps the `identify` scope and needs no extra permission.

`pages/auth.py` calls `DiscordRoleMappingService().sync_user_roles(user)` after the
`User` is upserted and before the redirect. That call **fans out across every tenant
that has a `discord_guild_id`**, syncing each inside its own `tenant_scope` and
concurrently, since one person may belong to several communities' guilds — login
latency stays at roughly one Discord round-trip instead of scaling with tenant
count. Per-tenant mappings are `DiscordRoleMapping` rows managed on the admin
**Discord Roles** tab.

### Two kinds of mapping

A mapping grants **either** a community-wide `Role` **or** a `TournamentGrant`
(Tournament Admin / Crew Coordinator) on one named tournament. Both shapes live in
`DiscordRoleMapping` and appear together on the admin tab; `add_mapping` enforces
the either/or, since a cross-column rule is not something the database can express.

A tournament grant must name its tournament — a guild role is guild-wide, so there
is otherwise nothing to scope the authority to. Once the tournament is no longer
`is_active` the mapping counts as absent: authority ends with the event, and
re-activating the tournament hands it back on the next sync. What each grant
actually permits: [authentication.md](../reference/authentication.md#roles).

### Source tracking is the safety guard

`UserRole.source` (`RoleSource`: `manual` | `discord`) is what makes full-sync safe:

- Roles granted by a staff member are `manual` and are **never** auto-revoked.
- Roles granted by the sync are `discord` and are revoked when the Discord role goes away.
- A manual grant over a previously-synced role upgrades the row to `manual`, pinning it against future revocation.

Tournament grants get the same guarantee from a different mechanism.
`Tournament.admins` and `.crew_coordinators` are bare join tables with no column to
record who made a row, so the sync writes a `DiscordTournamentGrant` alongside each
grant it creates and revokes only what it finds there. A grant the user already
holds is left unclaimed, and `TournamentService.add_admin` /
`add_crew_coordinator` (and their removes) delete the provenance row, which pins
the grant as manual.

### Fail-open

`sync_user_roles` never raises. A bot that is not ready, or a Discord API error,
skips the sync and leaves roles untouched — an outage can never block login. A
failure in one tenant does not abort the others. A member definitively *not* in the
guild yields an empty role set, which correctly revokes their Discord-sourced roles.

**Operational prerequisite:** the privileged **Server Members Intent** must be
enabled for the bot in the Discord Developer Portal, and the bot invited to the
guild. The code already sets `intents.members = True`; without the portal toggle
`get_member_role_ids` returns empty and the sync is a safe no-op.

Audit actions: `discord_role.mapping_added` / `.mapping_removed` for staff edits,
`role.discord_sync_granted` / `.discord_sync_revoked` for the login sync (actor =
the signing-in user).

## Tournament notification preferences

Users subscribe per tournament to hear about matches beyond their own.
`MatchNotificationLevel` (`models/enums.py`) sets the volume:

| Level | DMs sent for |
|---|---|
| `none` | nothing |
| `streamed` | matches assigned to a stream stage |
| `streamed_and_candidates` | stream-assigned + stream-candidate matches |
| `all` | every scheduled match in the tournament |

A subscription is a **follow** and does not require enrollment — the fan-out never
checks the player pool — so the picker spans every active tournament and merely
badges the ones the user is enrolled in.

Stored as `TournamentNotificationPreference` (user × tournament × level), set inline
under Profile → Notifications → **Match alerts by tournament**
(`pages/home_tabs/player_edit_info.py`) via
`TournamentNotificationService.upsert_preference`. The card's **Delivery**
checkbox (`User.dm_notifications`) is the master switch above it: the subscriber
queries filter on it, so with delivery off no level sends anything — on Discord or
on a mirrored device. Fan-out reads subscribers
directly from `TournamentNotificationRepository` —
`get_match_notification_subscribers` and `get_stream_candidate_subscribers`; there
is no service-level `get_subscribers()` abstraction.

`Match.is_stream_candidate` is toggled by admins in the match dialog; turning it on
fans out to `streamed_and_candidates` subscribers with crew-signup buttons attached.

## Mock mode

`MOCK_DISCORD=true` makes the whole integration developable with no Discord
application, bot token, or network:

- **OAuth bypass** — `/login` renders a user picker instead of redirecting to Discord. Any user in the database can be impersonated, plus a "Create test user" shortcut. Picked and created users are real rows and persist across restarts.
- **`DiscordService` stubbed** — swapped for `MockDiscordService`, which mirrors the real public surface and logs to stdout, so notification code paths run end to end.
- **Server-connect offline** — the bot-authorization flow short-circuits straight to its own callback with a mock guild id, and `member_can_manage_guild` returns `True`, so `Tenant.discord_guild_id` gets set with no Discord round-trip.
- **Bot does not start** — `DISCORD_TOKEN` is not required.

```bash
./start.sh mock                     # development + MOCK_DISCORD + MOCK_CHALLONGE + MOCK_SEEDGEN
MOCK_DISCORD=true ./start.sh dev    # mock Discord only
```

Mock mode is a complete authentication bypass, so the app **refuses to start** when
it is enabled while `ENVIRONMENT=production`.

**Limit:** button interactions (acknowledgment, crew signup, watch) need a live bot
connection and cannot be exercised in mock mode — test those against a real Discord
dev server.

### Mock fixture data

Guilds, roles, and per-member role assignments live in one place —
[`application/utils/mocks/mock_discord_data.py`](../../application/utils/mocks/mock_discord_data.py)
— and every `MockDiscordService` method reads from it, so the data stays
self-consistent. It is kept in sync with `scripts/seed_dev.py`: the guild ids and
mapped role ids/names match the dev seed, so a mock member's roles resolve against
seeded `DiscordRoleMapping` rows and login sync does real work.
`get_member_role_ids` hands each user a deterministic, varied role set (everyone is
at least a Volunteer). Edit `MOCK_GUILDS`, a guild's `roles`, or `MOCK_MEMBER_ROLES`
to enrich the fixtures.

## Testing

Fan-out and sync logic are covered by `tests/services/test_match_schedule_service.py`
and `test_discord_role_mapping_service.py`. Actual DM delivery and button
interactions are not unit-tested — they need a live connection.
