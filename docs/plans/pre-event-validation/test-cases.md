# Test cases

_Fourteen suites, run against the rehearsal stack described in
[README.md](README.md). Each case names its **severity** (S1 blocks the event,
S2 degrades it, S3 is cosmetic) and its **cause** (A mock ≠ program, B transport
is the feature, C SQLite ≠ PostgreSQL, D one process under load, E real
hardware). Fill in owners before the window opens._

Record results in the table at the [end of this file](#results).

---

## S1 · Identity and access

Everything here runs through `pages/auth.py` and `middleware/auth.py`, which the
suite marks as uncovered — mock mode replaces the whole login with a user picker.

### ID1 · First-time login provisions a real account — S1, cause A
Sign in to the rehearsal stack as a Discord account that has **never** logged in.
Confirm a `User` row appears with the right `discord_id` and username, that the
community-membership gate does what it should for a non-member, and that landing
on a deep link (`/t/<slug>/home/player?schedule=<id>`) survives the round trip
rather than dumping the user on the landing page.
**Pass:** account created, correct post-login destination, no error in logs.

### ID2 · Login on the custom domain — S1, cause A
Run both strategies, because the choice is an environment variable and only one
of them will be set in October.
- `HOST_OAUTH_MODE=local`: a redirect URI registered per domain. Log in at the
  custom domain root (no `/t/<slug>` prefix).
- `HOST_OAUTH_MODE=handoff`: OAuth runs on `PLATFORM_HOST`, the identity comes
  back through `/oauth/link/claim`. Confirm the token is single-use (replay the
  claim URL — it must fail), host-bound and browser-bound (open the claim URL in
  a second browser — it must fail).
**Pass:** whichever mode production will use works end to end with real TLS; the
three handoff failure modes all fail closed.

### ID3 · Guild-role sync at login — S1, cause A
Give a test account a mapped Discord role in the test guild, log in, confirm the
app role is granted. Remove the Discord role, log in again, confirm it is
revoked — and confirm a role granted *in the app* is not revoked by the sync
(that is what source tracking is for). Then take the bot offline and log in
again: the sync must **fail open**, not lock the user out.
**Pass:** grant, revoke, source tracking and fail-open all behave.

### ID4 · Connect Discord server — S1, cause A
Run the bot-authorization flow against the test guild as a user who really does
have Manage Server. Under `MOCK_DISCORD` this short-circuits and
`member_can_manage_guild` always returns `True`, so the real permission check has
never run. Confirm `DISCORD_BOT_PERMISSIONS` grants the bot enough to apply roles
and manage scheduled events, and that a user *without* Manage Server is refused.
**Pass:** guild id stored, bot has the permissions the features need, refusal path works.

### ID5 · Sessions survive a deploy — S2, cause D
Log in on three browsers, restart the container, reload all three. `STORAGE_SECRET`
signs the session, so this is really a check that it is stable across the deploy
and not regenerated.
**Pass:** all three still signed in; nobody has to re-auth mid-event.

### ID6 · Membership gate and self-serve join — S2, cause A
A real new account requests to join the community; staff approve from the Users
tab. Confirm the approval notification links the control that performs the action,
not the page near it.
**Pass:** request visible, approval works, the DM's button lands on the right surface.

---

## S2 · Discord, live

The bot does not start under `MOCK_DISCORD`, so none of this has ever run outside
production.

### DC1 · A DM actually arrives — S1, cause A
Schedule a match for a real test account and confirm the DM lands, the embed
renders with its colour and fields, and the link button appears.
Then the failure path that will definitely happen in October: **an attendee with
DMs closed.** Set a second test account to refuse DMs from server members, send
again, and confirm the app records the failure without wedging the queue or
throwing into a UI handler.
**Pass:** delivery works; a closed-DM recipient is a logged failure, not an outage.

### DC2 · Every button family — S1, cause A
Five `custom_id` prefixes, five handlers, none of them reachable in mock mode.
Press each from a real DM and confirm the state change lands in the database and
the interaction gets a response rather than "This interaction failed":

| Prefix | Handler | Press as |
|---|---|---|
| `match_ack:ack:<id>` | `discordbot/match_acknowledgment.py` | a player on their own match |
| `crew_ack:<type>:<id>` | `discordbot/crew_acknowledgment.py` | assigned crew |
| `crew_signup:<role>:<id>` | `discordbot/crew_signup.py` | a volunteer, both commentator and tracker |
| `volunteer_ack:<id>` | `discordbot/volunteer_acknowledgment.py` | a shift assignee |
| `match_watch:unwatch:<id>` | `discordbot/watch_buttons.py` | a watcher |

Also press each **twice** (double-tap is what people do on a phone) and press one
belonging to a *different* tenant's match, since `discordbot/_tenant.py` is what
stops a cross-tenant press from working.
**Pass:** all five act once, are idempotent on the second press, and refuse cross-tenant.

### DC3 · Buttons still work after a restart — S1, cause D
Send the DMs, restart the app, then press the buttons in the **old** messages.
Handlers are routed by `custom_id` prefix rather than a per-message view object,
so this should survive — which is exactly why it needs proving rather than
assuming. A DM sent Friday whose button is dead on Saturday is the worst version
of this bug, because nobody reports it.
**Pass:** every button family works from a pre-restart message.

### DC4 · Calls to action land on the control — S2, cause A
For every DM type the event will send, follow its link button on a phone while
signed in as the recipient. Check the three failures CLAUDE.md names: a
destination that is named but not linked, a page rather than the control, and a
surface the recipient's role cannot act on. Then make one link stale (cancel the
match it points at) and confirm the page says so rather than silently doing nothing.
**Pass:** every link opens something the recipient can act on; stale links explain themselves.

