# Bracket UI Redesign Plan (design record)

> Status: **proposed.** The native bracket system
> ([features/brackets.md](features/brackets.md)) shipped with a deliberately
> minimal visualization — [brackets-plan.md](brackets-plan.md) budgeted the
> polish as deferred work. This is that work: a redesign of the public bracket,
> Swiss, and group/round-robin views to match how tournament brackets are
> conventionally presented (Challonge / start.gg / Liquipedia visual grammar).
> The engine, data model, and service layer are correct and stay untouched
> except for the small additive fields listed in [Model additions](#model-additions).

## Context: what ships today vs. the target

The current public view (`pages/brackets.py`) renders elimination brackets as
independent per-round columns of plain `ui.card`s — no connector lines, no
seeds, no scores, no avatars, no round metadata — with winners/losers/finals as
three disconnected stacked sections and `overflow-x: auto` as the only mobile
accommodation. Swiss and round robin render a standings `ui.table` plus a plain
"X def. Y" text list. It is functional but does not read as a bracket.

The target is the canonical presentation every major platform converged on
(reference screenshot: a Challonge-style double-elimination view):

- **Round headers** carrying the round name, scheduled date/time, and a
  best-of badge ("Best of 3").
- **Match cards** with two stacked participant rows: avatar, name, and a
  right-aligned **score cell** — the winner's score cell accented (orange/green
  fill), the loser dimmed. A small **match number** sits on the card's edge so
  staff can call "match 12 on stream".
- **Elbow connector lines** joining each pair of feeder matches to the match
  they feed, with the child match vertically centered between its feeders.
- **Winners bracket on top, losers bracket as a separate section below**, grand
  final (and conditional reset) at top-right.
- Byes/TBD slots dimmed and italic; hovering a player highlights their run
  through the bracket.

Everything needed to draw this already exists in the persisted graph
(`BracketMatch.round`/`position`/`winner_to`/`loser_to` + slots, negative
rounds = losers bracket) — the redesign is almost entirely presentation-layer,
plus two small additive model/config changes (scores, per-round best-of/time).

## Research record (2026-07)

Researched so it is not re-researched.

### The canonical visual grammar

Challonge, start.gg, Battlefy, Toornament, and Liquipedia all share the same
conventions:

- **Column-per-round, left to right**, each column headed by the round name +
  secondary metadata (time, best-of). Headers stay visible while scrolling
  (`position: sticky`).
- **Match card anatomy**: seed number in a small muted fixed-width badge, then
  avatar (16–24 px), then name (ellipsis + tooltip for long names), then a
  fixed-width score cell. Winner's row: bold name + accent-filled score cell;
  loser's row dimmed (~60 % opacity) — completed matches recede so live ones
  pop. Cards are ~160–200 px wide, participant rows 24–32 px tall, ~3 em
  gutters for connectors.
- **Only winner-advancement links are drawn** — never loser-drop links (the
  losers bracket would become spaghetti). This is explicit in Toornament's
  developer guide and universal in practice.
- **Double elimination**: winners bracket section on top, losers below, each
  with its own round headers; the two sections don't column-align (losers has
  ~2×−1 rounds) and simply scroll together. Grand final is the last column
  top-right, with the reset match beside/after it, shown as TBD until a bracket
  reset actually happens.
- **Byes** render as a dimmed italic "BYE" row; unresolved slots show "TBD" or,
  better, the source hint ("Winner of 7", "Loser of Winners Finals") — cheap to
  derive from the persisted `winner_to`/`loser_to` pointers by inversion.
- **Match states are color-coded**: pending (dim), ready (accented border),
  in-progress ("LIVE" badge), complete (winner accent).

### Layout techniques (how the tree gets drawn)

Three viable techniques, in increasing order of control:

1. **Flexbox spacers** — each round is a flex column with `flex-grow: 1`
   spacer elements between matches (half-size at the ends); flexbox centers
   every round against the previous one with zero math. Connectors come from
   borders on the spacer elements. Simplest; degrades on lopsided sections.
