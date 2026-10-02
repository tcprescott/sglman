# Player journey UX — evaluation

**Scope:** the whole path of a plain member with no staff role, from the join
door to a played match. Asking to join, the approval DM, signing up on
**Tournaments**, the matchup-ready DM and its `?schedule=` deep link, booking a
bracket game, the opponent's side of that booking (acknowledge, ask to change,
agree), availability, seeds and race rooms, the bracket pages, and every Home
tab (Event › Schedule / On Air / Brackets, My Schedule, Tournaments, Profile).
The Discord DMs a player receives along the way are in scope, as is whether each
DM's link button lands on a control the recipient can use.

**Method:** read `AuthService`, `TenantMembershipService`, `TournamentService`,
`BracketService` scheduling, `MatchRescheduleService` and the notification
builders, then drove the running dev app (`./start.sh validate`, seeded
`default` tenant) with Playwright at **1440×900** and **390×844** (`isMobile`).
Two fresh accounts were minted from the mock login, `pj_alice` (desktop) and
`pj_bob` (phone), so the two-sided steps ran in two browser contexts at once.
Staff-side setup used my own rows only: a `PJ Audit Open` tournament (id 19) and
a two-entrant single-elimination stage (bracket 9, matchup 30), started from
Admin › Brackets so the DMs went through the app. Seeded `player_one`,
`player_three` and `player_four` covered states a fresh account cannot reach.
The server log was read across every click. DM text below is copied from the
`[MOCK Discord DM]` lines in `/tmp/app.log`, or rendered with
`.claude/skills/discord-ux/render_surface.py`. Anything not driven is tagged
`code-read`.

Screenshots and dumps: `/tmp/claude-0/-home-user-sglman/21037563-847e-55a4-bd9a-303508d481a4/scratchpad/player/`
(abbreviated `shots/` below).

**Headline:** the booking itself is now very good. The matchup-ready DM opens the
date picker directly, Suggest a time fills it, and booking is three taps from a
Discord notification; a stale or forwarded link says why it did nothing; two
players racing to book one matchup get one booking and a refusal. The damage is
around it. On a phone, every match board stops after its third card and paints
the rest under the next panel, so a player with fifteen matches can reach three.
The opponent of a reschedule request is asked to press an Agree button that
exists only in Discord. Acknowledging a match on the web silently removes the
Ask to change button. And the Triforce Texts button on the Tournaments tab has
never opened anything.

---

## The measured shape of the journey

| Step | Interactions | Notes |
|---|---:|---|
| Open the community link, see the door | 0 | Door explains itself; Request access is the one action |
| Optional note + **Request access** | 1–2 | Staff DM'd at once with a link to Admin › Users |
| Approval DM → **Open the community** | 1 | Lands on Event › Schedule, not Tournaments (F9) |
| Find **Tournaments** | 1 | |
| Scroll to the tournament, **Sign up** | 1 + scroll | `PJ Audit Open` card at y=2,013 px desktop, 2,506 px phone, eighth card under "Open for signup" |
| Matchup-ready DM → **Pick a time** | 1 | Dialog already open on arrival |
| **Suggest a time**, **Schedule** | 2 | "Match scheduled — your opponent will be asked to confirm." |
| Opponent: ack DM → web, tap the tick | 2 | 44×44 labelled on phone; 18×18 unlabelled on desktop (F8) |
| **Total, door to booked** | **≈8 + two scrolls** | |

---

## Findings, ranked

### F1 — Blocker · On a phone, every match board stops at its third card