### DC5 · Fan-out at match-day scale — S1, cause D
Publish a full match day's schedule in one action against a tournament with a
realistic roster. `discord_queue` is a **single in-process worker draining
sequentially**, so this measures the real thing: how long until the last person
gets their DM, and whether Discord rate-limits us partway through.
**Pass:** the queue drains without loss; record the wall-clock time and write it
into the runbook so October's staff know what "still sending" looks like.

### DC6 · What a restart costs the queue — S1, cause D
Queue a large fan-out and restart the app mid-drain. Shutdown **counts, logs and
drops** whatever is still queued, by design.
**Pass:** the count is in the logs and we know the number. Write the mitigation
into the runbook: never restart during a publish, and how to re-send if it happens.

### DC7 · Discord Events reconciler — S2, cause A
With `DISCORD_EVENTS_SYNC_ENABLED=true`, mirror an opted-in tournament's schedule
into the test guild. Reschedule a match, cancel another, and confirm the guild's
scheduled events follow. Also reconcile on demand from the admin tab.
**Pass:** create, update and delete all reconcile; no duplicate events after
repeated runs.

### DC8 · Gateway reconnect — S2, cause B
Sever the bot's network for a few minutes and restore it. Confirm the gateway
reconnects on its own, the `/platform` service-health board shows the transition,
and DMs queued during the outage go out afterwards.
**Pass:** self-heals with no restart; health board tells the truth throughout.

---

## S3 · Web push on real devices

Transport *is* the feature here — RFC 8291 encryption and a POST to Apple,
Google and Mozilla. Nothing local proves any of it.

### WP1 · Subscribe on each real platform — S2, cause B/E
One device each: **iOS Safari** (the app must be added to the Home Screen first —
Safari exposes no push API in a plain tab), **Android Chrome**, and a desktop
browser. Subscribe from Profile → Notifications → Your devices.
**Pass:** three subscriptions stored; a test notification arrives on all three.

