# Public pages and wayfinding UX: evaluation

**Scope:** every surface a signed-out visitor can reach, and how anyone finds
their way between surfaces. That is the eight `@public_page` routes (the two
interactive bracket views in [`pages/brackets.py`](../../pages/brackets.py), `/help`
and `/help/{slug}`, `/event-info` and `/event-info/{slug}`, `/room/{token}/seeds`,
`/cat-facts`), the two cached spectator routes in
[`pages/static_brackets.py`](../../pages/static_brackets.py) (`/live/...`), the
tenant front door (`/`, `/t/<slug>`, an unknown slug, the membership join page,
`/login`), the 403/404/500 pages, the drawer and bottom nav per role, and help
coverage: which pages carry a help icon, whether each one opens something, and
whether the articles link to pages their reader can open.

**Method:** against the running dev app (`./start.sh validate`, MOCK_DISCORD,
seeded `default`/`second`/`fledgling`), with Playwright scripts in the session
scratchpad. A 53-route list was driven signed out and as `player_one` at 1440×900,
a 24-route subset signed out at 390×844, the draft/cancelled cases again as
`staff_user`, and eight hub pages as seven `USER_SPECS` users (`player_three`,
`staff_user`, `proctor_only`, `volunteer_only`, `outsider`, `super_admin` at
desktop; `player_one` at phone). Every help article's in-body links were crawled
on all three tenants (35 links), every help icon on the home and volunteer hubs
was opened and its "Read more" target loaded (20 targets), and the server log
was read across each run. Screenshots are under
`/tmp/claude-0/-home-user-sglman/21037563-847e-55a4-bd9a-303508d481a4/scratchpad/public/`
(cited below by file name). Two other auditors shared the instance, so log
lines were attributed by the `File` frames in each traceback; none of the
tracebacks in my windows came from a surface in this scope (they were
`admin_users.py:103`, `player.py:312`, `triforce_texts.py:45` and
`bracket_schedule_dialog.py:146`). Writes: none, apart from the two
`RoomToken.last_used_at` touches that opening the kiosk page performs and the
mock-login sessions. Claims not driven are tagged `code-read`.

**Headline:** the spectator content itself is in good shape. Draft and cancelled
stages stay hidden on every public surface, the static view sends no cookie,
a room token from one community is not found in another, the anonymous bracket
dialog is read-only, every help icon opens and every "Read more" lands on a real
anchor, and nothing scrolls sideways at 390 px. The damage is at the edges:
how a signed-out person gets *in*, and what they see when a link is wrong. A
Discord DM's button opened in a browser with no session loses its target twice
over, the join page's own Sign in button loops back to the join page from any
`/home/<section>` URL, and a mistyped community slug makes Chrome download a
16-byte file.

---

## Route × viewer matrix

What each route shows. "Member" is `player_one` (member of `default` and
`second`, holds VOLUNTEER). Status is the HTTP status the browser received.

| Route | Signed out | Member | Note |
|---|---|---|---|
| `/` | 200 community picker, 3 cards | 200 picker | no Help anywhere on the bare host |
| `/t/default/` | 200 join page with bracket preview | 200 home | |
| `/t/second/` | 200 join page with today's schedule (opt-in preview) | 200 home | |
| `/t/fledgling/` | 200 join page | 200 join page (not a member) | |
| `/t/nope/`, `/t/nope/help` | **404 with no Content-Type: Chrome downloads it** | same | finding 2 |
| `/help`, `/cat-facts` (bare host) | 200 rendering "404 Not Found" | same | finding 12 |
| `/t/default/help`, articles | 200 | 200 | 10 articles |
| `/t/second/help/volunteering` | 200 "That help article does not exist." | same | linked from 2 articles, finding 4 |
| `/t/default/help/nope` | 200 "does not exist" | same | soft 404 |
| `/t/default/event-info` | 200, 1 article | 200, 2 articles | role filter works |
| `/t/default/event-info/proctoring` | 200 "That page does not exist." | 200 article | finding 13 |
| `/t/second/event-info` | 200 rendering "404 Not Found, not enabled" | same, shown signed out | finding 6 |
| `/t/default/tournament/6/brackets` | 200 | 200 | title `Wizzrobe — Brackets` |
| `/t/default/tournament/7/brackets` (draft only) | 200 "No brackets have been published", tournament name shown | same | staff: 1 stage + share link that 404s |
| `/t/default/tournament/999/brackets`, `/13/` (other tenant) | 200 bare "Tournament not found." | same | scoped correctly |
| `/t/default/brackets/1,4,5,8` | 200 | 200 | |
| `/t/default/brackets/2` (draft), `/3` (cancelled) | 200 "Bracket not found." | same | staff sees both |
| `/t/default/brackets/99999999999` | **500** error page with reference | same | finding 3 |
| `/t/default/brackets/abc` | **422 raw JSON** | same | finding 3 |
| `/t/second/brackets/1` | 200 rendering "404, not enabled" | same | flag off |
| `/t/default/live/tournament/6/brackets`, `/live/brackets/1` | 200, good titles, `Cache-Control: public` | same | HEAD returns 405 |
| `/t/default/live/brackets/2` (draft) | 404 plain text "Bracket not found" | same | |
| `/t/default/live/brackets/99999999999` | **500 plain "Internal Server Error"** | same | finding 3 |
| `/t/default/room/<live token>/seeds` | 200 chromeless board, 1 seeded match | same | |
| `/t/default/room/<revoked or garbage>/seeds`, other tenant's token | 200 rendering "404, only exists inside a specific community" | same, shown signed out | finding 7 |
| `/t/default/zzz`, `/zzz` | 404 "Page not found" | 404 | the only real 404s |
| `/t/default/admin` | 307 to login | 403 page | |
| `/t/default/home/schedule` | 200 join page | 200 home | finding 1 |
| `/platform` | 200 rendering "403" | 200 rendering "403" | |

