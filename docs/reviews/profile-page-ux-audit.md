# Profile page UX audit

**Surface:** the `Profile` tab of the tenant home (`/t/<slug>/home/profile`) —
`pages/home_tabs/player_edit_info.py`, plus the sections it composes
(`_link_section.py`, `web_push_section.py`, `api_tokens_section.py`).

**Method:** read of the presentation + service code, then the real app driven in
a headless browser (`/ui-validation`) as a non-staff player (`player_one`) on the
seeded `default` tenant — desktop 1500px, mobile 430px, light and dark, with both
expansions opened. Findings below are what the rendered page actually does, not
what the source implies.

---

## Summary

The page is structurally sound: one column, four titled cards, autosave, and a
mobile layout that doesn't overflow. The problems are not layout problems. They
are, in order of cost to the user:

1. Two of the page's hint strings **never render at all** — a Quasar
   labeling bug, not a copy problem.
2. The notification card presents Discord DMs and device push as two
   independent channels. **Device push is downstream of the Discord toggle**, so
   the card is actively misleading.
3. The same ten tournaments appear **twice on one page, in two different
   orders**, with nothing explaining why the lists differ.
4. A read-only (Challonge-managed) enrollment row is **visually
   indistinguishable** from the editable ones.
5. Both text inputs are **unlabeled to a screen reader** (`aria-label=""`).

---

## Confirmed defects

### 1. Field hints are invisible (`player_edit_info.py:247`, `:261`)

Both inputs are built as `ui.input('', placeholder=…)` with the visible caption
supplied by a separate `ui.label`. Passing an empty label still sets Quasar's
`label` prop, so the field renders with `q-field--labeled` but never floats the
label — and Quasar only paints a placeholder while the label is floated. Net
effect, verified in the DOM and in a 2× clip of the card:

- Pronouns: `placeholder="e.g. they/them"` is set on the element and **nothing
  is drawn**. The user sees a blank box with no idea what format is expected.
- Display name: the `Default: {username}` hint (`:244`) is dead for exactly the
  users it was written for — those who have not set a display name.

The rest of the codebase already does this correctly (`api_tokens_section.py:94`
passes a real label), so the profile is the outlier.

### 2. `aria-label=""` on both text inputs

Same root cause. The visible `ui.label('Display Name')` has no `for`/`aria`
association with the input, and the empty label prop overwrites the accessible
name with `""`. A screen reader announces two unlabeled text fields.

### 3. Device notifications silently depend on the Discord toggle

The Notifications card says *"Choose how Wizzrobe reaches you"* and then lists
**Discord** and **On this device** as siblings. In reality web push is a mirror
of the DM send path: `discord_service.send_dm` calls `_mirror_dm_to_web_push`
(`discord_service.py:209`), and every notification call site gates on
`user.dm_notifications` *before* reaching `send_dm` (e.g.
`_match_recipients.py:14`, `tournament_notification_repository.py:55`).