### WP2 · Both rendering paths — S2, cause B
Safari 18.4+ parses the declarative payload with no service worker; everything
else fires the classic `push` event and renders the same JSON through
`static/sw.js`. One payload, two code paths — check both actually render title
and body, not a browser default.
**Pass:** no "This site has been updated in the background" placeholder anywhere.

### WP3 · Tap target — S2, cause B
Tap a notification on a locked phone. It must open the `navigate` URL — the same
`DMLink` the Discord button uses.
**Pass:** correct deep link from a cold start of the browser.

### WP4 · Dead subscriptions get pruned — S3, cause B
Uninstall the PWA / clear site data so the push service starts answering
`404`/`410`, then send again.
**Pass:** the row is deleted, not retried forever.

### WP5 · Push follows the DM opt-in — S2, cause B
Turn `dm_notifications` off and send. Push is a mirror of the DM path, so it must
go silent too.
**Pass:** no push while delivery is off. Verify the profile UI says so.

### WP6 · Key stability — S1, cause B
Confirm the production `VAPID_PRIVATE_KEY` is backed up and will not be
regenerated by a deploy. **Rotating it invalidates every subscription**, and
every attendee would have to re-subscribe from their phone mid-event.
**Pass:** key is in the secret store, documented as never-rotate, and distinct
from the rehearsal stack's.

---

## S4 · Randomizer upstreams

`MOCK_SEEDGEN` returns a fake `mock.seedgen.local` permalink; the HTTP paths in
`seedgen_service.py` are named in the coverage gaps.

### RG1 · Every live randomizer rolls — S1, cause A
Roll one real seed each for the generators the October tournaments will use:
`alttpr`, `ff1r`, `z1r`, `smmap`, `ootr`, `dk64r`. Open each permalink.
**Pass:** every one returns a playable seed at a live URL.

### RG2 · Per-tenant credentials resolve — S1, cause A
Keys are **not** environment variables — each community sets its own on
Admin → Randomizer Keys. Confirm the rehearsal tenant's keys are used, and that a
randomizer whose key is missing is dropped from the selector rather than offered
and then failing at roll time.
**Pass:** correct key used; unconfigured randomizers are not selectable.

### RG3 · Triforce texts land in the seed — S2, cause A
Roll an `alttpr` seed for a tenant with triforce texts configured and confirm the
text is in the generated game, not just in our database.
**Pass:** community text present in the rolled seed.

### RG4 · Presets reach the upstream — S1, cause A
For the two preset-aware generators (`alttpr`, `dk64r`), roll from a preset the
tournament will actually use and verify the settings on the permalink match the
preset. A preset that silently rolls defaults is a tournament run on the wrong
settings.
**Pass:** settings on the rolled seed match the preset, field by field.

### RG5 · DK64R's long roll — S2, cause A
Its upstream is a task queue whose whole submit→poll→result cycle legitimately
runs for minutes, and it gets exactly **one** attempt because a retry would submit
a second generation task. Roll one and time it.
**Pass:** completes inside the budget; no duplicate task submitted; the UI shows
progress rather than looking hung.

### RG6 · Upstream failure is a clean failure — S1, cause A
Point one randomizer at a bad key, and separately roll while the upstream is
unreachable (block it at the firewall). The failure must surface as a user-facing
error with no half-written seed on the match.
**Pass:** clear message, match left rollable, error captured in Sentry.

### RG7 · Stub randomizers — S3, cause A
`mmr`, `smdash` and `wwr` are registered but not wired. Confirm they are not
offered for an October tournament, and that rolling one raises cleanly.
**Pass:** not selectable; no traceback reaches the user.

### RG8 · Two staff roll the same match at once — S1, cause C/D
The per-match seed lock is an **in-process singleton**. Two admins on two
browsers press Roll on the same match simultaneously.
**Pass:** one seed, not two; the loser gets told, not a silent overwrite.

---

## S5 · racetime.gg runtime

A long-lived websocket per category. `MOCK_RACETIME` drives a scripted fake.

