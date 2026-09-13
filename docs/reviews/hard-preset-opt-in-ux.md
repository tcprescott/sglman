# Harder-settings opt-in — UX audit

Drove the flow against the running app (seeded `default` tenant) as
`player_one` (in an agreed match, an offered match and a staff-forced one),
`player_two` (opted in, waiting), `player_three` (the holdout on a match whose
opponent has opted in), and `staff_user` (the admin dialog). Desktop measured at
1280 / 1440 / 1680 / 1920 / 2000, mobile at 390×844. Gates read before the
pages. Discord covered separately by the `/discord-ux` pass in the same branch.

## The secrecy guarantee holds at the surface

Driven, not read. On match 12 — `player_two` has opted in, `player_three` has
not — the two boards render:

| Viewer | Settings cell | Mobile card |
|---|---|---|
| `player_two` | `hourglass_top`, primary | *Opted in — waiting* |
| `player_three` | `bolt`, grey | *Harder settings* |

`player_three`'s cell is byte-identical to the one on a match nobody has opted
into. No row field, tooltip, card label or DM carried the opponent's answer.
The `_hard_agreed` field — the only one that reports anybody else — was false
in `player_three`'s row payload.

## Findings

### 1. The control is off-screen at every desktop width — `driven`

The player board is ten columns and 1463px wide; the scroll viewport at 1440px
is 1026px. `Settings` ends at 1386px, so it sits **360px past the fold** at
1440, 520px at 1280, and is still 36px short at 1920. Measured cumulative
positions at 1440:

```
 700 PLAYERS         VISIBLE
 791 STAGE           VISIBLE
 937 GENERATED SEED  VISIBLE
1022 STREAM          VISIBLE
1133 CHANGE          off
1386 SETTINGS        off
1463 WATCH           off
```

A player who never reads the Discord DM, or who wants to change their mind
later, has to scroll a wide table sideways looking for a control they have no
reason to know exists. `notification_links.player_hard_preset`'s own docstring
names this risk — "a reader who cannot find the control cannot use the feature"
— and the board is now one column wider than when that was written.

Partly mitigated: the deep link opens the dialog directly, and a viewer can
reorder or hide columns from the gear (`UserTablePreference`).

**Not fixed here, deliberately.** Reordering only moves the problem: pulling
`Settings` in front of `Stage`/`Generated Seed` gains 237px and pushes the seed
link — what a player most needs on match day — off instead. The honest
statement is that the board is over its width budget at 1440 and the tenth
column is the one that lost. That is a column-budget decision for the board as
a whole, not something this feature should settle on its own.

### 2. One preset name set the widest column on the board — `driven`, **fixed**

`Settings` measured **253px at 1440 — wider than `Players` (193px)** — because
the override chip printed the full preset name inline (`ALTTPR Open — Hard
Mode`) with no bound. The name is tenant-supplied, so a longer one widens it
without limit.

Fixed with a `.wiz-chip--name` cap (16ch, ellipsis, full text still in the
tooltip), applied to both name-carrying chips in `HARD_PRESET_SLOT`. `Settings`
253px → 198px and the board 1463px → 1408px; the two overrides stay
distinguishable at a glance (`ALTTPR OPEN — …` vs `ALTTPR OPEN`). The mobile
card keeps the full name — it has the room.

### 3. `set_override` had no service-layer gate — `code-read`, **fixed**

Overruling two players' settings and DMing them about it was authorized by
nothing but whichever page called it. Its sibling `MatchService.update_match`,
which does strictly less, opens with
`AuthService.ensure(can_crud_match(actor, match))`.

Not exploitable today — the admin dialog is the only caller and sits behind a
staff gate — but it is the shape the feature-flag doc warns about in the
neighbouring case: a UI-only gate is not a gate for the next caller. Added the
same `can_crud_match` check, pinned by a test that a player cannot overrule
their own match.

### 4. The player's per-match dialog is unreachable — `driven`, pre-existing

`UserMatchDialog(match=...)` renders the two per-player match toggles (watch,
stream offer) and is wired into Home → Schedule as `on_edit`. That tab declares
no `id`/`edit` column, and `register_body_slots` hangs the edit affordance on
that cell — so **nothing on the page opens it**. Driving the row produced one
button (`notifications_none`); no dialog.

This is out of this feature's scope, but it closed off the natural home for
finding 1: the opt-in is the third toggle of exactly that family, and it can't
go where the other two live while nobody can open that dialog.

### 5. Two reads nothing called — `code-read`, **fixed**

`MatchHardPresetService.opted_in_match_ids` (a pass-through nothing used —
`board_states` calls the repository directly) and
`MatchHardPresetRepository.get_by_match_and_user` (no caller anywhere, tests
included, and the only method that returns a row object rather than ids).

In a service whose safety argument is "the repository is reachable only by its
service, which exposes exactly two reads", a third unused read is a liability
rather than dead weight. Both deleted.

## Checked and fine

- **Admin dialog** — *Seed settings* offers three options, correctly labelled
  from the tournament's own presets (`Let the players decide (they get ALTTPR
  Open unless all opt in)` / `Force ALTTPR Open — Hard Mode` / `Force ALTTPR
  Open`), with the caption *"Overrides the players' own choice. They are DMed
  either way."* Saved a real override; it persisted and both players were DMed.
- **The override no longer outlives a failed save.** Reproduced the original
  bug live: saving an override on a match outside its tournament's hours fails
  validation. Under the fix the override was **not** written — match 11 stayed
  `None` — where previously it was written and DMed before the failure.
- **Mobile (390×844)** labels every state plainly (*Harder settings*, *Opted in
  — waiting*, *Playing ALTTPR Open — Hard Mode*) and keeps the secrecy: the
  holdout's card reads the same as an untouched match. The desktop table is the
  weaker of the two surfaces here, which is the reverse of the usual.
- **Flag sweep** clean on both passes; no server-side errors across the run. The
  only console error (`Anchor: target "#c332" not found`) reproduces on matches
  this feature does not touch.
