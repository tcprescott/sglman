# Pre-event validation plan

_What has to be tested by hand against real infrastructure before the October
event, because no mock and no browser driver can reach it. Transient — delete
this directory once the event is over._

- **[test-cases.md](test-cases.md)** — the cases themselves, grouped into fourteen suites
- **[day-of-runbook.md](day-of-runbook.md)** — the morning smoke check and what to do when an upstream dies mid-event

## What already covers what

Four loops run before this plan starts, and nothing here should duplicate them:

| Loop | Reaches | Blind to |
|---|---|---|
| `poetry run pytest` | services, repositories, API routers in-process, tenancy leaks, bracket maths | anything over a socket; PostgreSQL-only behaviour except the `postgres` job |
| [`/ui-validation`](../../development.md) | real browser, real Postgres, seeded data, Vue/Quasar slots, mobile viewports (emulated) | every external service (mocked), real devices, real networks |
| [`/api-validation`](../../development.md) | the live ASGI stack — middleware, rate limiting, token→tenant resolution | upstream calls the endpoints make; a real client's TLS and proxy path |
| [`/discord-ux`](../../development.md) | embed and DM builders rendered offline | delivery, buttons, the gateway, anything Discord actually does |

Everything below is what falls through all four.

## The gap, by cause

There are exactly five reasons a feature lands in this plan. Every case names one.

**A — the mock is a different program.** `MOCK_DISCORD`, `MOCK_RACETIME`,
`MOCK_SEEDGEN`, `MOCK_CHALLONGE`, `MOCK_TWITCH`, `MOCK_SPEEDGAMING` each swap in a
canned client. They prove our call sites work; they prove nothing about the
protocol, the credentials, the rate limits, or the upstream's error shapes. The
Discord doc says it plainly: button interactions "need a live bot connection and
cannot be exercised in mock mode".

**B — the transport is the feature.** Web push is encryption plus a POST to
Apple's, Google's and Mozilla's push services. racetime rooms are a long-lived
websocket. A local fake exercises our framing and nothing else.

**C — SQLite is not PostgreSQL.** `SELECT … FOR UPDATE` is a silent no-op on
SQLite, so no SQLite test can tell whether `lock_user_for_draw` is there. The
`postgres` CI job covers the row-lock and tenancy cases; concurrency *through the
running app* is not covered anywhere.

**D — one process, one machine, real load.** `uvicorn --workers 1` is a hard
requirement, and the DM queue, the seed lock, the racetime connections, the
`match_live` subscribers and the NiceGUI client tree are all in-process
singletons. How they behave under an event's concurrency, and across a restart
mid-event, is untested by construction.

**E — the hardware is a person's phone.** Every mobile and dark-mode pass so far
has been Playwright at 390×844. Never verified on real hardware: the NiceGUI
websocket across screen lock and resume, the native `type=date`/`type=time`
pickers, printed QR labels under a scanner, and venue wifi.

## The rehearsal stack

Most of this plan needs a deployment that is production in every respect except
the audience. Stand it up once and keep it for the whole window.

| | Rehearsal stack |
|---|---|
| Host | its own box or VM, its own domain, real TLS through the same reverse proxy config as production |
| `ENVIRONMENT` | `production` — this is the point; every `MOCK_*` is refused, so nothing can silently fake a pass |
| Database | a **restored snapshot of production**, not `seed_dev.py`. Migration timing and query plans are meaningless against 40 seeded rows |
| Discord | a **separate** Discord application and bot in a **separate** test guild, with the real role structure mirrored. Never point a rehearsal bot at the production guild — it will DM real people |
| Randomizers | the real per-tenant keys, entered on Admin → Randomizer Keys, on a tenant that exists only for rehearsal |
| racetime.gg | a real category bot, `RACETIME_BOT_ENABLED=true` |
| SpeedGaming | `SPEEDGAMING_SYNC_ENABLED=true` against the real feed and the real event slug |
| VAPID | its **own** key pair. Sharing production's would let the rehearsal push to real attendees' phones |
| Sentry | its own project, so rehearsal noise never buries a real event error |
| Workers | every switch this event depends on turned **on**: `DISCORD_EVENTS_SYNC_ENABLED`, `SERVICE_HEALTH_ENABLED`, `SERVICE_HEALTH_ALERT_DM` |

Two standing rules for the window:

- **Nothing in this plan runs against the production Discord guild or production
  VAPID keys.** A misfired rehearsal DM to 200 attendees is worse than the bug it
  was hunting.
- **Restore the snapshot fresh before each full pass.** Half the cases mutate
  state (drawn qualifier runs, opened rooms, sent DMs), and a second pass over
  dirtied data quietly stops testing what it claims to.

## Schedule

Today is 2 August. The window is about ten weeks; the ordering is by
_how long a fix takes_, not by risk. Anything needing an upstream's cooperation —
a Discord app review, a racetime category grant, a randomizer API key — is first,
because those have lead times we do not control.

| When | Suites | Why then |
|---|---|---|
| **T-10 → T-8** (Aug) | S1 identity, S4 randomizers, S5 racetime, S6 SpeedGaming, S7 provider links | Every one can be blocked by a third party. Find that in August, not October |
| **T-8 → T-6** | S2 Discord live, S3 web push | Needs S1's guild and app in place; iOS push in particular has a slow feedback loop |
| **T-6 → T-4** | S8 outbound integrations, S9 PostgreSQL concurrency, S13 observability | Fixes here are ours alone, so they can sit later |
| **T-4 → T-3** | S10 deployment and ops, S14 clocks | Ops rehearsal is only meaningful once the build is close to what ships |
| **T-3 → T-2** | S11 real devices, S12 load | Needs the near-final UI. Borrow real phones from the crew who will use them |
| **T-2** | **Full dress rehearsal** — a complete simulated match day on the rehearsal stack, all suites re-run as a smoke pass | The only case that tests the suites *interacting* |
| **T-1** | Re-run anything that failed, then freeze | A fix landing the week of the event is a fix nobody has run |

The dress rehearsal at T-2 is the one immovable item. If time is short, cut
individual cases and keep it.

## Severity, and what it means

Each case carries one. This is the triage rule, agreed before the testing starts
so it is not being argued about in October.

| | Meaning | If it fails |
|---|---|---|
| **S1 — blocks the event** | The event cannot run as planned | Fix, or write the manual fallback into the runbook and rehearse *that* |
| **S2 — degrades the event** | It runs, but staff do manual work all weekend | Fix if there is time; otherwise the runbook gets a workaround and the staff running that surface get told |
| **S3 — cosmetic or recoverable** | Someone notices, nobody is blocked | Log it, fix after |

A case with no owner is a case that will not be run. Fill the owner column in
[test-cases.md](test-cases.md) before the window opens, and treat an unclaimed
S1 as a scheduling problem to escalate now rather than a testing problem to
discover later.

## Sign-off

The event is go when every S1 has passed on the rehearsal stack *and* the day-of
smoke check in [day-of-runbook.md](day-of-runbook.md) has been walked end to end
by someone who is not the person who wrote it.
