# PR 1 — Home: ten tabs to four

**Status: done.** Reference for what moved where; the living description is
[reference/frontend.md → Home](../../reference/frontend.md#home--pageshomepy).

## Before

A signed-in member on a fully-featured community got ten tabs: Schedule, On Air,
Brackets, Profile, Player, Tournaments, My Availability, My Crew, Triforce Texts,
Equipment. Flags moved the count between five and ten. The phone bottom bar
renders four, so **Player** — the player's own matches, and the target of four of
the six Discord link targets — sat behind **More**.

## After

| Tab | Holds |
|---|---|
| Event | Schedule board, On Air timeline, Brackets, as a view switcher |
| My Schedule | Your matches, crew commitments, availability, equipment checkouts |
| Tournaments | Signup cards; triforce text submission on the matching card |
| Profile | Unchanged |

## What moved

- **Event** (`pages/home_tabs/event.py`) is a shell over the three existing view
  modules, which keep their builders and table keys. `available_views` and
  `resolve_view` are pure and unit-tested. The switcher does not render when only
  one view is on offer.
- **My Schedule** (`pages/home_tabs/my_schedule.py`) stacks the four section
  builders, all open, no expansions. The `schedule`/`reschedule`/`match` deep-link
  params pass straight through to the matches section.
- **Equipment on home is checkouts only.** Browsing the register left the player
  surface; it lives on Admin → Equipment, and borrowing is the QR scan into
  `/equipment/<id>`, which is the path `can_checkout_equipment`'s docstring
  describes anyway. `TableKeys.EQUIPMENT_INVENTORY` was retired with it.
- **Triforce texts** lost its tournament index — you were picking a tournament
  twice — and became `open_triforce_dialog` on the signup card.

## Aliases

`BaseLayout` tab dicts gained `'aliases'`, resolved on read-in only through
`_label_by_alias` (consulted after `_label_by_slug`, so a live tab's slug can
never be shadowed) and never written back.

| Retired slug | Opens |
|---|---|
| `player`, `my-crew`, `availability`, `equipment` | My Schedule |
| `schedule`, `on-air`, `brackets` | Event, on that view |
| `triforce-texts` | Tournaments |

`tests/test_home_nav.py` pins every one, plus the invariant that home stays within
`BaseLayout.BOTTOM_NAV_CAPACITY`.

## The bottom bar

Now renders **only where every tab fits it**, and the **More** button is gone
entirely — it existed to reach tabs the bar could not hold, and the bar no longer
renders in that case. Home qualifies; Admin (27 tabs) and Volunteer navigate by
drawer, reachable from the header burger. Pinned by `tests/theme/test_bottom_nav.py`.

## Also

The signed-out branches in the tab modules came out — the lock card in
`player.py` and the Login with Discord button in the schedule header. Home is
members-only: `enforce_membership` renders the join page for anyone else,
anonymous included, before a tab is built, so those were unreachable. The
one-line `user is None` guards stayed; they are defensive, not misleading
call-to-action dead ends.

No model, repository, service, or migration changes.