### RT1 · Bots connect on boot — S1, cause B
With `RACETIME_BOT_ENABLED=true` and a real category bot configured, boot and
confirm one connection per active `RacetimeBot` row, visible on the service-health
board.
**Pass:** connected, category correct, credentials accepted.

### RT2 · Open a room from the app — S1, cause B
Open a race room for a scheduled match and confirm the room appears on
racetime.gg with the room profile's settings (goal, visibility, streaming rules,
auto-start) applied.
**Pass:** room exists with the intended configuration.

### RT3 · The full race lifecycle comes back — S1, cause B
Run an actual race in the room with two accounts: join, ready, start, finish one
racer, forfeit the other. Watch the `Match` and `RacetimeRoom` rows follow.
**Pass:** every state transition is reflected; final result recorded correctly,
including the forfeit.

### RT4 · Auto-open worker — S2, cause B/D
Opt a tournament into auto-open and schedule a match near-term. The worker should
open the room ahead of it, once.
**Pass:** room opens at the right lead time; a second worker tick does not open a
second room.

### RT5 · `require_racetime_link` — S2, cause A
With the flag on, a player whose racetime identity is not linked must be blocked
with an explanation, and one who links it must then pass. Use real linked
identities, since the mock hands out canned ones.
**Pass:** blocked, told why, unblocked after a real link.

### RT6 · Reconnect — S1, cause B
Drop the network under a live room. The connection must come back without a
restart and without losing the room's state.
**Pass:** reconnects; in-flight race unaffected.

### RT7 · racetime.gg is down — S2, cause B
Block racetime at the firewall during a scheduled window.
**Pass:** the app stays up and every other surface keeps working; health board
shows it down; the runbook's manual fallback is usable.

---

## S6 · SpeedGaming ETL

### SG1 · Real feed materializes matches — S1, cause A
With `SPEEDGAMING_SYNC_ENABLED=true` and the real event slug on a
`SpeedGamingEventLink`, poll the live feed.
**Pass:** episodes become `Match` rows with the right players, times and channels.

### SG2 · Changes propagate — S1, cause A
Reschedule and cancel an episode upstream, then let the next poll run.
**Pass:** the local match follows; a cancelled episode does not leave a ghost match.

### SG3 · Repeated polls do not duplicate — S1, cause A
Let the worker run several cycles over an unchanged feed.
**Pass:** row counts stable; no duplicate matches; no DM re-sent per poll.

### SG4 · Feed unreachable — S2, cause A
Block speedgaming.org.
**Pass:** the worker logs and keeps its schedule rather than dying; it recovers on
its own when the feed returns.

---

## S7 · Provider account links

Mock mode short-circuits the OAuth round trip entirely — `is_mock()` is checked
in the link page and the link is recorded on the spot, so the **provider callback
never runs**.

### PL1 · racetime link — S1, cause A
Real OAuth against racetime.gg. Link, confirm the stored identity matches the
account, unlink, re-link.
**Pass:** round trip completes; no token stored (the code is exchanged once and discarded).

### PL2 · Twitch link — S2, cause A
Same shape against Twitch.
**Pass:** as above.

### PL3 · Challonge, both doors — S2, cause A
One callback serves two flows. Run the **per-player** link (`me` scope) and the
staff **service connection** on `/admin/challonge` with the full scope list, and
confirm a non-admin hitting the admin door is refused.
**Pass:** both flows work; wrong-door refusal holds.

### PL4 · Challonge token expiry — S2, cause A
The service connection's token expires. Check the health board reports
`CREDENTIAL_WARNING` as expiry approaches and `DOWN` after, and that re-authorizing
clears it. If any Challonge-mirrored tournament runs in October, this must be
green going in.
**Pass:** warning fires early enough to act on.