`sticky_header()` caps the table at `max-height: 70vh`
([`theme/tables/preferences.py:558-568`](../../theme/tables/preferences.py#L558))
and makes `.q-table__middle` the scroll container
([`static/css/styles.css:1816`](../../static/css/styles.css#L1816)). Below
Quasar's `md` breakpoint the table renders as a grid, the cards live in
`.q-table__grid-content`, and nothing scrolls: the container measures
**591 px tall with 4,692 px of content and `overflow: visible`**. The cards
overflow onto whatever follows. Probing each card with `elementFromPoint` after
scrolling to it (`s4_reach.js`):

| Route (player_one, 390×844) | Cards on the page | Reachable and on top |
|---|---:|---:|
| `/home/schedule` (Event) | 25 (of 37; pager below) | **3**. Cards 4–25 sit past the document's end (`scrollHeight` 1,167 px), the pager with them |
| `/home/my-schedule` | 15 | **3**. Cards 4–10 are drawn underneath "Your change requests" and later panels; 11–15 are past the end |

`shots/phone-myschedule-scrolled-1100.png` shows "Your change requests" painted
across the fourth match card. Every DM that links to `/home/player` (the ack
request, the opponent's reschedule DM) can land a phone user on a board where the
match it is about is unreachable. `MatchTableView`, `UserTableView` and
`TournamentTableView` all call `sticky_header`, so this is not Home-only.

Fix shape: apply the height cap only when the table is not in grid mode (or
scroll `.q-table__grid-content` too), and re-run `s4_reach.js` against all six
callers.

### F2 — Blocker · The Triforce Texts button on a tournament card does nothing

The button spawns the dialog builder as a detached task without a client
([`pages/home_tabs/tournaments.py:217-221`](../../pages/home_tabs/tournaments.py#L217)),
so `ui.dialog()` at
[`triforce_texts.py:45`](../../pages/home_tabs/triforce_texts.py#L45) has no slot.
Driven with `FEATURE TRIFORCE_TEXTS` forced on for `default` for one click and
restored afterwards (`j3_tri.js`): no dialog, and

```
ERROR wizzrobe.ui: Unhandled exception in a UI event handler
  File "pages/home_tabs/triforce_texts.py", line 45, in open_triforce_dialog
RuntimeError: The current slot cannot be determined because the slot stack for this task is empty.
```

This is the only player surface for triforce submissions since the tab was
folded into the card, so on a community with the flag on, nobody can submit or
see their submissions. The two handlers right above it in the same file pass
`context.client` correctly; this one was missed.

### F3 — Major · The opponent is told to press Agree, and the web has no Agree

When Bob asks to move a match, Alice gets (log, 12:51):

> **PJ Bob** asked staff to move your match in **PJ Audit Open**. … Press
> **Agree** if that works for you. … `[button: View your matches -> /t/default/home/player]`

The Agree button is a Discord view
([`discordbot/reschedule_agreement.py`](../../discordbot/reschedule_agreement.py)).
`record_opponent_agreement` has two callers: that handler and
`api/routers/reschedule_requests.py:126`. No page calls it. The link button,
which is also the web-push tap target, opens Alice's board, where the text
contains neither "agree" nor "request" (`j9_alice.js`,
`shots/j9-alice-opponent-asked-d.png`). The Change requests card lists only her
own requests (`list_mine`). A player reading the push on their phone has no way
to do what it asks. The link is built at
[`_reschedule_notifications.py:117`](../../application/services/_reschedule_notifications.py#L117);
the copy at
[`discord_messages_reschedule.py:94`](../../application/utils/discord_messages_reschedule.py#L94).

Fix shape: an "Your opponent asked to move this" strip on the match row with an
Agree button, and the DM linking to it (`?match=<id>` already exists).

### F4 — Major · Acknowledging a match on the web removes its Ask to change button

Bob tapped the tick on his card (`j6_ack.js`): "You acknowledged PJ Alice vs PJ
Bob." The card re-rendered without **Ask to change**
(`shots/j6-bob-card-after-ack-m.png`); a reload brought it back
(`j7_reload.js`). `refresh()` stamps `_can_reschedule` and `_reschedule_pending`
on each row ([`theme/tables/match.py:435-436`](../../theme/tables/match.py#L435));
`update_row_by_id()` carries `_watching`, `_stream_volunteer` and the hard-preset
state across but not those two
([`match.py:601-603`](../../theme/tables/match.py#L601)). Every single-row
update loses them, including the live `match_live` flash when staff edit the
match, so the one moment a player most needs to ask for a change (staff just
moved it) is when the button vanishes.

### F5 — Major · Stage DMs tell crew "your match" and link them to an empty board

The stage reminder, assignment and clearance DMs go to the whole
`collect_match_recipients` set (players, approved crew, watchers) with one copy
and one link
([`_schedule_notifications.py:160-187`](../../application/services/match/_schedule_notifications.py#L160)).
The log at 12:38 has `player_three` and `player_four`, the commentators on match
19, receiving:

> Your match in **Wizzrobe Cup** is coming up on **Stage 1**. Players: Player One
> vs Player Two … Head to the stage rather than the tournament room.
> `[button: View your match -> /t/default/home/player?match=19]`

Opened as `player_three` (`s5_link.js`, `shots/link-commentator-match19-d.png`):
the board shows the "Showing one match only" chip over **"No matches to show
yet." and 0 matches**, with no notice. The commentary slot they are being
reminded about sits two panels further down under Crew you signed up for. The
docstring at `:107-109` chose this link because the admin board would be "a
button that looks right and does nothing for most recipients"; for crew and
watchers it is still that button. `?match=` for someone else's match gets no
stale-link notice either, unlike `?schedule=`, `?reschedule=` and `?hard=`
(`j13_stale.js`).

### F6 — Moderate · "Your opponent confirms" promises a step that does not exist

The Waiting-on-you card says "Pick a time and your opponent confirms"
([`pages/home_tabs/player.py:224, 279`](../../pages/home_tabs/player.py#L279)) and
the booking toast says "your opponent will be asked to confirm"
([`bracket_schedule_dialog.py:140`](../../theme/dialog/bracket_schedule_dialog.py#L140)).
What Bob actually receives is the acknowledgment request ("Click **Acknowledge**
below to confirm you've seen this"), and the match is booked whether or not he
presses it. He cannot decline the time; his only route is a reschedule request
that staff decide. A player who books a time their opponent never agreed to has
been told the opponent would get a say. Either say what happens ("it's booked;
your opponent can ask staff to move it") or build the confirm.

### F7 — Moderate · A booking logs an unhandled exception from the board refresh

Every successful booking from the Waiting-on-you card ends with (log,
12:49:04):

```
ERROR wizzrobe.ui: Unhandled exception in a UI event handler
  File "theme/dialog/bracket_schedule_dialog.py", line 146, in submit
  File "pages/home_tabs/player.py", line 312, in after
    await table_view.refresh()
RuntimeError: No tenant in context.
```

`after()` refreshes the bracket section and then the board, from a handler whose
dialog has just been closed, so the client stash is gone by the second call: the
"end of a chain" shape the README's cross-cutting themes already describe. The
row did appear on Alice's board (`shots/j5-alice-after-book-d.png`), most likely
through the `match_live` push, so the user-visible cost today is small. The log
line on every booking is not.

### F8 — Moderate · At 1440 the player's own actions are past the right edge

Measured header positions inside a 1,076 px-wide table that starts at x=332:

| Board | Off the right edge (viewport 1440, table edge 1408) |
|---|---|
| My Schedule › Your matches | **Change** 1373–1484 (cut), **Settings** 1484–1674, **Watch** 1674–1749 |
| Event › Schedule | **Commentators** 1398–1535, **Trackers** 1535–1634, **Watch** 1634–1709 |

Event's subtitle is "Every match, and where you can sign up as crew"; every
Sign up button on it needs a horizontal scroll, whose bar sits at the bottom of a
70vh box. On desktop the player's own buttons are icon-only 30×30 (Stream,
Change, Watch), and the Acknowledge control is an **18×18 unlabelled tick** with
a tooltip (`j17.js`; `match_slots.py:517-519`). The phone card gets the same
actions as labelled 44 px buttons, which shows the desktop row is the outlier.

### F9 — Moderate · The DM links stop one step short

Three link buttons land on a page rather than the control:

- Join approved: "Open the community" → `/home`, which is Event › Schedule
  ([`tenant_membership_service.py:312`](../../application/services/tenant_membership_service.py#L312)).
  A new member's next step is Tournaments, and `notification_links.home_tournaments()`
  already exists.
- Acknowledgment request: "View your matches" → `/home/player`, the whole list
  ([`_schedule_notifications.py:303`](../../application/services/match/_schedule_notifications.py#L303)),
  though `player_match(match_id)` exists and the stage DMs use it. For
  `player_one` that is fifteen matches, and on a phone F1 hides twelve.
- Reschedule opponent DM: see F3.

### F10 — Moderate · An online player has no route to their race room

`player_one` plays "Online Scheduled Race", whose room `alttpr/dev-room-default`
is open. My Schedule has no column, link or text naming racetime for that match
at either width (the word appears only on Profile and Tournaments, as account
linking). `RaceRoomService.create_room_for_match` and `auto_open_if_eligible`
send no DM (`code-read`, `race_room_service.py:59-150`). The room is reachable
only from racetime.gg itself.

### F11 — Moderate · Request Match offers an archived tournament

The tournament picker in Request Match lists "Wizzrobe Cup — Last Season"
(`is_active = false`) for `player_one` at both widths (`j14_req.js`).
`get_player_requestable` filters on `allow_player_match_requests` only
([`tournament_repository.py:167-168`](../../application/repositories/tournament_repository.py#L167)),
and `submit_match_request` has no `is_active` check, so the request would go
through (`code-read`; not submitted, to avoid writing to a seeded tournament).

### F12 — Moderate · Copy written for players reaches people who aren't playing

Rendered with `render_surface.py`, `code-read` for the audience:

- Tournament subscribers and crew get "You've got a match scheduled in
  **Wizzrobe Dev Tournament**. … Good luck!"
  ([`discord_messages.py:124-126`](../../application/utils/discord_messages.py#L124))
  and "Your match … got moved"
  ([`:147`](../../application/utils/discord_messages.py#L147)). A player who
  follows a tournament for alerts reads that as being drafted into someone
  else's match.
- The stage DMs in F5.
- Signing up for a bracket-run tournament DMs "Staff can now schedule you into
  its matches"
  ([`_tournament_signup.py:273`](../../application/services/_tournament_signup.py#L273)).
  In PJ Audit Open (`allow_player_match_requests` off, native bracket) the
  players book their own games.

### F13 — Minor · The booking dialog defaults to right now, and nothing refuses the past

`_defaults()` fills the current local date and minute
([`bracket_schedule_dialog.py:84-86`](../../theme/dialog/bracket_schedule_dialog.py#L84));
Bob's dialog opened on 08:48 AM. Neither `schedule_bracket_match` nor
`submit_match_request` checks for a time in the past (`code-read`; grep for
"past" in both is empty), so pressing Schedule without touching the inputs books
a match that started a minute ago.

### F14 — Minor · The stale booking refusal is machine-shaped

Bob's dialog, open while Alice booked, answered his Schedule with "All 1 game(s)
of this series are already scheduled."
([`_bracket/series.py:154`](../../application/services/_bracket/series.py#L154),
`shots/j5-bob-after-stale-book-m.png`). It does not say who booked it or when,
and the dialog stays open with a Schedule button that will fail again. "PJ Alice
already booked this for 10:30" and closing the dialog would answer the obvious
question.

### F15 — Minor · Signing up moves the card out from under you

After **Sign up**, the card moves from "Open for signup" to "My tournaments",
334 px further down (y 2,013 → 2,347 desktop; 2,506 → 2,883 phone) while the
viewport stays put. The toast confirms it, but the Withdraw button the player
might want next is no longer where they were looking.

### F16 — Minor · The bracket page forgets who is looking at it

On `/brackets/9` Alice's final shows both names, no booked time and no marker
for which entry is hers (`shots/j11-pj_alice-stage-d.png`). The page's drawer
drops Event, My Schedule and Tournaments, leaving Home plus the help links, and
the subtitle reads "1 round(s) with their own best-of", a configuration note
meant for staff.

### F17 — Minor / polish

- Phone bottom nav: the four tabs measure 373 px in a 358 px bar, so
  **Profile** sits under Quasar's scroll arrow (`j15_nav.js`).
- `?hard=999999` (no such match) says "The settings for that match are already
  decided"; `?schedule=abc` returns FastAPI's raw 422 JSON (`j13_stale.js`).
- The request guard's copy says "schedule your matchup from Your Schedule"; the
  tab is **My Schedule** (`match_request_guard.py:25-26`).
- On the join door at 390 px, the bracket buttons wrap their icon above the
  label and the card runs past the page background (`shots/j1-pj_bob-door-m.png`).

---

## What works, and should stay

- **The matchup-ready DM is the model.** `?schedule=30` opened the dialog on
  arrival for both players; Suggest a time filled 10:30 and said "review and
  save"; booking took two more taps.
- **Stale deep links explain themselves.** `?schedule=` for a booked or foreign
  matchup, `?reschedule=` for a match the player cannot change and `?hard=` all
  toast a reason instead of doing nothing (F5's `?match=` is the exception).
- **The booking race is safe.** Two open dialogs, one booking, one refusal; no
  duplicate match.
- **The join door.** One clear action, an honest pending state ("You will get a
  message either way"), DMs to staff with a link to the queue and back to the
  requester on both outcomes.
- **The reschedule request form** says up front that nothing moves until staff
  decide, and the requester's card tracks the status and staff's reply.
- **Availability** saved first time on a phone; the phone match card's
  Acknowledge is a labelled 44×44 button.

## Could not drive

- Discord button clicks (Acknowledge, Agree, Unwatch, crew signup) and web push
  delivery: no live bot under `MOCK_DISCORD`; the copy and link targets above are
  from the mock log and the renderer.
- Result reporting is staff-only (`report_result` gates on `is_staff`), so a
  player's view of a settled bracket was checked on seeded stages, not on PJ
  Audit Open.
- The harder-settings offer: no seeded tournament in `default` offers a hard
  preset to the PJ accounts.
- The race room open → player notification path (F10) is `code-read`.

## Adjacent, outside this scope

- Approving a join request on Admin › Users raises `No tenant in context` from
  `admin_users.py:103` (`decide` → `table_view.refresh`) on every click; the
  approval itself commits and the DM goes out. Same chain shape as F7.
- `nicegui: The parent slot of the element has been deleted` from a `ui.timer`
  logs at ERROR every ten seconds while the instance is in use. Three auditors
  shared it, so I could not attribute it to a page.
