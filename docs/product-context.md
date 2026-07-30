# Product Context

Who uses Wizzrobe, at what scale, and what failure costs. Every other doc in this
tree describes *mechanism*; this one records the *situation* the mechanism serves,
so a design decision can be argued against something other than taste.

Captured from the maintainer, 2026-07. Treat as authoritative until contradicted;
revise in place rather than appending a second snapshot.

## History

Wizzrobe's first tenant is **SpeedGaming Live**, and its first production use was
**October 2025** — in a much cruder form than what's in this tree today (see git
history for that era). The project was originally named **SGLMan**
("SpeedGaming Live Manager"), reflected in this repo's name (`sglman`).

Its original purpose was narrow: simplify operations during SGL's on-site
tournament. That purpose broadened once it became clear how much overlap exists
between on-site tournament operations and running an **online tournament via
racetime.gg** — a problem space the maintainer had already solved once in a prior
Discord bot, **Sahasrahbot** (github.com/tcprescott/sahasrahbot). Wizzrobe brought
that functionality forward rather than leaving it to age in a separate codebase.
The **Async Qualifier** feature is a direct port of Sahasrahbot's async tournament
functionality, rebuilt Discord-native rather than command-driven.

The resulting goal is broader than the original one: a **unified platform for
speedrunning/randomizer tournament operations**, spanning both on-site and online
events, not just SGL's annual show.

## The situation

| Dimension | Reality |
|---|---|
| Live tenants | **One.** Multitenancy is built and load-bearing in code, but has one occupant. |
| Second tenant | **Opportunistic** — say yes if asked, not being chased. |
| Peak concurrency | **500+, spiky**, and **mostly signed-out spectators**. |
| Primary surface | **The web app.** Discord is the notification channel, not the product. |
| Cadence | One flagship on-site restream event per year, **plus continuous online tournaments**. |
| Stakes | **Sponsored / semi-professional.** Sponsors raise the reliability bar; they ask for nothing else. |
| Downtime cost | **The event stalls.** Wizzrobe is the source of truth during a live event. |
| Team | **Solo** — one developer, same person on call. |
| Deployment constraints | **None fixed.** Cost, container topology and Discord-only auth are all negotiable if the need is real. |

## Who it must work for

The weakest user is **a new community's first admin** — someone handed an empty
tenant who must configure a tournament from zero with no one to ask. That user
does not exist yet in production, but designing for them is the standing bar for
any admin surface.

The user who *does* exist in volume is the **player or crew member on the web
app**: schedule, availability, acknowledgment, crew signup. They arrive from a
Discord DM but they do the work on the site.

## What actually hurts

- **Third-party integration failure is the recurring production pain** — not
  performance, not staff error. Ranked worst: **Discord itself**, which carries
  auth, the bot, and role sync simultaneously. A Discord outage is currently a
  Wizzrobe outage, and whether that deserves a break-glass path is an **open
  question, not a settled decision**.
- **Repeat questions are the operational load.** The thing that eats the
  maintainer's time is answering the same thing over and over because the app
  does not answer it in place. This — not tenant onboarding — is why
  "make it onboardable by others" is the current priority: self-explanatory
  surfaces are load reduction, and a second community would be the side effect.
- **Deploys have gone out mid-event.** It happened, it was frightening, and
  nothing structural currently prevents a repeat.

## Implications worth holding onto

These follow from the table above and are the reason it is written down.

1. **The expensive traffic is the cheap traffic.** Peak load is signed-out
   spectators, and every NiceGUI page holds a WebSocket — so the lowest-value
   audience competes for the same single worker as the source-of-truth surface
   during the event that matters most. Public spectator views are the first
   candidate for a cheaper serving path, not the last.
2. **Reliability is the sponsor deliverable.** Sponsorship asks for no reporting,
   no branding, no data handling — only that it not fall over. Scale work is
   sponsor work.
3. **"Onboardable" means self-explanatory, not self-serve.** The goal is a surface
   that answers its own questions. A signup funnel would not address the load
   that prompted the priority.
4. **Solo on-call bounds acceptable complexity.** Any design whose failure mode
   requires the maintainer to be awake and available should lose to a simpler one
   that degrades on its own.

## Known gaps in this picture

- The 500+ peak is a real observation, but its composition has not been read back
  from telemetry — the signed-out majority is inference from event shape.
- Discord-outage behaviour has never been rehearsed. Nobody knows today what
  degrades gracefully and what hard-fails.