### PL5 · Handoff on a real domain — S1, cause A
Repeat the cross-host link handoff from ID2 with a **real** custom domain and real
TLS rather than `*.localhost`. `scheme_for_host` forces `https` off localhost, so
this path has genuinely never run against a real certificate.
**Pass:** link completes on the custom domain.

### PL6 · Identity already linked to someone else — S3, cause A
Try to link a provider identity another account already holds.
**Pass:** refused with a message that says which account, not a traceback.

---

## S8 · Outbound integrations

### WH1 · Webhook to a real receiver — S2, cause B
Point a webhook at a real HTTPS endpoint outside our network and fire an event.
Verify the signature **on the receiver** with the shared secret.
**Pass:** delivered, signature validates, payload timestamps are UTC.

### WH2 · A failing receiver — S2, cause B
Make the receiver return 500, then a connection reset, then recover.
**Pass:** retries and backoff behave; the delivery log shows each attempt; recovery
delivers without manual intervention.

### WH3 · A slow receiver does not stall the app — S1, cause D
Make the receiver hang for 60 seconds and fire several events while a browser
session is open. One process, one event loop.
**Pass:** the UI stays responsive throughout.

### API1 · REST from outside — S2, cause A
Call the API from off-network with a real personal token over TLS through the
reverse proxy.
**Pass:** authenticates, resolves the right tenant, returns UTC timestamps.

### API2 · The shared rate budget — S2, cause A
`API_RATE_LIMIT_PER_MIN` is **shared by REST and MCP** — one credential, one
budget. Exhaust it from REST and confirm MCP is limited too, and that the limit
keys on the token (or client IP) as intended behind the proxy. If
`TRUST_PROXY_FORWARDED_FOR` is on, confirm a spoofed `X-Forwarded-For` cannot
inflate the budget.
**Pass:** budget shared, keying correct, 429s are clean.

### MCP1 · A real MCP client connects — S2, cause A
Connect a real client (Claude) to `/mcp` on the rehearsal stack: discovery, OAuth,
the consent screen, tool listing.
**Pass:** connects; the consent screen names the right scopes.

### MCP2 · Write scope — S2, cause A
On a connection whose consent approved match writes, perform one. On a read-only
connection, attempt the same.
**Pass:** the write lands and is audited to the right actor; the read-only
connection is refused.

### MCP3 · The proxy passes it through — S1, cause D
`/mcp` and `/.well-known/*` must reach the app **unrewritten**, and `BASE_URL`
must be the public URL — it is the MCP resource identifier and the OAuth issuer,
both of which clients compare against what they requested. DNS-rebinding
protection is deliberately off because `Host` and TLS terminate at the proxy.
**Pass:** discovery documents advertise the public URL; a client that compares
them connects.

---

## S9 · PostgreSQL and concurrency

The `postgres` CI job covers row locks and tenancy over `tests/postgres/` and
`tests/tenancy/`. What it does not cover is concurrency **through the running
app**.

### PG1 · Migrations against real data — S1, cause C
Restore the production snapshot and boot. `init_db()` runs Aerich `upgrade()`
before serving. **Time it**, and check for any migration that rewrites a large
table.
**Pass:** chain applies; total boot time is known and acceptable as a deploy
window. If it is long, the runbook needs a maintenance-window note.

### PG2 · Double-click the qualifier draw — S1, cause C/D
`AsyncQualifierRepository.lock_user_for_draw` exists so two simultaneous draw
clicks cannot both open a run — and it is a **silent no-op on SQLite**, so no
SQLite test can tell whether it is there. Two browsers, same user, press Draw
simultaneously.
**Pass:** exactly one run opens.

### PG3 · Race for the last crew slot — S2, cause C/D
Two volunteers sign up for the same single remaining slot at the same moment.
**Pass:** one wins; the other is told the slot is gone, not silently dropped or
double-booked.

### PG4 · Concurrent result writes — S2, cause C/D
Two staff record different results on the same match simultaneously.
**Pass:** deterministic outcome, and the audit log shows both attempts.

