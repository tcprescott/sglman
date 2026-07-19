---
name: discord-ux
description: >-
  Reconstruct and assess the Discord bot's user-facing surface — the DMs and
  interactive buttons SGL On Site sends (match lifecycle, crew, seeds, volunteer
  shifts). Discord cannot be driven headlessly and MOCK_DISCORD never connects a
  bot, so the surface is inspected by rendering the real message builders and
  reproducing Discord's DM chrome, not by clicking a live client. Use when asked
  to review the Discord UX, "see what the bot sends", check a notification/DM's
  copy or buttons, or audit the bot's frontend. The Discord counterpart of
  /ui-validation (web) and /api-validation (REST).
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

- **All notifications are plain-text DMs with markdown `**bold**`** — there are
  **zero `discord.Embed`** uses in the codebase (`grep -rn 'discord.Embed'`).
- **No slash commands** — the bot only *sends* DMs and *receives* button clicks
  (`grep -rn 'slash_command\|app_commands\|tree.command'` → none).
- Every DM is sent via `user.send(message, view=...)` in
  `application/services/discord_service.py` — `message` is a plain string, `view`
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
| `application/utils/discord_messages.py` | **Every DM/ephemeral string** — public builder functions. Start here. |
| `discordbot/crew_signup.py`, `match_acknowledgment.py`, `crew_acknowledgment.py`, `volunteer_acknowledgment.py`, `watch_buttons.py` | Button view factories (labels + `ButtonStyle`) and click handlers |
| `application/services/discord_service.py` | `send_dm*` methods (`user.send(message, view)`), the mock, the `(bool, reason)` guard ladder |
| `docs/reference/discord-integration.md` | The map: flows, `custom_id` grammar, recipient fan-out, queue |

Behavior docs: `docs/features/discord-notifications.md`, `match-acknowledgment.md`,
`crew-management.md`, `tournament-notifications.md`, `match-watcher.md`.

## Step 1 — render the real copy

Run the helper to print every DM and ephemeral reply with representative data,
by calling the actual builders (no bot, no Discord, no DB):

```bash
poetry run python .claude/skills/discord-ux/render_surface.py
```

This is the source of truth for the copy — never paraphrase a DM, render it.
(If the builders' signatures change, update the helper's sample calls.)

## Step 2 — reproduce Discord's rendering

Discord renders each DM as: the bot's avatar + name + an **`APP`** badge +
timestamp, then the message body with `**bold**` → bold and newlines preserved,
then an action row of buttons below. To build a faithful visual mockup (an
Artifact is ideal), reproduce Discord **dark** DM chrome:

```
--dc-bg #323540   --dc-text #d6d9df   --dc-strong #f3f4f6   --dc-muted #969ba5
--dc-link #00a8fc  buttons: primary #5865F2 · secondary #4e5058 · success #248046 · danger #da373c
```

Render `**x**` as bold, autolink bare `https://…`, keep `\n` as line breaks, and
put the correct button row under each message (see the flow table in
`docs/reference/discord-integration.md` for which buttons ride which DM).
Ephemeral replies get an "Only you can see this" header. Discord DMs are dark for
almost everyone — a single dark treatment for the panels is the honest default.

## Step 3 — apply the UX checklist

Read each rendered DM against these (the recurring issues on this surface):

- **Tenant safety** — no hardcoded community/org name (the app is multi-tenant;
  a fixed "SGLive"/"SpeedGaming" is wrong for every other community). `grep -niE
  'sglive|speedgaming|sgl on site' application/utils/discord_messages.py`. The
  *"SGL On Site account"* login line is fine — identity is global.
- **No duplicated fields** — a builder that shows two labels sourced from the
  same value (e.g. a match `title` that equals the player roster) prints it
  twice. Guard by suppressing the redundant line when the values match.
- **Consistent block spacing** — DMs should share one rhythm: intro, then a
  detail block, then the call-to-action, separated by blank lines (`\n\n`), not
  a single dense newline run.
- **Times** — the builders receive pre-formatted US/Eastern strings. Discord's
  native `<t:unix:F>` / `<t:unix:R>` tokens render in each viewer's own timezone
  with a live countdown ("in 2 hours") — a real win for a scheduling bot, but a
  larger change (raw UTC must be threaded to the builders).
- **Embeds vs plain text** — plain text is functional; embeds add state-as-color
  (scheduled/live/done), field columns, and a per-community footer. A shared
  embed builder would lift the whole surface at once.
- **Community identity** — nothing marks *which* community a DM is from beyond a
  tournament name; a user in several communities can't tell them apart.

## Step 4 — verify any fix without a live bot

Builder copy is covered by **substring/prefix/suffix** assertions in
`tests/test_utils_coverage.py` (class `TestCrewAssignmentDm`, `TestVolunteerDms`,
etc.) and `tests/services/test_match_schedule_service.py`. A pure spacing/copy
change usually keeps those green — run `poetry run pytest
tests/test_utils_coverage.py -q` after editing a builder. There is **no** live
button-interaction test (needs a real bot); the handlers are exercised only
through their service calls.

## Files

- `render_surface.py` — prints every DM + ephemeral reply with sample data by
  calling the real builders. The discovery-heavy part; run it first.
