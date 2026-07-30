# Equipment UX — implementation plan

Ship the findings of
[reviews/equipment-live-event-ux.md](../../reviews/equipment-live-event-ux.md):
make the on-site lending loop trustworthy on a phone, on a venue network, in the
hands of a volunteer who is not staff.

**Read this file completely before starting any task.** It carries the evidence,
the design decisions and the ground rules that the wave files do not repeat.

## Wave files

| Wave | File | Theme | Migration? |
|---|---|---|---|
| 1 | [wave-1-trustworthy-actions.md](wave-1-trustworthy-actions.md) | An action is never silently lost, and the scan → login → asset link is exact (F1, F2) | no |
| 2 | [wave-2-phone-first.md](wave-2-phone-first.md) | The phone tells the truth about what you can do and why (F3, F7, F5) | no |
| 3 | [wave-3-borrower-scope.md](wave-3-borrower-scope.md) | The borrower picker offers this community's people, not the platform's (F4) | no |
| 4 | [wave-4-label-host-check.md](wave-4-label-host-check.md) | A batch of labels can't be printed against the wrong host unnoticed (F6) | no |

Wave 1 is the critical fix and stands alone. Wave 2 is the largest behaviour
change on screen and depends on nothing in wave 1. Wave 3 is the only wave that
touches the repository/service layers and the only one with an **open decision
that needs sign-off before coding** — see its file. Wave 4 is the smallest and
the least valuable; **stopping after wave 3 is a legitimate outcome.**

Do not start wave N+1 until wave N is merged.

## The evidence this exists to fix

All of it measured on the running app against the seeded `default` tenant at
390×844 — the audit has the full tables; these are the four facts the waves turn
on.

**An action clicked during a network blip disappears.** Offline → click
**Check in** → no notification, no error, no disabled control, no connection
overlay; reconnect → the asset still reads `Checked out` and nothing ever says
the click failed. The framework's own asymmetry is the root: `ui.run_with`'s
`message_history_length=1000` replays **server→client** messages across an
interruption, but a **client→server** UI event has no ack and no replay. And the
framework's "Connection lost" popup (`#popup`, already branded in
[`static/css/styles.css`](../../../static/css/styles.css) — search
`.nicegui-error-popup`) only fires on socket `disconnect`, which lags a dead
network by up to `ping_interval + ping_timeout` — 4 s + 2 s at the default
`reconnect_timeout=3.0` (`nicegui/nicegui.py:131-132`). The audit's 4 s offline
window closed before it could ever show.

**`ui.navigate.to` prepends the tenant prefix — always.** `nicegui.js` line 520:

```js
open: (msg) => { const url = msg.path.startsWith("/") ? options.prefix + msg.path : msg.path; ... }
```

`options.prefix` is `X-Forwarded-Prefix` + `root_path` (`nicegui/client.py:172`),
i.e. `/t/<slug>` in path mode and `''` on a custom domain or the platform host.
Most of the codebase already relies on this deliberately (see the comments in
[`qr_label_dialog.py`](../../../theme/dialog/qr_label_dialog.py),
[`match_slots.py`](../../../theme/tables/match_slots.py),
[`match_handlers.py`](../../../theme/tables/match_handlers.py)). The two
post-login `ui.navigate.to` calls in
[`pages/auth.py`](../../../pages/auth.py) pass a path that is **already**
prefixed, so it gets prefixed twice.