### PG5 · Pool under load — S1, cause D
During the S12 load run, watch PostgreSQL connection count and the app's pool.
**Pass:** no pool exhaustion at peak; headroom recorded.

### PG6 · Backup and restore drill — S1, cause D
Take a backup of the rehearsal database, destroy it, restore it, boot.
**Pass:** the app comes up on restored data. **Record the elapsed time** — that
number is the event's actual recovery objective, and if nobody has measured it
the answer during the event is "we don't know".

---

## S10 · Deployment and operations

### OP1 · Ship the image we will ship — S1, cause D
Pull the GHCR image (`ghcr.io/tcprescott/wizzrobe`) by the exact tag October will
run, not a local `build: .`, and boot it.
**Pass:** the published image boots and serves.

### OP2 · Single worker holds — S1, cause D
Confirm production runs `--workers 1`. Raising it breaks the DM queue, the seed
lock, the racetime connections, the `match_live` subscribers, the OAuth handoff
nonce store, NiceGUI client state, and races Aerich at boot.
**Pass:** one worker, verified in the running container, and the constraint is
written where whoever deploys will see it.

### OP3 · Restart mid-event — S1, cause D
With sessions open, a race live, and DMs queued, restart. Time the outage.
**Pass:** measured downtime, a list of what is lost (queued DMs — see DC6), and
sessions surviving (ID5). All three go in the runbook.

### OP4 · The proxy in front — S1, cause D
Exercise the real reverse-proxy config: TLS, `X-Forwarded-Host`/`-Proto` with
`TRUST_FORWARDED_HOST` on, websocket upgrade for NiceGUI, and long-lived
connections not being cut by an idle timeout mid-match.
**Pass:** host and scheme resolve correctly; the websocket stays up for hours.

### OP5 · `BASE_URL` is right — S1, cause D
A stale `BASE_URL` bakes an unreachable host into printed equipment QR labels and
into every DM deep link. Check the label sheet's encoded-host warning, one DM
link, and the MCP resource identifier.
**Pass:** all three name the real public host.

### OP6 · Fail-fast checks actually fail — S2, cause D
Deliberately boot with a blank `STORAGE_SECRET`, with a short one under
`ENVIRONMENT=production`, and with `MOCK_DISCORD=true` in production.
**Pass:** each refuses to start. The mock check especially — it is a complete
authentication bypass.

### OP7 · Three days of logs and disk — S2, cause D
Project log volume and database growth over the event from the load run.
**Pass:** disk headroom for the weekend plus margin; rotation configured.

### OP8 · Rollback — S1, cause D
Roll back to the previous image **after** a migration has applied. This is the
one that surprises people: migrations are not reversed by pulling an old image.
**Pass:** either it works, or we know it does not and the runbook says
roll-forward-only.

---

## S11 · Real devices and the venue

All mobile verification so far is emulated Playwright at 390×844 / 360×800.

### RD1 · A real device pass — S1, cause E
Borrow the actual phones the crew will use — a spread of iOS and Android, at
least one small screen and one older device. Walk the player, crew, volunteer and
proctor surfaces in both light and dark mode.
**Pass:** every row action reachable, nothing off-screen, no horizontal scroll,
readable in both themes.

### RD2 · Screen lock and resume — S1, cause E
Open a live page, lock the phone, wait five minutes, unlock. Then background the
browser and return. The NiceGUI websocket lifecycle across lock/background/resume
is explicitly unverified on real hardware.
**Pass:** the page reconnects and shows current data — not a stale board a
volunteer then acts on.

### RD3 · Native date and time pickers — S2, cause E
Every `type=date` / `type=time` input on a real iOS and a real Android keyboard.
**Pass:** the value that lands in the database is the one the person picked, in
the right zone.