So unchecking "Receive Discord DM notifications for match updates" turns off
**both** channels. A user who wants phone notifications without Discord DMs will
do exactly the wrong thing, get a green "Saved" toast, and then hear nothing.
The "On this device" copy ("Notifications mirror the Discord DMs you already
receive") hints at the coupling but never states the dependency.

### 4. Ten tournaments, listed twice, ordered differently

Both lists come from the same `Tournament.filter(is_active=True)` set:

| Section | Source | Order |
|---|---|---|
| Per-tournament match alerts | `TournamentNotificationService.get_active_tournaments()` | `order_by('name')` |
| Tournament enrollment | `UserService.get_active_tournaments_categorized()` | **none** — DB order |

On the seeded tenant that is the same ten tournaments rendered twice on one
page, alphabetical in one place and arbitrary in the other. Expanded, the page
is ~3100px tall on desktop and the duplication is the single largest contributor.

The two lists genuinely mean different things — enrollment puts you in the
player pool; an alert level is a *follow*, and works for tournaments you don't
play in (`get_match_notification_subscribers` never checks enrollment). Nothing
on the page says so, so it reads as a duplicate.

### 5. The Challonge-managed enrollment row reads as editable

`render_challonge_tournament` (`:311`) disables the checkbox, but Quasar's
disabled state is a slight opacity change — in the render it is the same filled
brown checkbox as its editable neighbours. The two explanatory lines and the
"View bracket" link that follow are emitted as siblings at card level, not
indented under the row, so they float unattached and read as card-level prose.
The only reliable signal that the row is read-only is the tooltip.

---

## Weaker points (judgment, not defects)

- **Vertical rhythm.** `.card-full-width` already carries `margin-bottom: 1.5em`
  and the page column adds `gap-4` on top, so cards sit ~40px apart;
  `.section-title` adds another `1em` under each title. Collapsed, the page is
  1734px for four cards holding two inputs, one checkbox, and a list. Above a
  1100px fold the user sees two-and-a-half cards. Worth noting that the fix
  below is a wash on total height (1734px → 1759px): dropping the doubled gap
  buys back roughly what the newly-visible field hints spend. The gain is that
  the space now carries information.
- **The identity header repeats the app bar.** Name + avatar already sit in the
  top-right chrome; the header beneath adds only `@username`. It carries no
  roles, no community, no "member since" — nothing that makes it a profile.
  (Addressed below by adding the per-tenant role badges; the rest is left.)
- **Personal settings are spread across three tabs.** Profile, My Availability,
  and Player ("Your Schedule") are all first-person surfaces at the same level
  as the community-wide Schedule/On Air tabs.
- **Sentence case is inconsistent** — "Display Name" against "Personal
  information", "Tournament enrollment".
- **Copy over-promises.** "…about matches, crew, and shifts" sits above controls
  that only tune *match* alerts.
- **No account-level actions.** No timezone note (everything renders US/Eastern
  and the page never says so), no deactivate, no data export.
- **The save-status indicator is pinned to the top** of a 1700–3100px page. The
  `ui.notify` toast covers this, so it is a nit, not a defect.
- Dark mode renders correctly; card borders are near-invisible against the page
  but the layout holds.

---

## What this change set fixes

| # | Fix | Where |
|---|---|---|
| 1, 2 | Each input carries its own Quasar label (`stack-label`) instead of a preceding `ui.label`, so the placeholder renders and the accessible name is real. Guidance moved into a persistent `hint`. | `player_edit_info.py` |
| 3 | The DM checkbox is reframed as the delivery master switch ("Send me notifications about match updates") under a **Delivery** heading, with a sub-caption naming both channels and a warning line that appears while it is off. Web-push copy states the dependency. | `player_edit_info.py`, `web_push_section.py` |
| 4 | `get_active_tournaments_categorized` now orders by name, matching the alerts list. The alerts expansion is retitled "Match alerts by tournament", says a follow does not require enrollment, and marks the enrolled ones with a badge; the enrollment blurb names the distinction from the other direction. | `user_service.py`, `player_edit_info.py` |
| 5 | The Challonge-managed row gains a lock glyph and an "Automatic" badge, and its explanatory lines are indented under the row instead of floating at card level. | `player_edit_info.py` |
| — | Doubled card gap removed (`gap-4` → `gap-2`); "Display Name" → "Display name". Role badges added to the identity header. | `player_edit_info.py` |

Verified in the browser at 1500px and 430px, light and dark, with both
expansions opened, plus a long-tournament-name overflow check on the new
Challonge row. `scripts/ui_flag_sweep.sh` clean; 3669 tests pass (the 7
`test_discord_service.py` failures in this container pre-date the change —
they assert the installed Discord library's identity).

The remaining items in the section above are product decisions and are left
alone. The largest of them: **enrollment and match alerts remain two separate
lists of the same tournaments.** They mean different things and merging them
would remove the ability to follow a tournament you are not playing in, so this
change set makes the distinction legible rather than collapsing it. Merging is
worth revisiting as a deliberate design call.
