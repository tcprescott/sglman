# Day-of runbook

_The morning smoke check, and what to do when an upstream dies mid-event. Written
against production, not the rehearsal stack. Companion to
[test-cases.md](test-cases.md)._

Numbers marked **⟨measure⟩** are filled in from the rehearsal runs. A runbook
with an unfilled ⟨measure⟩ has not been rehearsed.

## Before the doors open

Twenty minutes, one person, in this order. Stop and escalate on any failure —
these are ordered so an early failure makes the later checks pointless anyway.

1. **`/platform` service-health board is green.** Discord bot connected,
   PostgreSQL responding, racetime bots connected for every active category,
   SpeedGaming reachable, Challonge tokens valid and not expiring this weekend.
   Anything amber goes on the whiteboard now, not at the first match.
2. **Log in as a real non-staff account** on a phone, on the venue wifi. Not a
   staff account and not the office network — that combination hides the two
   things most likely to be broken.
3. **Send one test DM** to yourself (schedule and unschedule a throwaway match)
   and **press its button**. Confirms the gateway, the queue and the interaction
   handlers in one action.
4. **Roll one seed** on each randomizer the day will use. Upstream keys expire
   and upstream sites have outages; find out now.
5. **Open one racetime room** and close it, if the day has races.
6. **Check disk and database size** against the projection from OP7.
7. **Confirm who is on call** and that they are a super-admin — health alerts DM
   super-admins only.

## Rules for the weekend

- **Do not restart during a schedule publish.** Shutdown counts, logs and drops
  whatever is still in the DM queue. Wait for the drain (⟨measure⟩ from DC5) or
  accept that the tail gets nothing.
- **Do not raise the worker count.** Under load the instinct is to add workers.
  It breaks the DM queue, the seed lock, the racetime connections, live view
  refresh and the OAuth handoff store, and it races Aerich at boot. Scale the box.
- **Do not deploy.** Anything that ships during the event has been run by nobody.
  If a fix is genuinely required, it goes through the same restart cost as OP3
  (⟨measure⟩ of downtime) and someone re-runs the smoke check afterwards.
- **Never set `MOCK_*` on production.** They are refused, loudly, and reaching
  for one means something else has already gone wrong.

## When an upstream dies

Each row is what actually breaks and what to do about it. The fallback column is
the thing to have rehearsed — a fallback nobody has practised is a plan, not a
mitigation.

| Down | What stops | What still works | Fallback |
|---|---|---|---|
| **Discord gateway** | DMs, all five button families, role sync at login | Everything in the web app; **web push still goes out** — the mirror fires before the bot-readiness check | Point people at the web app. Acknowledgment, crew signup and watching all exist as web controls |
| **Discord OAuth** | New logins | Existing sessions — they survive independently | Do not restart; sessions are the only thing keeping people in. Staff can act on behalf of a locked-out user |
| **racetime.gg** | Room opening, race state sync | On-site matches, brackets, everything else | Run affected races manually; record results by hand in the app |
| **A randomizer** | Rolling for that game | Every other randomizer | Roll on the randomizer's own site and paste the permalink onto the match |
| **SpeedGaming feed** | New and changed episodes syncing | Matches already materialized | Schedule by hand in the app; reconcile after |
| **Challonge** | Mirror updates | Native brackets, all match ops | If the tournament is Challonge-mirrored, update Challonge by hand after |
| **Push services** | Device notifications | Discord DMs | Nothing to do; it is a mirror |
| **PostgreSQL** | Everything | Nothing | This is the one that ends the day. Restore per PG6 (⟨measure⟩ recovery time). Staff fall back to paper for the schedule |
| **Sentry** | Error visibility | Everything | Read container logs directly |

## Escalation

| Symptom | First check | Then |
|---|---|---|
| "I didn't get a DM" | Is their `dm_notifications` on? Are their Discord DMs open to server members? | Health board for the gateway; the queue depth in logs |
| "The button says the interaction failed" | Was the DM sent before the last restart? (DC3 says it should still work) | Container logs for the handler; act for them in the web app |
| A page is blank or stale on a phone | Lock/unlock the phone to force a reconnect (RD2) | Venue wifi; then the websocket path through the proxy (OP4) |
| Everything is slow | Concurrent sessions against the LD1 number (⟨measure⟩) | PostgreSQL connections against PG5; is a report running? (LD4) |
| A seed rolled twice / two seeds on a match | Two staff pressed Roll together (RG8) | Pick one, record which, tell both racers before the match |

## After the event

Delete this directory. The plan is transient by the `docs/` convention — once the
event is over, what was learned belongs in the feature docs and in
[current-state.md](../../current-state.md), and the measured numbers belong in
[scaling-roadmap.md](../../scaling-roadmap.md), which has been asking for them.