### RD4 · Printed QR labels — S2, cause E
Print the equipment label sheet on the printer the event will use, at the size it
will use, and scan the labels with real phone cameras under venue lighting.
**Pass:** scans first try; the encoded host matches the host being browsed.

### RD5 · Venue network — S1, cause E
On the venue wifi if at all possible, otherwise a deliberately degraded
connection: high latency, packet loss, a captive portal, a dead spot mid-action.
**Pass:** the app recovers when signal returns; a submit during a dropout either
completes or clearly fails — never silently loses the write.

### RD6 · The proctor station board on station hardware — S1, cause E
Run the proctor workflow — check-in, station assignment, start, finish, result,
flag for review — on the actual station machines and screens.
**Pass:** usable at that screen size and distance; the whole workflow completes.

---

## S12 · Load and capacity

One worker, one event loop, one machine. Everything about capacity is a guess
until measured.

### LD1 · Peak concurrent viewers — S1, cause D
Drive the expected peak concurrent session count (players, crew, volunteers,
spectators) against the rehearsal stack on production-sized data. Include real
browser sessions holding websockets, not only HTTP.
**Pass:** page loads stay acceptable at peak; record the number and the headroom.

### LD2 · Publish day under load — S1, cause D
Run DC5's fan-out **while** LD1's load is running. This is the actual October
morning: the schedule goes out while everyone is refreshing.
**Pass:** the UI stays responsive while the queue drains; measure both.

### LD3 · Spectator views — S2, cause D
The cached `/live/…` bracket views take no websocket. Load them at spectator scale.
**Pass:** they hold up, and they do not drag the interactive app down with them.

### LD4 · Report pages — S3, cause D
Reports reload the whole page on a filter change — measured at ~1.2 s on crew and
~1.4 s on telemetry against seeded data. Re-measure against production-sized data
under load.
**Pass:** still tolerable for the admins who will use it, or the runbook tells
them to run reports off-peak.

---

## S13 · Observability

### OB1 · Sentry receives real errors — S1, cause D
`application/utils/sentry.py` is instrumentation wiring run only at process
start, and is uncovered. Trigger a real error on the rehearsal stack.
**Pass:** the event arrives, tagged with the environment and the logged-in user;
the rehearsal project is separate from production's.

### OB2 · Health probes against real hosts — S2, cause A
With `SERVICE_HEALTH_ENABLED=true`, let the probe loop run against real
Discord, racetime, SpeedGaming, Challonge and PostgreSQL. Then break one and
watch the transition.
**Pass:** statuses are accurate — under mocks every probe reports healthy with a
"Mock …" detail string, which tells us nothing.

### OB3 · Alerts reach a human — S1, cause A
With `SERVICE_HEALTH_ALERT_DM=true`, force an unhealthy transition.
**Pass:** every super-admin gets the DM, the `service_health.alert` event
publishes, and Sentry captures it. Confirm the on-call person for October is
actually a super-admin.

### OB4 · Telemetry at volume — S3, cause D
Capture is on by default and mirrors every published event. Check the write volume
during the load run, and confirm `TELEMETRY_ENABLED=false` stops capture without
breaking reads.
**Pass:** no measurable drag; the kill switch works if we need it mid-event.

---

## S14 · Clocks

### TZ1 · Pinned versus follow-the-viewer — S2, cause E
Set the community to a pinned timezone and check a schedule; switch it to
follow-the-viewer and check the same schedule from a device in another zone.
**Pass:** both render correctly; no raw UTC anywhere user-facing.

### TZ2 · Browser zone detection — S2, cause E
From a device genuinely in another timezone (a remote crew member's laptop, or a
phone with its zone changed), confirm the `wiz_tz` cookie is set and the fallback
chain — user timezone, then browser, then community default — resolves in order.
**Pass:** an out-of-region volunteer sees their own clock, not the venue's.

### TZ3 · Discord timestamps — S2, cause A
Discord gets native `<t:unix:F>` markup so each recipient's client localizes it.
Have two people in different timezones read the same DM.
**Pass:** each sees their own local time.