---

## Findings, ranked

### 1. High: a signed-out person following a DM link never reaches it

The DMs' link buttons point at `/home/<section>?<param>` (the matchup picker,
the reschedule dialog, the harder-settings dialog, one match's row) and at
`/admin/<section>?match_id=` style routes, built by
[`notification_links.py`](../../application/services/notification_links.py).
Opened in a browser with no session, which is the normal case for a phone
tapping a Discord button, three things go wrong, all driven at 390×844:

1. `/t/default/home/my-schedule?match=1` renders the join page, because home is a
   bare `ui.page` that applies the membership gate itself
   ([`pages/home.py:134`](../../pages/home.py#L134)). The copy reads "Sign in to
   ask to join this community." to someone who is already a member
   ([`theme/join_page.py:242`](../../theme/join_page.py#L242)).
2. The join page's **Sign in** button navigates to the *relative* path `'login'`
   ([`theme/join_page.py:298`](../../theme/join_page.py#L298)). From
   `/t/default/home/schedule` or `/t/default/home/my-schedule?match=1` that
   resolves to `/t/default/home/login`, which home serves as `section='login'`:
   the join page again. The button is a loop on every `/home/<section>` URL,
   desktop and phone. It only works from `/t/<slug>/` and `/t/<slug>/home`.
   Screenshots `signin_desktop__t_default_home_schedule.png`,
   `signin_phone__t_default_home_my_schedule_match_.png`.
3. Signing in through the header button instead lands on `/t/default/`, the
   Event tab. The section and the `match=1` param are gone, because only a
   *protected* route records `referrer_path`, and home is not one. On protected
   routes the path survives but the query does not:
   `/t/default/admin/schedule?match_id=1` comes back as `/t/default/admin/schedule`,
   because [`middleware/auth.py:425`](../../middleware/auth.py#L425) stores
   `f'{root_path}{path}'` without `request.url.query`.

So the DM that CLAUDE.md requires to "open the exact dialog" opens it only for a
reader who was already signed in. The real Discord `/login` reads the same
`referrer_path` ([`pages/auth.py:278`](../../pages/auth.py#L278), `code-read`),
so production loses the target the same way.

### 2. High: an unknown or inactive community slug downloads a file

`/t/nope/` (and any path under it) returns `Response('Tenant not found', 404)`
with no `Content-Type` ([`middleware/tenant.py:195`](../../middleware/tenant.py#L195)).
Chrome treats the body as a download: Playwright's `goto` fails with "Download
is starting" and the tab shows `ERR_INVALID_RESPONSE`, "This site can't be
reached" (`anon_d__t_nope_.png`). A typo in a shared link, a renamed slug, or a
community a super-admin deactivated all end there, with no themed page, no link
to the picker, and the word "Tenant" if the body ever does render. Every other
not-found in the app has a Back to home button.

### 3. Medium: malformed or out-of-range ids crash public routes

A spectator link pasted with a trailing character or a stray digit is the
input these routes see most. Driven with curl:

| Request | Result |
|---|---|
| `/t/default/brackets/99999999999999999999` | 500 error page with an error reference |
| `/t/default/tournament/99999999999/brackets` | 500 |
| `/t/default/live/brackets/99999999999` | 500, body `Internal Server Error`, ExceptionGroup traceback in the log |
| `/t/default/live/tournament/99999999999/brackets` | 500 |
| `/t/default/brackets/abc` (and the two other int routes) | 422 `{"detail":[{"type":"int_parsing",...}]}` as raw JSON |

The 500 is `models.column_guards.FieldValueError: Id must be between -2147483648
and 2147483647` from `bracket_repository.py:34` via `BracketService.get_bracket`
and from the `Tournament.get_or_none` calls at
[`pages/brackets.py:328`](../../pages/brackets.py#L328) and
[`pages/static_brackets.py:172`](../../pages/static_brackets.py#L172) / `:219`.
Each one logs `UNHANDLED ERROR error_id=...`, so in production every bad link a
bot or a spectator follows files a Sentry event.

### 4. Medium: help articles link to articles that do not exist on two of three communities

`proctor` and `volunteering` declare `feature: VOLUNTEERS`, so they disappear
where that flag is off. The links to them do not. The in-body crawl found 35
internal links across the three tenants and 8 of them dead, all rendering "That
help article does not exist.":

- `getting-started` → `/help/volunteering` and `/help/proctor`
  ([`getting-started.md:46-47`](../../application/help/content/getting-started.md))
- `glossary` → `/help/proctor` and `/help/volunteering`
  ([`glossary.md:48`](../../application/help/content/glossary.md), `:74`)

on both `second` and `fledgling` (`anon_d__t_second_help_volunteering.png`).
`getting-started` is the first card on `/help`, and its "depending on why you
are here" table is where the two dead rows sit. `render_blocks` renders a link
span without asking whether its target is readable
([`theme/help/render.py:21-25`](../../theme/help/render.py#L21)); the snippet
path already solves the same problem by hiding the icon.

### 5. Medium: signing in from a public page drops you on home

On `/t/default/brackets/1`, signed out, the header's **Login with Discord** goes
to `/t/default/login`; after picking `player_one` the browser lands on
`/t/default/`, not the bracket (`desktop_login_roundtrip.png`). The header
button is a bare `navigate.to('/login')`
([`theme/base.py:335`](../../theme/base.py#L335)) and public pages never set
`referrer_path`. The help article says the opposite: "approve the request, and
you land back where you started"
([`getting-started.md:12`](../../application/help/content/getting-started.md)).
A spectator who signs in to sign up as crew from a bracket, or to read the
role-gated half of the event handbook, has to find their way back.

### 6. Medium: not-found states disagree on status, chrome and who you are

Eight distinct "this isn't here" states were reached. Only the unknown-route
page returns HTTP 404; every other one returns 200:

| State | Status | Chrome |
|---|---|---|
| Unknown route `/t/default/zzz` | 404 | error card, viewer shown correctly |
| Feature off (`/t/second/event-info`, `/t/second/brackets/1`) | 200 | error card, **signed-in viewer shown signed out** |
| Bad room token | 200 | error card, viewer shown signed out |
| Bare-host `/help`, `/cat-facts` | 200 | error card |
| Missing help / event-info article | 200 | full page, one line and a back link |
| Missing tournament / bracket (interactive) | 200 | full page, a red "Tournament not found." with no way back |
| Missing bracket (static) | 404 | plain text |
| Unknown slug | 404 | none, see finding 2 |

The signed-out header is the visible part. `player_one` opening
`/t/second/event-info` or a revoked room link sees **Login with Discord** in the
header, because those paths call `render_error_page(..., user=None)`
([`middleware/auth.py:272-277`](../../middleware/auth.py#L272),
[`pages/room_seeds.py:53-58`](../../pages/room_seeds.py#L53)), while the 403
for the same user passes `user=user` and shows their name. The 200s matter for
the static view's CDN story and for link checkers, which treat these pages as
live.

### 7. Medium: the join page and every error page drop the community's chrome

Both render `BaseLayout(user=user).render_chrome()` without `render()`
([`theme/join_page.py:286`](../../theme/join_page.py#L286),
[`theme/error_page.py:57`](../../theme/error_page.py#L57)), and `render()` is
where the wordmark, the tenant palette, the Event Information item and Feedback
are resolved ([`theme/base.py:133-148`](../../theme/base.py#L133)). Measured:

- The header reads "Wizzrobe" on `/t/default/` signed out, on `/t/default/zzz`,
  and on the 403 at `/t/default/admin`, where every framed page reads "Default"
  (`anon_p__t_default_.png`, `anon_p__t_default_zzz.png`).
- The drawer on the join page and on error pages holds Home and Help only. On
  `/t/default/help` the same signed-out visitor gets Home, Event Information,
  Help. The join page is the front door a spectator lands on, and the event
  handbook is the public section written for exactly that visitor; from the
  door there is no way to it.
- The tenant's brand colours are not loaded on either (`code-read`; `default`
  uses the shipped palette, so the screenshots cannot show it).

### 8. Medium: a revoked kiosk token tells staff the page is in the wrong place

An unknown, revoked, malformed or other-community token renders "This page only
exists inside a specific community. Try getting there from your community's
link." ([`pages/room_seeds.py:53-58`](../../pages/room_seeds.py#L53)), on a URL
that is already inside `/t/default/`. The person who sees this is a staff
member standing at a room PC whose token was just revoked
(`anon_d__t_default_room_garbage_seeds.png`). The module docstring says the page
"renders the same page a route that never existed would"; it does not. A real
missing route is a 404 reading "Page not found ... the link's out of date",
and this one is a 200 with different copy. Reusing the unknown-route page would
make the claim true and the copy accurate.

### 9. Low: tournament names can be read by id, signed out

`/tournament/{id}/brackets` and its static twin print the tournament's name for
any id in the community, whether or not it has a published stage. Walking ids
1-19 signed out returned "Bracket Demo — Draft" (only a draft stage), "Wizzrobe
Cup — Next Season" (no stages) and "PJ Audit Open", a tournament another session
had created minutes earlier. Stage contents stay hidden; the name and existence
of an unannounced event do not. Gating the title on "has a visible stage" at
[`pages/brackets.py:328-345`](../../pages/brackets.py#L328) and
[`pages/static_brackets.py:172-190`](../../pages/static_brackets.py#L172) would
close it.

### 10. Low: staff are offered a share link for a draft that 404s

As `staff_user`, `/t/default/brackets/2` (draft) and `/t/default/tournament/7/brackets`
show **Shareable spectator view**. The first leads to `/live/brackets/2`, a plain
"Bracket not found" 404; the second leads to a page saying nothing has been
published. Correct for spectators, confusing for the staff member who copies it
into Discord before starting the stage. The link is unconditional at
[`pages/brackets.py:342`](../../pages/brackets.py#L342) and `:497`.

### 11. Low: shared bracket links carry generic titles

Every interactive bracket page is titled `Wizzrobe — Brackets` or
`Wizzrobe — Bracket` ([`pages/brackets.py:319`](../../pages/brackets.py#L319),
`:373`), so ten open tabs and every browser-history entry read the same. The
static pages get it right (`Championship — Bracket Demo — Single Elimination`).
Neither has `og:title`/`og:description`, so a Discord unfurl shows only the
`<title>`, and `HEAD /live/brackets/1` answers 405, which some unfurlers try
first. Help and event-info titles omit the community name.

### 12. Low: the bare host has a circular Help link and no help

`/help` and `/cat-facts` without `/t/<slug>` render "This page only exists inside a
specific community", and that page's drawer offers Help, which points at the
same URL (`anon_d__help.png`). The community picker at `/` has no drawer and no
Help, so a first-time visitor on the bare host has no help at all.

### 13. Low: a role-gated handbook article tells a signed-out reader it does not exist

`/t/default/event-info/proctoring` signed out reads "That page does not exist."
(`anon_d__t_default_event_info_proctoring.png`). Not revealing which articles
exist is deliberate ([`event_info_service.py`](../../application/services/event_info_service.py)
`get_article`), but a signed-out visitor holds no role by definition, so adding
"Signed in? Some pages are only for crew and staff." to the *signed-out*
variant of [`pages/event_info.py:99-101`](../../pages/event_info.py#L99) leaks
nothing and gives the proctor on a borrowed laptop a next step.

### 14. Low: on a phone the article's contents come after the article

At 390 px the help and event-info navigation, including "← All help" and the
"On this page" list, is moved below the body by `order: 2`
([`static/css/styles.css:2349`](../../static/css/styles.css#L2349)). On
`getting-started` it starts at 1,867 px of a 2,468 px page; on `glossary` at
2,740 of 3,311 (`full_phone__t_default_help_getting_started.png`). The comment
at [`pages/help.py:103-105`](../../pages/help.py#L103) says the order puts the
reader's contents "right above the body it indexes", which is what the code was
meant to do and not what it does.

### 15. Low: the phone bottom nav overflows on every home page

The four home tabs measure 373 px in a 358 px bar (the footer's `q-px-md`,
[`theme/base.py:527`](../../theme/base.py#L527)), so Quasar draws a scroll arrow
over **Profile** on every member's home (`nav_phone_player_one__.png`). Every
role has the same four tabs, so every member sees it.

### 16. Low: non-members get a Feedback item on public pages

`outsider` (a member of no community) sees Feedback in the drawer on
`/t/default/help` and `/t/default/event-info`, because the drawer gates it on
`self.user` and the flag, not membership ([`theme/base.py:146`](../../theme/base.py#L146),
`:414`). `FeedbackService.submit` checks neither, so a non-member can write into
the community's feedback queue (`code-read`: the dialog was not submitted).

### 17. Low: a bye reads BYE on the card and TBD in the dialog

Opening Match 1 of `/t/default/brackets/1` signed out shows "Player One" against
"TBD" in a Complete match whose card says BYE (`desktop_bracket1_dialog_anon.png`).
The card uses the slot-label helper in
[`theme/brackets/cards.py:89-98`](../../theme/brackets/cards.py#L89); the dialog
falls back to a literal at [`theme/brackets/dialog.py:267`](../../theme/brackets/dialog.py#L267).

---

## Help coverage

Help icons per page, driven as `staff_user` (desktop) and `player_one` (phone):

| Page | Icons | Targets |
|---|---:|---|
| Home → Event (schedule board) | 2 | `schedule-board#the-columns`, `#match-states` |
| Home → My Schedule | 10 | `player` ×4, `event-info/attending` ×3, `crew` ×3 |
| Home → Tournaments | 1 | `tournament-signup#signing-up` |
| Home → Profile | 1 | `notifications#where-your-settings-live` |
| Volunteer → My Availability / My Shifts | 1 / 1 | `volunteering` |
| Volunteer → Proctor Station | 4 | `proctor` ×2, `event-info/proctoring` ×2 |
| Admin (all tabs), bracket views, join page, room board | 0 | |

All 20 distinct targets load and their anchors exist. Every tap target measures
44 px at 390 wide. Eight snippets are defined and opened by no icon
(`dm-buttons`, `watch-match`, `crew-signup`, `crew-confirm`,
`getting-started-optin`, `player-trouble`, `player-turnover`, `proctor-integrity`,
plus `proctor-check-in`/`proctor-turnover` in the `sgl26` handbook), which is
harmless (`code-read`). The admin area has no help icon and no article; the
help index describes itself as being for "players, crew and volunteers", so
that is a choice rather than a gap, but it means the seventeen-tab admin drawer
has no in-app explanation anywhere.

## Navigation per role

Drawer contents on `/t/default/` (desktop), from the nav crawl:

| User | Drawer (top level) |
|---|---|
| signed out | Home, Event Information, Help (join page: Home, Help) |
| `outsider` | join page: Home, Help; on `/help`: Home, Event Information, Help, Feedback |
| `player_three`, `player_one` | Home, Volunteer, Admin*, the four home tabs, Event Information, Help, Feedback |
| `proctor_only` | Home, Volunteer, the four home tabs, Event Information, Help, Feedback |
| `volunteer_only` | same as `proctor_only` |
| `staff_user`, `super_admin` | Home, Volunteer, Admin, the four home tabs, Event Information, Help, Feedback |

\* `player_three` reaches Admin with two tabs (Schedule, Reports).

Every drawer item a role was offered opened for that role; no nav item led to a
403. On a 403 page the drawer collapses to Home and Help (finding 7). A
spectator has no nav path to brackets: the only links to
`/tournament/{id}/brackets` for a signed-out visitor are the join page's
preview list, which appears only where `BRACKETS` is on.

## What could not be driven

- The real Discord OAuth `/login` (MOCK_DISCORD replaces it with a picker), so
  finding 1's production path is `code-read` from the shared `referrer_path`.
- An inactive community: none is seeded and deactivating one would have changed
  a tenant other auditors were using. It shares the unknown-slug branch at
  `middleware/tenant.py:194`, so finding 2 applies (`code-read`).
- The room board's live update when a seed is rolled: it needs a write
  (rolling a seed) on a shared instance. `MatchTableView._on_remote_change`
  handles the filtered-board case explicitly (`code-read`).
- A tenant with a custom brand palette on the join and error pages (finding 7,
  `code-read`).
