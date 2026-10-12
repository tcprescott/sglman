# UI style guide

The rules every page follows so Wizzrobe looks like one person designed it. This
is the prescriptive half: what to reach for and what not to do. The mechanics
(token values, how the tenant palette is applied, each helper's signature) live in
[reference/frontend.md](reference/frontend.md#design-tokens-the-studio-system).

It exists because, before October 2026, each era of pages used a different slice
of the design system: three page-top styles, ~205 underline inputs against 52
boxed ones, four badge styles, nine dialog widths, and gold doing every job from
the header bar to table headers to timestamps. The style pass (PRs #305, #312,
#314) and the accessibility audit (PR #315,
[reviews/2026-10-accessibility-audit.md](reviews/2026-10-accessibility-audit.md))
unified it. Most rules below are checked automatically; see
[Checking your change](#checking-your-change).

## The direction: "Studio"

Chosen by the project owner over keeping the gold "Phoenix" chrome.

- **A neutral warm-grey shell.** White header, grey page canvas, white cards.
  Borders separate things; shadows only lift (menus, dialogs).
- **One accent, and it means "you can act here" or "you are here".** Filled
  buttons, links, the active nav item, focus rings. Never titles, table headers,
  timestamps or decoration, or it stops meaning anything.
- **The accent is the community's colour.** Admin → Settings → General can
  re-point it, so never assume gold. Read `--accent` / `--wiz-link`, never
  `#9C6B12`.
- **One type family.** Atkinson Hyperlegible for everything, titles included;
  IBM Plex Mono only for times and IDs. Fraunces is retired.
- **Status is a tint, not a fill.** Soft-tinted chips with a thin border, never
  solid saturated pills.
- **Public pages (bracket, join, Watch) follow the same system** with a little
  more brand colour.

## Colour

| Do | Don't |
|---|---|
| Read a token: `var(--fg)`, `--fg-secondary`, `--fg-muted`, `--surface`, `--border-subtle`, `--status-*`, `--accent`, `--wiz-link` | Write a hex, `rgb()` or `hsl()` in a page, a `.style()` call or a slot template's `style=` |
| Use a class: `.st-ok` / `.st-pending` / `.st-live` / `.st-cancelled` for status text, Quasar `text-grey`/`text-negative`/… (re-pointed at tokens) | Mute text with `opacity` (the cat fact under empty lists was 2.7:1 that way) |
| Put brand-coloured *text* in `--wiz-link` (the accent mixed 15% toward black in light mode) | Put raw `--accent` on text in light mode: the default gold is 4.3:1 on white |
| Add a new colour as a token in `styles.css`, with its dark value | Add a colour that only exists in light mode |

Dark mode has two traps, both of which shipped and were fixed:

1. **A `:root` alias resolves once, at `:root`.** `--wiz-section-title: var(--fg)`
   on `:root` holds the *light* ink forever, even under `.body--dark`. Any token
   that derives from a dark-aware token must be restated in the `.body--dark,
   .q-dark` block. That left settings card titles, and later the On Air stage
   names, near-black on dark.
2. **Quasar's palette classes win over unlayered `!important`.** Quasar declares
   `text-*` / `bg-*` `!important` in its last cascade layer, and for
   `!important` the *earliest* layer wins. To re-point one, put the rule in
   `@layer theme { … }` in `styles.css`, as the grey-caption and dark-mode
   status rules do.

Every text token must clear 4.5:1 on `--surface`, `--page-bg` and `--surface-alt`
in both modes. `tests/theme/test_style_guide.py` computes this from `styles.css`.

## Type and page structure

| Need | Use |
|---|---|
| Page or tab title, with optional lede | `page_header(title, subtitle)` (`theme/page_header.py`). Renders the page's one `<h1>`; inside a Settings pane it drops to `<h2>` on its own |
| Title row you build yourself | `page_title(text)` |
| A tab that opens on controls, not a title | wrap it in `heading_fallback(title)` so screen readers still get an `<h1>` |
| A titled block on a page with several | `section_panel(title, icon=…)` (`theme/section.py`) |
| Dialog title | `dialog_header(title, dialog)`, or `form_dialog(title)` which includes it |
| Times, match IDs | `--font-mono` / `.cell-timestamp` |

Don't put a lede in a caption label after the header (it floated 40px below the
title on 20 pages), and don't size a title with `text-h1`…`text-h5`.

## Components: reach for these first

| Need | Use | Not |
|---|---|---|
| Status / count | `ui.badge(text, color='positive')`: the colour only picks the tone, CSS draws the chip. Or `.wiz-chip .wiz-chip--ok\|pending\|live\|neutral\|cancelled` in a template | `text-color=` on a solid chip, a hand-built pill |
| A notice across the page | `banner(message, title=, tone=)` (`theme/banner.py`; `info`/`ok`/`warning`/`danger`) | A hand-coloured row |
| Flash a message across a redirect | `stash_notice` / `drain_notice` (`theme/notice.py`) | |
| Empty list | `empty_state(message)`, `no_data_slot()` in a table | |
| A form in a dialog | `form_dialog(title)` + `dialog_actions()` + `submit_on_enter()` (`theme/dialog/_helpers.py`) | Hand-rolled `ui.dialog()` + `ui.card()` + title row |
| Dialog width | `dialog-card` (medium, the default), `dialog-card dialog-card--sm` (a few fields, a confirmation), `dialog-card--lg` (a table or two columns) | `w-96`, `w-full`, `.style('max-width: …')` |
| Phone-sized dialog | `mobile_sheet(dialog)` (form_dialog does it) | |
| A table | `enable_mobile_grid(table, columns, table_key=TableKeys.X, …)` | A bare `ui.table` (the `check_table_grid` and `check_table_prefs` hooks enforce this) |
| Text input / select | `.props('outlined dense')` | `filled`, `standout` |
| Two-to-four way toggle | `.wiz-segmented` | A row of separate buttons |
| Admin refresh | `refresh_button` (`theme/tables/admin_crud.py`) | |
| A new admin setting | A card in a Settings pane (`pages/admin_tabs/settings/`, `section_panel` + `SaveFooter`, whose bar appears only once something changed) | A new drawer tab, a second Save button |

## Accessibility (WCAG 2.1 AA)

- **Every control has a name.** An icon-only `ui.button` gets one from
  `.tooltip('Delete')` (`theme/a11y.py` copies it into `aria-label`). In a Vue
  slot template, a `<q-btn>` with only an icon spells out `aria-label` itself;
  a `<q-tooltip>` is not a name. `tests/test_a11y_names.py` enforces this.
- **Captions are labels.** A free-standing caption over a field becomes
  `label_field(caption, field)`; an unlabeled filter select or switch is a
  failure.
- **Click handlers go on buttons.** A clickable card or icon gets
  `make_activatable(el, label)` so it's in the tab order and fires on
  Enter/Space.
- **Never remove the focus ring.** It's a 2px `--accent` outline on everything,
  Quasar's `.no-outline` controls included.
- **Dialogs are named by their title and return focus** to whatever opened them
  (`static/js/a11y.js`). Use `dialog_header` and you get both.
- **Contrast is 4.5:1 for text, 3:1 for large text and icons**, in light and
  dark. Check both modes; most of the 2026-10 failures were dark-only.
- **Every page works at 390px wide** without sideways scrolling: tables become
  cards, dialogs become sheets.

## Words

UI copy follows [CLAUDE.md § Writing user-facing text](../CLAUDE.md#writing-user-facing-text)
and [Calls to action](../CLAUDE.md#calls-to-action-must-land-on-the-control-that-performs-them).
Sentence case everywhere, badges and table headers included.

## Checking your change

Automated, on every PR:

| Check | Catches |
|---|---|
| `tests/theme/test_style_guide.py` | Dialog cards off the three sizes; colour literals in `.style()` / slot `style=`; `text-h1`…`h5` titles; hex colours in CSS rules outside token definitions; `:root` aliases not restated for dark mode; text tokens under 4.5:1 on any surface in either mode |
| `tests/test_a11y_names.py` | Icon-only `<q-btn>` in a slot template with no name |
| `check_table_grid`, `check_table_prefs` hooks | Tables with no phone card view or no `table_key` |
| `scripts/ui_a11y_scan.js` (CI `browser` job) | On every page in `scripts/ui_a11y_ci.json`, in light and dark: axe's WCAG 2.1 A/AA rules, and rendered text under 4.5:1 |

The browser scan runs locally against the seeded app (boot and seed as in the
[ui-validation skill](../.claude/skills/ui-validation/SKILL.md)):

```bash
npm install --no-save playwright@1.56.1 axe-core@4.10.3   # once
node scripts/ui_a11y_scan.js scripts/ui_a11y_ci.json
```

It writes `report.json` under `<outDir>/a11y/`. When it fails:

- **A contrast hit** names the element, its class and the ratio. Fix the colour
  at the token or the class, never by adding a one-off hex. If it fails only in
  dark mode, look for an un-restated alias (trap 1 above) or a Quasar class that
  needs an `@layer theme` rule (trap 2).
- **An axe hit** names the rule and the element. `button-name`, `label` and
  `aria-dialog-name` are the common ones; the helpers above fix each.
- **Axe's own `color-contrast` rule is off on purpose.** Badges are tinted with
  an inset box-shadow (Quasar's layered `!important` background beats both
  `background-color` and `background-image`), axe can't see it, and it reports
  every badge as failing. The scan's own tint-aware check replaces it.
- **`a11y.ignore` in the config is for a finding that is wrong**, not one that is
  inconvenient. Each entry says why.

When a new page or a restyle lands, add it to `scripts/ui_a11y_ci.json`, then
look at it yourself in light, dark and at phone width (the ui-validation skill
screenshots all three). The scans prove the floor; they can't tell you that the
page looks like the rest of the app.

## Exceptions

A line that genuinely needs to break a mechanical rule says why in place:
`# style-guide: exempt — <reason>` in Python, `/* style-guide: exempt — <reason> */`
in CSS. The report stat figures (`text-h4`) and the charcoal offline banner are
the current examples. An exemption without a reason is a review comment waiting
to happen.