### TZ4 · Machines stay on UTC — S2, cause A
REST responses and webhook payloads.
**Pass:** UTC, unambiguous, with offsets where the schema says so.

### TZ5 · The DST boundary — S3, cause E
The October event does not cross a US DST change, but anything scheduled through
the app for early November does. If post-event scheduling matters, book a match
either side of the boundary and confirm both render correctly.
**Pass:** no hour drift across the change.

---

## Results

| ID | Sev | Owner | Run on | Result | Notes / issue |
|---|---|---|---|---|---|
| ID1 | S1 | | | | |
| ID2 | S1 | | | | |
| ID3 | S1 | | | | |
| ID4 | S1 | | | | |
| ID5 | S2 | | | | |
| ID6 | S2 | | | | |
| DC1 | S1 | | | | |
| DC2 | S1 | | | | |
| DC3 | S1 | | | | |
| DC4 | S2 | | | | |
| DC5 | S1 | | | | |
| DC6 | S1 | | | | |
| DC7 | S2 | | | | |
| DC8 | S2 | | | | |
| WP1 | S2 | | | | |
| WP2 | S2 | | | | |
| WP3 | S2 | | | | |
| WP4 | S3 | | | | |
| WP5 | S2 | | | | |
| WP6 | S1 | | | | |
| RG1 | S1 | | | | |
| RG2 | S1 | | | | |
| RG3 | S2 | | | | |
| RG4 | S1 | | | | |
| RG5 | S2 | | | | |
| RG6 | S1 | | | | |
| RG7 | S3 | | | | |
| RG8 | S1 | | | | |
| RT1 | S1 | | | | |
| RT2 | S1 | | | | |
| RT3 | S1 | | | | |
| RT4 | S2 | | | | |
| RT5 | S2 | | | | |
| RT6 | S1 | | | | |
| RT7 | S2 | | | | |
| SG1 | S1 | | | | |
| SG2 | S1 | | | | |
| SG3 | S1 | | | | |
| SG4 | S2 | | | | |
| PL1 | S1 | | | | |
| PL2 | S2 | | | | |
| PL3 | S2 | | | | |
| PL4 | S2 | | | | |
| PL5 | S1 | | | | |
| PL6 | S3 | | | | |
| WH1 | S2 | | | | |
| WH2 | S2 | | | | |
| WH3 | S1 | | | | |
| API1 | S2 | | | | |
| API2 | S2 | | | | |
| MCP1 | S2 | | | | |
| MCP2 | S2 | | | | |
| MCP3 | S1 | | | | |
| PG1 | S1 | | | | |
| PG2 | S1 | | | | |
| PG3 | S2 | | | | |
| PG4 | S2 | | | | |
| PG5 | S1 | | | | |
| PG6 | S1 | | | | |
| OP1 | S1 | | | | |
| OP2 | S1 | | | | |
| OP3 | S1 | | | | |
| OP4 | S1 | | | | |
| OP5 | S1 | | | | |
| OP6 | S2 | | | | |
| OP7 | S2 | | | | |
| OP8 | S1 | | | | |
| RD1 | S1 | | | | |
| RD2 | S1 | | | | |
| RD3 | S2 | | | | |
| RD4 | S2 | | | | |
| RD5 | S1 | | | | |
| RD6 | S1 | | | | |
| LD1 | S1 | | | | |
| LD2 | S1 | | | | |
| LD3 | S2 | | | | |
| LD4 | S3 | | | | |
| OB1 | S1 | | | | |
| OB2 | S2 | | | | |
| OB3 | S1 | | | | |
| OB4 | S3 | | | | |
| TZ1 | S2 | | | | |
| TZ2 | S2 | | | | |
| TZ3 | S2 | | | | |
| TZ4 | S2 | | | | |
| TZ5 | S3 | | | | |