2. **CSS grid + pseudo-element connectors (Liquipedia's technique** — the most
   battle-tested wiki-scale implementation, documented at
   [river.me/blog/tournament-brackets](https://river.me/blog/tournament-brackets/)):
   `grid-auto-flow: column` with alternating content columns (16 em) and line
   columns (3 em); every match spans 2 grid rows and vertical placement is
   `grid-row: span N` where N encodes the 2^r geometry; connectors are built
   from the line-cells' `::before`/`::after` borders (5 independently
   borderable segments per cell → "Z" and "L" elbows, small border-radius),
   themed via CSS custom properties (`--bracket-line-color` etc.).
3. **Explicit coordinates + SVG polylines (Toornament's algorithm** —
   [developer guide](https://developer.toornament.com/v2/guides/display-bracket)):
   treat matches as a rooted binary tree on winner-links only; in-order
   traversal assigns `x = depth`, `y = visit order`; a post-order pass centers
   each parent between its children (`y = (y₁+y₂)/2`); map to pixels and draw
   orthogonal SVG elbows. Most robust for byes, feed-ins, and lopsided losers
   brackets, at the cost of owning coordinate math.

Large brackets: fixed-height viewport, `overflow: auto`, optional zoom
(`transform: scale()` + fit button). Production sites mostly avoid minimaps by
splitting big fields into pools; horizontal scroll + zoom is the pragmatic
answer at our scale.

### Libraries evaluated

| Library | Tech / license | Verdict |
|---|---|---|
| [brackets-viewer.js](https://github.com/Drarig29/brackets-viewer.js/) | Vanilla JS + CSS, **MIT** | The strongest embed candidate (already named the fallback in [brackets-plan.md](brackets-plan.md)). Renders SE/DE/RR from JSON (`brackets-model` shape), participant images, `onMatchClick`, CSS-variable dark theme. Cost: match cards are its DOM, not NiceGUI elements — interactivity is limited to a click callback bridged back to Python; no Quasar components inside cards. |
| [@g-loot/react-tournament-brackets](https://github.com/g-loot/react-tournament-brackets) | React/SVG, LGPL | Study only (data shape, `SVGViewer` pan/zoom); React island not worth it. |
| [vue-tournament](https://github.com/RuiChen0101/vue-tournament) | Vue 3, MIT | Tempting since NiceGUI is Vue-based, but mounting third-party SFCs means building a custom NiceGUI component — more work than the CSS approach for less control. |
| [jquery-bracket](https://github.com/teijo/jquery-bracket), [Gracket](https://github.com/Zettersten/jquery.gracket.js/) | jQuery, MIT | Legacy; mined for ideas only (jquery-bracket's inline score entry; Gracket's hover-run highlight = stamp `data-entrant-id` on every row, toggle a class on all matches via one `querySelectorAll`). |

### Swiss & group conventions

- **Swiss** = two coordinated views under a **round selector** (tabs, current
  round default): per-round **pairings list** (board #, "A (2-1) vs B (2-0)",
  result, byes listed last) and a **standings table** with explicit tiebreaker
  columns in application order — narrow, muted, abbreviated headers with
  tooltips (chess: Buchholz/SB per lichess; TCG: Points → OMW% → GW% per
  melee.gg/start.gg; Challonge: Median-Buchholz). When Swiss feeds a top cut,
  a **cut line** (heavier border) after position N.
- **Groups/round robin** = one card per group ("Group A" …) in a responsive
  grid, each with a compact standings table (Pos, entrant, W-L(-T), Pts) whose
  rows are **tinted by fate**: green edge/tint for advancing positions, red
  for eliminated, with a cut line and a small legend. Match list per group
  below, grouped by round. Optional secondary **crosstable** view (entrants on
  both axes) — excellent ≤ 8 entrants, degrades beyond ~10, keep it a tab.

### Interaction & platform patterns

- **Hover-run highlight** of a participant across all rounds (see Gracket note
  above — a few lines of JS even for server-rendered DOM).
- **Click match → dialog** with details and (authorized) score reporting.
- **Live updates**: subscribe the page to bracket events and refresh — our
  in-process event bus + `@ui.refreshable` (`theme/realtime.py` pattern)
  already fit.
- **Fullscreen / venue mode**: a toggle that expands the bracket container
  (Fullscreen API) at increased scale, for projectors and stream layouts.
- **Mobile**: consensus is *degrade to a vertical per-round list* (accordion or
  round tabs with stacked match cards) with the 2-D bracket still reachable via
  horizontal scroll; accessibility work reaches the same conclusion (expose a
  screen-reader-friendly list, don't aria-label the tree).
- **Dark theme is the esports default**; drive all colors through CSS custom
  properties so Quasar dark/light switching just works.

## Decisions (proposed)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Build the bracket renderer in-house as server-generated NiceGUI/HTML using the CSS-grid technique (Liquipedia's), with connectors from pseudo-element borders — no JS bracket library.** | Match cards must be *interactive NiceGUI elements* (click → existing dialogs, admin report actions, live refresh); brackets-viewer.js only offers a click callback and forecloses Quasar components inside cards. The grid technique needs no coordinate math, no SVG, themes via CSS variables, and is proven at wiki scale. brackets-viewer.js (MIT) **remains the recorded fallback** if the in-house renderer stalls — our API already exposes a graph trivially mappable to `brackets-model`. |
| 2 | **One shared bracket-rendering module** (`theme/brackets/` — layout walker + match-card component + CSS), consumed by both the public page and the admin tab. | The admin Results dialog currently lists matches as flat text (`R-2 #1: A vs B`); staff should report results by clicking the same visual bracket users see. |
| 3 | **Draw winner-links only**; losers-bracket drops are conveyed by "Loser of …" placeholder hints, not lines. | Universal convention; loser lines are unreadable. |
| 4 | **Add game scores** (`entry1_score`/`entry2_score`, nullable ints) to `BracketMatch`, reported optionally alongside the winner. | The score cell is the visual anchor of every match card on every platform; today we store only a winner. Nullable + optional keeps every existing flow (win-only reporting, `advance_if_linked`) valid — a missing score renders as `1–0`-style W/L glyphs. |
| 5 | **Per-round metadata (best-of, scheduled time) lives in `Bracket.config`**, keyed by round — not on `BracketMatch`. | It's display/format metadata, uniform per round (like the reference screenshot); the config blob is already schema-validated at the service boundary; no migration beyond the score fields. Actual per-match scheduling stays on the linked `Match` (the seam), shown on the card when present. |
| 6 | **Mobile**: below `lt.md`, elimination brackets render a per-round accordion list of stacked match cards (the `wiz-grid-card` idiom); the 2-D bracket remains available via horizontal scroll. Swiss/RR tables keep `enable_mobile_grid`. | House pattern (every table gets a mobile card view) extended to the bracket; matches industry mobile consensus. |
| 7 | **Avatars**: entrant rows show the linked user's Discord avatar (fallback: initial-letter disc for placeholders), 20 px, hidden at compact density. | Cheap (avatar URLs already used on home/profile) and a large perceived-quality win. |
| 8 | Seeds, match numbers, state color-coding, hover-run highlight, sticky round headers, fullscreen toggle — **all in scope**; pan/zoom minimap **out of scope** (horizontal scroll + zoom buttons suffice at our field sizes). | Convention-complete without speculative complexity. |

## Model additions

Deliberately minimal — one migration:

- `BracketMatch.entry1_score` / `entry2_score` (`IntField(null=True)`) —
  written by `report_result` when provided (service validates score-vs-winner
  consistency: reported winner must have the higher score when both present);
  surfaced through `api/schemas/brackets.py` and the REST report endpoint as
  optional fields. Existing rows/flows unaffected.
- `Bracket.config` schema gains an optional `rounds` map:
  `{"<round>": {"best_of": 3, "scheduled_at": "<UTC iso>"}}` (validated in
  `bracket_config.py`; negative keys address losers rounds). Display-only in
  v1: shown in round headers (times through `format_eastern_display`), not
  enforced against reported scores.

No changes to engines, progression, standings, or the scheduling seam.

## UI specification

### Shared bracket renderer (`theme/brackets/`)

- `layout.py` — pure function: `BracketMatch` rows → per-section
  (winners / losers / finals) grids of positioned cells (content cells,
  connector cells, spacer spans), computed from `round`/`position` and the
  winner-pointer tree. Handles byes (dimmed rows; a round-1 bye may collapse to
  a feed-in), placeholder hints by pointer inversion ("Winner of 7"),
  and the grand-final/reset pair (reset card dimmed "if necessary" until
  activated, per `_detect_finals`' structural detection).
- `cards.py` — the match-card component: match number chip, two entrant rows
  (seed badge · avatar · name · score cell), state classes
  (`pending/open/live/complete`), `data-entrant-id` stamps, click handler slot.
- `static/css/brackets.css` — the grid, connector pseudo-elements, card
  anatomy, state/winner/hover classes, sticky headers, print rules; all colors
  via `--bracket-*` custom properties for dark/light.
- A few lines of page JS for the hover-run highlight
  (`querySelectorAll('[data-entrant-id="…"]')` + class toggle).

### Elimination (public `/brackets/{id}`)

- Section order: **Winners** (or the sole bracket for SE) → **Losers** →
  implicit finals column(s) at the end of the winners grid.
- Round headers: name ("Round 1", "Winners Finals", "Losers Round 2", "Grand
  Finals") + optional time + best-of badge from config; sticky.
- Card click → detail dialog: entrants (with records), state, linked `Match`
  info (scheduled time, links) when present; staff additionally get the
  report/override controls (reusing the admin dialog logic).
- Toolbar: fullscreen toggle, zoom −/100 %/+, stage selector when multi-stage.

### Swiss

- Round tabs (`ui.tabs`, newest open round default) → per-round **pairings
  table**: board #, entrant A (record chip) vs entrant B (record chip),
  score/result, byes last; complete rows dimmed, open rows accented.
- **Standings** panel: rank, entrant (seed + avatar + name), W-L(-D), Points,
  then the configured tiebreaker columns (`buchholz`, `omw`, `head_to_head`)
  as narrow muted columns with tooltip headers — the tiebreaker chain is
  already computed by `standings.py`; the UI simply stops hiding it. Cut line
  after position N when the next stage's advancement rule is known.
- Dropped entrants struck through with a "dropped" chip.

### Round robin / groups

- Responsive grid of **group cards**; each: standings table (Pos, entrant,
  W-L(-T), Pts) with advancement tint + cut line derived from the next stage's
  advancement config (green = advancing, red = eliminated once locked), and
  the group's matches grouped by round below.
- Optional **crosstable tab** per group (shown for ≤ 10 entrants).

### Admin tab

- The Results dialog embeds the shared renderer (compact density) — staff
  click a match card to report/override, replacing the flat text list. Manage/
  advance flows unchanged.

### Live refresh

- The public page subscribes (`theme/realtime.py` pattern) to
  `BRACKET_MATCH_COMPLETED` / `BRACKET_ADVANCED` / `BRACKET_COMPLETED` /
  `BRACKET_STAGE_ADVANCED` for its bracket and calls the existing
  `@ui.refreshable` body's `.refresh()`.

## Implementation breakdown

One PR per unit; sizes S/M/L as in [brackets-plan.md](brackets-plan.md).

- **U1 — Scores + round metadata (M).** The two nullable score fields +
  migration; `report_result` accepts optional scores (consistency-validated);
  `rounds` config schema; API schemas/report endpoint updated;
  `seed_brackets.py` grown to write scores and per-round best-of/time so demos
  exercise the new chrome; service/API tests.
- **U2 — Shared renderer core (L).** `theme/brackets/` (layout walker, card
  component, CSS) + the elimination public page rebuilt on it: connectors,
  seeds, avatars, scores, states, byes/placeholder hints, sticky headers,
  finals/reset handling. Layout-walker unit tests (positions/spans for 2–64
  entrants incl. byes, DE losers rounds, GF+reset); `/ui-validation` pass
  against every seeded demo.
- **U3 — Interactions (M).** Match detail dialog (+ staff reporting), hover-run
  highlight, fullscreen + zoom toolbar, live refresh subscription.
  `/ui-validation`.
- **U4 — Swiss & groups views (M).** Round-tabbed pairings, tiebreaker columns,
  cut lines, group cards with advancement tinting, optional crosstable.
  `/ui-validation`.
- **U5 — Mobile + admin embed + docs (M).** Per-round accordion list under
  `lt.md`; admin Results dialog embedding the renderer; print stylesheet;
  updates to [features/brackets.md](features/brackets.md),
  [reference/frontend.md](reference/frontend.md),
  [reference/data-model.md](reference/data-model.md),
  [reference/rest-api.md](reference/rest-api.md),
  [current-state.md](current-state.md).

Critical path: U1 → U2 → U3; U4 depends only on U1; U5 last.

## Out of scope

- Pan/zoom minimaps and pool-splitting (field sizes don't warrant them).
- Score *enforcement* against best-of (display-only in v1).
- Embeddable iframe module à la Challonge.
- Team entrants, auto-scheduling — unchanged from
  [brackets-plan.md](brackets-plan.md)'s deferred list.

## Open questions (for sign-off)

1. **Score entry granularity** — set score only (`2–1`), or per-game results?
   Plan assumes set score only; per-game is a later model (`BracketMatchGame`)
   if ever needed.
2. **Default tiebreaker column set** for Swiss standings display — show the
   whole configured chain (plan's assumption) or cap at the first two?
3. Should the reference screenshot's **orange** winner accent become a
   `--bracket-*` theme default, or reuse the existing app accent color?
   (Plan assumes the app accent; tenants theming later.)
