# In-App Help

A public `/help` section plus tappable help icons scattered through the
player-, crew-, volunteer- and proctor-facing surfaces. Written for the people
who turn up to an on-site tournament — **not** for staff. Staff actions are
explained from the outside ("staff approve your signup", "a proctor fetches an
admin") so a reader understands why they are waiting on something, without
documenting an admin surface they cannot reach.

The proctor article is the exception to "documentation of the app": it is also a
**training aid**, so it carries room procedure the code does not encode — who
runs the countdown, what to do about a missing player, and which decisions are
not the proctor's to make. That content came from the community, not from
reading the source, and it will go stale independently of the code.

## Where the content lives

`application/help/content/*.md` — nine articles, in the repo, reviewed in PRs.

They live inside the package rather than at the repo root because
`.dockerignore` drops `docs` and root-level `*.md` from the build context. Help
is runtime content, not project documentation.

| Slug | Covers | Gate |
|---|---|---|
| `getting-started` | Signing in, preferred name, opting into a tournament, where to go next | — |
| `schedule-board` | The Schedule tab's columns, the five match states, watching, filters, mobile cards | — |
| `crew` | Commentator vs tracker, signing up, approval, confirming, My Crew's four chips, withdrawing | — |
| `player` | Your Schedule, acknowledging, requesting a match, Suggest a time, availability, check-in and stations, results | — |
| `on-air` | The stage timeline, finding a stream, spectating | — |
| `proctor` | The Proctor Station, running a match start to finish, unclear finishes, when to fetch an admin | `FeatureFlag.VOLUNTEERS` |
| `volunteering` | Volunteer availability, how shifts reach you, My Shifts, giving a shift back | `FeatureFlag.VOLUNTEERS` |
| `notifications` | What the bot DMs, the DM buttons, DMs not arriving, the Profile notification controls | — |
| `glossary` | Every term the app uses, plus the match-state table | — |

### Article format

```markdown
---
title: Signing up as crew
slug: crew
icon: record_voice_over
order: 30
feature: VOLUNTEERS        # optional — omit for an ungated article
summary: One line for the index card and the search index.
---

## A heading            <!-- becomes the anchor `a-heading` -->

Text with **bold**, *italic*, `code`, [a link](/help/player), a
{chip:pending:Awaiting approval} status chip and a {state:Confirmed} match state.

:::snippet crew-status
Content a help icon elsewhere in the app also shows.
:::
```

A `:::snippet` region is **not** a second copy of the text — the markers are
stripped and the region renders as ordinary article content. That is what stops
a popup and its article drifting apart. Snippet names are global; a duplicate is
logged and the first wins.

An unknown `feature:`, chip tone, or state name degrades rather than raising: a
typo in an article header must not take the help page down.

## The safe document model

Articles are **never** rendered through `ui.markdown`. They are parsed into a
closed vocabulary — six block kinds, seven span kinds
(`application/help/blocks.py`) — and each one is drawn with a native NiceGUI
element (`theme/help/render.py`). There is no path from article text to markup,
so an article can only produce elements the renderer itself creates.

This is not defensive theatre against the current authors. It is what makes the
surface safe by construction if the content ever becomes editable, and it is the
same hazard `check_markdown_xss` exists to stop. Two consequences worth knowing:

- **Link targets are allow-listed** (`/…`, `#…`, `https://`, `mailto:`).
  Anything else — `javascript:`, `data:`, plain `http://` — renders as the label
  in plain text, with no anchor.
- **Prose tables are hand-built**, not `ui.table`: their cells carry chips,
  icons and links, and they are five-row explanations rather than sortable data
  grids. They scroll inside their own `overflow-x` container.

Chips use `{chip:tone:Text}` with a **colon**, not a pipe, so they can live
inside the tables that explain what each status means.

`{state:…}` renders the board's own icon and colour class
(`STATE_STYLES`, mirroring `theme/tables/match_slots.py`), so the help shows the
reader the thing they will actually see rather than a stylised stand-in. A test
asserts the five names match `LEGACY_STATE_LABELS`.

## Feature gating

Help itself has **no** feature flag — it documents shipped behaviour, and there
is nothing to gate. Individual *articles* declare a flag, and `HelpService`
withholds them where the community has the feature off:

```python
from application.services import HelpService

await HelpService.list_articles()          # only what is live here
await HelpService.get_article('crew')      # None if missing *or* gated
await HelpService.get_snippet('crew-status')
await HelpService.search('crew withdraw')  # AND over terms
```

A gated article and a missing one give the **same** answer, deliberately: a
reader following a stale link should not learn which optional features their
community has turned off. `help_icon` renders **nothing** when its snippet
resolves to `None` — an icon that opens an empty popup is worse than no icon.

**One known consequence.** `proctor-result` explains the *Flag for admin review*
checkbox, and it lives in the `VOLUNTEERS`-gated proctor article. The dispute
flag itself is ungated (it self-gates — a community that never ticks the box
never sees it), and `can_run_match` admits staff and tournament admins as well as
proctors. So in a community with volunteers switched off, a staff member
recording a result gets the checkbox with no help icon beside it. That is
consistent with the scope call above — the help is written for non-staff — and it
degrades to *no icon* rather than to a broken one. Writing a staff track is what
fixes it.

## The surfaces

`/help` and `/help/{slug}` are `@public_page` (`pages/help.py`). Help has to
work for someone who cannot get in, which is exactly when they most need it.
There is no user-specific content on either page.

- **Index** — a search box (AND over whitespace-separated terms, matched against
  title + summary + flattened body) over article cards.
- **Article** — a sticky sidebar listing every article plus the current one's own
  `##` headings, and the rendered body. Both stack below 1024px.

**Entry point: the drawer.** The Help item sits above Feedback and is *not*
gated on `self.user`, so a signed-out visitor on any framed public surface can
reach it. The real `/login` is a bare redirect to Discord with no page to hang a
link on — the drawer is the way in.

### Help icons

```python
from theme.help import help_icon

await help_icon('crew-status')                        # bare — "explain this page"
await help_icon('crew-withdraw', label='Withdrawing')  # labelled — a named topic
```

A tappable button with a `q-menu`, not a hover tooltip: a tooltip is unreachable
on a touch screen, and this help is read on phones in loud rooms. The convention
is **one bare icon per surface** (the page's own explainer, first) plus labelled
icons for specific topics — two bare `help_outline`s side by side are
indistinguishable, and the reader has to open both to find which one answers
their question.

Wired at: Home → Schedule (columns + states), My Crew (statuses + approval +
withdrawing), Player (overview + check-in), My Availability, Profile →
Notifications; the Submit Match dialog and its Suggest a time button; Volunteer →
My Shifts and its release dialog; Volunteer → Proctor Station (the board, running
a match, and when things go wrong) and the result dialog's review flag; Home → On
Air; and the shared availability editor, which takes `help_snippet=` because the
two callers render identical UI over different data.

## Tests

`tests/test_help_content.py` and `tests/test_help_service.py`.

The one worth knowing about: **`TestPagesAndArticlesAgree`** greps `pages/` and
`theme/` for every `help_icon('x')` and `help_snippet='x'` and asserts the
snippet exists. A renamed article silently turns its icons into nothing —
correct at runtime, useless for catching the rename. Nothing else catches it.
Internal `/help/slug` and `#anchor` links are checked the same way.
