# Accessibility audit, October 2026

Target: WCAG 2.1 AA across every page a member, crew, staff or platform owner
reaches, at 1440px and 390px, light and dark, signed in and out.

## How it was run

- **axe-core 4.10** (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `best-practice`)
  injected by Playwright into every drawer page under `/t/default/home`, `/admin`
  (including all eight Settings panes), `/volunteer`, `/checkin`, `/platform`,
  `/qualifiers`, `/help`, `/event-info`, `/changelog` and the profile, as
  `staff_user`, `super_admin` and signed out. 44 pages at desktop, 19 at phone.
- **By hand**: tabbing the header, drawer and a match board; opening the Edit
  Match dialog from the keyboard and closing it with Escape; Enter on Help
  cards; the skip link.
- Contrast was the style pass's job (PR #314) and was not redone, except where a
  scan here turned up something it missed.

## What the scan found, and what changed

| Finding | WCAG | Before | After |
|---|---|---|---|
| Icon-only buttons with no name (a tooltip is not one) | 4.1.2 | 531 on 44 pages | 0 |
| `<html>` had no `lang` | 3.1.1 | every page | fixed (`language='en-US'`) |
| No `<h1>` on any page | 1.3.1 | every page | `page_header`/`page_title` render h1; tabs without a title get a hidden one |
| No way past the header and drawer | 2.4.1 | — | Skip to content link, first tab stop |
| Filter-strip selects (Day/Tournament/Stage/State) unnamed | 4.1.2 | 12 on 6 pages | `<label for>` the control |
| Feature switches, Discord/volunteer mapping checkboxes unnamed | 4.1.2 | 23 | named |
| Stream icon links unnamed | 2.4.4 | 14 | named |
| Check-in progress bar unnamed | 1.1.1 | 1 | named |
| Buttons and toggles showed focus only as a faint tint | 2.4.7 | header, rows, toggles | 2px ring like every other control |
| Help/Event Info cards, bracket matches, date-picker icons were click-only | 2.1.1 | — | in the tab order, Enter/Space activate |
| Dialogs had no accessible name | 4.1.2 | every dialog | named by their title |
| Closing a dialog dropped focus to `<body>` | 2.4.3 | Edit Match and other table-row dialogs | focus returns to the button that opened it |
| Phone tab bar labels 4.0:1 | 1.4.3 | every tabbed page on a phone | 4.9:1 |
| Cat fact under empty lists 2.7:1 | 1.4.3 | every empty list | muted by colour, not opacity |
| Ember text buttons in dark mode 3.5:1 | 1.4.3 | `/platform` | lifted toward white |
| Orange Restart button 2.2:1 | 1.4.3 | `/platform` bots | `warning` |

The shared pieces live in `theme/a11y.py` and `static/js/a11y.js`; see
[frontend.md](../reference/frontend.md#accessibility-themea11ypy).
`tests/test_a11y_names.py` fails on any new icon-only `<q-btn>` in a slot
template without a name.

## Still open

- **Badge contrast is reported by axe, but is fine.** Badges are tinted with an
  inset box-shadow, which axe can't see, so it compares dark text against the
  solid Quasar colour and reports ~60 failures. The style pass's tint-aware
  checker (`final-checks/ui-cohesion/contrast-scan.js`) is the one to trust.
- **Action columns have empty `<th>`** (axe best-practice, not a WCAG failure).
  Giving them text would also put an "Actions" caption on every mobile card,
  which reads column labels.
- **The mock login picker** (`/login` with `MOCK_DISCORD`) has 3.3:1 buttons.
  Dev-only; production shows the Discord button.
- **Platform pages** use the tenant-less chrome, so they have no skip link and
  no dialog focus repair.
- Not tested: a real screen reader (VoiceOver/NVDA) pass, 200% zoom reflow, and
  Discord DMs (outside the web app).