**The mobile register's row actions are four unlabelled icons and one of them
deletes.** In the `item` slot of
[`admin_equipment.py`](../../../pages/admin_tabs/admin_equipment.py) the only
explanation is a `q-tooltip`, and this codebase already established that
*"the proctor reads this board on a tablet, where a tooltip never opens"*
([`match_slots.py:349-352`](../../../theme/tables/match_slots.py#L349)).

**The borrower picker is `UserService.get_all_users()`** — 11 options in the
seeded tenant, every `User` on the platform, the `System` service account
included, and the audit's own checkout went to `System`.

## What is settled and not in scope

- **The asymmetric gate stays.** `can_checkout_equipment` admits volunteers;
  `can_checkin_equipment` is manager-only, so a return is recorded by someone
  accountable for the item coming back. The audit records this as intentional
  (RC1) and only the *silence* about it is a finding (F7). **A task that widens
  `can_checkin_equipment` is wrong — stop and ask.**
- **No new feature flag.** Equipment is already behind `FeatureFlag.EQUIPMENT`
  (`application/feature_flags.py`); every change here lands inside an
  already-gated subsystem, so CLAUDE.md's step 0 is asked and answered: no.
- **No physical-device pass.** Everything the audit measured is emulated
  Playwright and so is everything here. F1 in particular deserves a real phone on
  real venue Wi-Fi; that remains open work, not a wave.
- **The equipment REST surface.** There isn't one — `api/routers/` has no
  equipment router, and MCP's equipment tools are read-only. Nothing in this plan
  needs one.

## Design decisions

Fixed. **If a task seems to contradict one of these, the task is wrong — stop
and ask.**

- **Offline honesty is client-side.** While the socket is down the server has no
  way to say anything: `ui.notify`, a refresh and a disabled-state update all
  travel over the same dead socket. The F1 fix therefore lives in the browser —
  a script and CSS under `theme/` + `static/css/` — and is judged by what the
  operator sees with the network off, not by a server-side handler.
- **No queue-and-retry.** A checkout is not idempotent and a click replayed after
  a reconnect (possibly after the asset moved) is worse than a refused one. The
  contract is *refuse loudly now*, never *maybe later*.
- **No optimistic UI.** The page must never show a state the server has not
  confirmed. Every fix here makes the page **less** willing to imply success.
- **`ui.navigate.to` takes tenant-local paths.** `/equipment/3`, never
  `/t/default/equipment/3` — the framework adds the prefix. The fix for F2 is to
  stop handing it a prefixed path, not to special-case the doubling.
- **Presentation-first.** Waves 1, 2 and 4 add no model, no migration and no new
  service method except where a bounded read demands one (task 2.3). Wave 3 is
  the only one that reaches the repository.
- **A picker filter is not an authorization rule.** Wave 3 narrows what the
  borrower select *offers*; the hard rules the service enforces are separate and
  deliberately narrower. Read that wave's decision section before writing either.
- **The audit's viewport is the acceptance viewport.** 390×844, and as each role
  the surface admits — manager, volunteer, signed-out. A change verified only at
  desktop width is not verified.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit:

**Three-layer pattern.** Presentation (`pages/`, `theme/`) → Service → Repository
→ Models; `enforce_architecture.py` blocks violations at write time. Waves 1, 2
and 4 are almost entirely presentation — resist the pull to put a host
comparison or a history bound in a service just because it looks like logic.
Wave 3's new read belongs to `UserService`, **not** `EquipmentService`: it is a
people query several surfaces need (the match dialog and the Users tab have the
same leak), and hanging it off the equipment service would drag
`FeatureFlag.EQUIPMENT`'s `service_modules` gating onto a read that has nothing
to do with the flag.

**Tenant scoping.** The new people read in wave 3 is the one place a leak is
possible: scope through `application/repositories/_tenant.py`, and add the leak
test (`tests/tenancy/`) that proves another community's user never reaches the
picker.

**Errors and toasts.** Services raise `ValueError` / `PermissionError`;
presentation catches and calls `notify_error(e)`
([`theme/notify.py`](../../../theme/notify.py)).
[`checkout_dialog.py`](../../../theme/dialog/checkout_dialog.py) still hand-rolls
`ui.notify(str(e), color='warning')` in three places — whichever wave touches it
first converts them.

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`; capture
`context.client` before a background task and restore it with `with client:`
(never `Client.current`, never `async with`). Any new client-side script must
tolerate `window.socket` not existing yet — it is created in `nicegui.js`'s
`mounted()`, which may run after your snippet is parsed.

**Mobile.** The four family tables (match / user / tournament / equipment) keep
their **bespoke** `item` slots — `enable_mobile_grid` is not the answer for
equipment. `check_table_grid` only proves a grid exists; keeping the card's
actions labelled and the destructive one separated is wave 2's job, and the
desktop `body-cell-actions` slot and the card `item` slot must stay in step (the
equipment surfaces duplicate their button HTML in both — see
`admin_equipment.py` and `home_tabs/equipment.py`).

**Dev seed.** Two waves need fixtures the seed cannot currently produce (an
equipment-manager-only user; a volunteer *holding* an asset; an asset with a long
history; a user who belongs only to the other tenant). Extend
[`scripts/seed_dev.py`](../../../scripts/seed_dev.py)'s equipment block —
idempotent (`get_or_create`), tenant-scoped like the rows around it. A fixture no
one can produce is a finding no one can re-check.

**File length.** `check_file_length.py` advises over 800 lines; none of these
files are close, but `pages/equipment.py` (155) doubling in wave 2 would be a
smell — extract a `theme/` helper instead.

## Verification loop

```bash
bash scripts/setup_env.sh                      # once
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/default/login`: `staff_user` (also EQUIPMENT_MANAGER),
`player_two` / `player_three` (plain volunteers), plus the roles wave 2's seed
task adds. Chromium is at `/opt/pw-browsers` — **never run
`playwright install`**. `scripts/ui_smoke.js` is a config-driven harness (read
its header); multi-step flows need a one-off script that reuses its login.

The surfaces every wave re-checks, **at 390×844 and 1500 px**:

- `/t/default/equipment/1` and `/t/default/equipment/3` as manager, as volunteer,
  and signed out (the scan target — one available asset, one checked out)
- `/t/default/admin/equipment` as manager (the register)
- `/t/default/home/equipment` as volunteer (`INVENTORY` + `MY CHECKOUTS`)
- `/t/default/equipment/qr-labels?ids=1,2,3` as manager (the label sheet)

```bash
poetry run pytest                    # whole suite, parallel
poetry run pytest -n0 -k equipment   # serial, for -s / pdb
scripts/ui_flag_sweep.sh             # flags-off sweep — equipment is flagged
```

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why. Two things here genuinely cannot: a dead socket
   and a printed label. Where that is true, the proof is a re-measurement pass
   with the numbers written into the wave's commit message, in the audit's own
   format ("offline click → …").
4. The affected surfaces render at both widths, verified by screenshot, with no
   new console errors.
5. Docs named in the task updated.
6. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and say
explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each wave
file as its wave merges. When the last one lands:

- delete this directory and its row in [docs/README.md](../../README.md)'s
  "Work in flight" table;
- delete [reviews/equipment-live-event-ux.md](../../reviews/equipment-live-event-ux.md),
  its row in [reviews/README.md](../../reviews/README.md), and the pointer line
  above that table;
- prune what the waves actually fixed from
  [reviews/README.md](../../reviews/README.md)'s **cross-cutting themes** — the
  global-`User`-picker bullet loses its equipment clause in wave 3 but stays for
  the Users tab and the match dialog, and the dev-seed bullet loses its
  equipment-manager clause in wave 2;
- make sure the behaviour lives in the feature docs — principally
  [`docs/reference/frontend.md`](../../reference/frontend.md) (the asset page, the
  register, the home tab, the label sheet) and
  [`docs/reference/services.md`](../../reference/services.md) (wave 3's new read).

Git history holds the rationale.
