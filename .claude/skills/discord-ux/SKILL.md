---
name: discord-ux
description: >-
  Reconstruct and assess the Discord bot's user-facing surface — the colour-coded
  embed cards, DMs, and interactive buttons SGL On Site sends (match lifecycle,
  crew, seeds, volunteer shifts). Discord cannot be driven headlessly and
  MOCK_DISCORD never connects a bot, so the surface is inspected by rendering the
  real embed + message builders and reproducing Discord's DM chrome, not by
  clicking a live client. Use when asked to review the Discord UX, "see what the
  bot sends", check a notification/DM's copy, card, or buttons, or audit the
  bot's frontend. The Discord counterpart of /ui-validation (web) and
  /api-validation (REST).
---

# Discord surface reconstruction

The bot is a **peer presentation layer** to the web UI: `discordbot/` button
handlers call the same services the NiceGUI pages do. But unlike the web UI,
**it can't be driven in a browser** — there is no headless Discord client, and
under `MOCK_DISCORD=true` (this repo's dev/test default) the bot never connects;
`MockDiscordService` just prints `[MOCK Discord DM] ...` to stdout. So the way to
"see" the surface is to **render what the builders produce and reproduce how
Discord displays it** — the copy and button styles are fully determined by code.

## What the surface actually is (as of this writing)

- **Every notification is sent as a colour-coded `discord.Embed` card** built in
  `application/utils/discord_embeds.py` — title + state colour, a Tournament /
  Players / Time / Stage field grid, native `<t:unix:F>·<t:unix:R>` timestamps
  (viewer-local date + live countdown), and a **community-name footer** so a user
  in several communities can tell whose DM this is.
- **The plain-text string still rides along** for the web-push mirror and the
  mock: `send_dm` sends `embed=` as the Discord representation but always mirrors
  the plain `message` to web push. So the embed layer is **additive** — the text
  builders in `discord_messages.py` are still the fallback/mirror copy.
- **No slash commands** — the bot only *sends* DMs and *receives* button clicks
  (`grep -rn 'slash_command\|app_commands\|tree.command'` → none).
- Every DM is sent via `user.send(embed=..., view=...)` (or `user.send(message,
  view=...)` when no embed) in `application/services/discord_service.py` — `view`
  is a `discord.ui.View` of buttons.
- Four button kinds, with Discord's `ButtonStyle` colors:
  | Style | Color | Buttons |
  |---|---|---|
  | `primary` | blurple `#5865F2` | Sign up as Commentator |
  | `secondary` | grey `#4e5058` | Sign up as Tracker; disabled "Acknowledged" |
  | `success` | green `#248046` | Acknowledge |
  | `danger` | red `#da373c` | Unwatch |
- Acknowledge swaps itself for a disabled **Acknowledged** button after a click
  (`make_acknowledged_view`); routing is stateless via `custom_id` prefixes.

## Where the surface is defined

| File | What lives there |
|---|---|
| `application/utils/discord_embeds.py` | **Every embed card** — `match_embed`, `state_changed_embed`, `volunteer_embed`, `notification_embed`, `time_field`, and the `COLOR_*` palette. The card shape. |
| `application/utils/discord_messages.py` | **Every DM/ephemeral string** — the plain-text mirror/fallback copy. Start here for wording. |
| `discordbot/crew_signup.py`, `match_acknowledgment.py`, `crew_acknowledgment.py`, `volunteer_acknowledgment.py`, `watch_buttons.py` | Button view factories (labels + `ButtonStyle`) and click handlers |
| `application/services/discord_service.py` | `send_dm*` methods (`user.send(embed=…, view=…)`), the web-push mirror, the mock, the `(bool, reason)` guard ladder |
| `application/services/match_schedule_service.py`, `crew_service.py`, `volunteer_schedule_service.py`, `volunteer_reminder.py` | Where each embed is **built and threaded** into the send call (titles, colours, descriptions per notification) |
| `docs/reference/discord-integration.md` | The map: flows, `custom_id` grammar, recipient fan-out, queue |

Behavior docs: `docs/features/discord-notifications.md`, `match-acknowledgment.md`,
`crew-management.md`, `tournament-notifications.md`, `match-watcher.md`.

## Step 1 — render the real surface

Run the helper to print every embed card, plain-text DM, and ephemeral reply with
representative data, by calling the actual builders (no bot, no Discord, no DB):

```bash
poetry run python .claude/skills/discord-ux/render_surface.py
```

This is the source of truth for both the card shape and the copy — never
paraphrase a DM, render it. (If a builder's signature changes, update the
helper's sample calls; the `EMBEDS` list mirrors what the services build.)

## Step 2 — reproduce Discord's rendering

**The card is the primary thing to reproduce.** Discord renders each notification
as an embed: a left **colour bar** (the state colour), a bold **title**, an
optional description, then an inline **field grid** (Tournament / Players / Time /
Stage), and a small **footer** (the community name). Below the card sits the
action row of buttons. The `<t:unix:F>·<t:unix:R>` tokens in the Time/Start/End
fields render as a viewer-local date and a live countdown ("in 2 hours").

To build a faithful visual mockup (an Artifact is ideal), reproduce Discord
**dark** DM chrome plus the embed card (a rounded panel with a 4px colour rail on
the left, muted-caps field names above their values):

```
--dc-bg #323540   --dc-text #d6d9df   --dc-strong #f3f4f6   --dc-muted #969ba5
--dc-link #00a8fc  --dc-embed-bg #2b2d31  (card)  --dc-field-name #b5bac1 (caps)
state colours: scheduled #5865F2 · rescheduled/checked-in #B45309 · started #557A1F
               finished #6B6258 · confirmed #0E7470 · stream #E0A82E · seed #8250DF · volunteer #0E7470
buttons: primary #5865F2 · secondary #4e5058 · success #248046 · danger #da373c
```

Render the colour rail from the embed's colour, `**x**` as bold, autolink bare
`https://…`, and put the correct button row under each card (see the flow table
in `docs/reference/discord-integration.md` for which buttons ride which DM).
Ephemeral replies get an "Only you can see this" header. Discord DMs are dark for
almost everyone — a single dark treatment for the panels is the honest default.

## Step 3 — apply the UX checklist

Read each rendered card + DM against these (the recurring issues on this surface):

- **Tenant safety** — no hardcoded community/org name (the app is multi-tenant;
  a fixed "SGLive"/"SpeedGaming" is wrong for every other community). `grep -niE
  'sglive|speedgaming|sgl on site' application/utils/discord_messages.py`. The
  *"SGL On Site account"* login line is fine — identity is global.
- **Community footer present** — every embed should carry the community-name
  footer (`TenantService.current_community_name()`, best-effort → '' when no
  tenant). A card with an empty footer in a real tenant context is the bug to
  catch; a missing footer in a DB-less render is expected.
- **State colour matches the event** — the `COLOR_*` constant must match the
  lifecycle state (scheduled=blurple, checked-in=amber, started=olive,
  finished=gray, confirmed=teal, seed=purple, stream=gold). A miscoloured card
  reads as the wrong state at a glance.
- **No duplicated fields** — a builder or embed that shows two labels sourced from
  the same value (e.g. a match `title` that equals the player roster) prints it
  twice. Guard by suppressing the redundant field when the values match.
- **Times use `<t:>` tokens** — embed Time/Start/End fields must come from
  `time_field()` (raw UTC → `<t:unix:F>·<t:unix:R>`), never a pre-formatted
  Eastern string. The plain-text mirror still uses the Eastern string — that's
  correct, because `<t:>` tokens only render inside Discord, not in web push.
- **Consistent block spacing (text mirror)** — the plain-text DMs should share one
  rhythm: intro, detail block, call-to-action, separated by blank lines (`\n\n`).

## Step 4 — verify any fix without a live bot

Embed builders are unit-tested in `tests/test_utils_coverage.py` (class
`TestDiscordEmbeds` — colours, `time_field`, field suppression, footer). Plain-text
builder copy is covered by **substring/prefix/suffix** assertions in the same file
(`TestCrewAssignmentDm`, `TestVolunteerDms`, etc.). The embed **threading** (which
`send_dm*` call gets which embed) is asserted in
`tests/services/test_match_schedule_service.py` and `test_match_schedule_coverage.py`
(the `embed=` kwarg in the `assert_awaited_*with` calls). Run `poetry run pytest
tests/test_utils_coverage.py tests/services/test_match_schedule_service.py -q`
after editing an embed or a builder. There is **no** live button-interaction test
(needs a real bot); the handlers are exercised only through their service calls.

## Files

- `render_surface.py` — prints every embed card, plain-text DM, and ephemeral
  reply with sample data by calling the real builders. The discovery-heavy part;
  run it first.
