# Wave 3 — the right message on the wrong door

**Read [README.md](README.md) first. Waves 1 and 2 must be merged** — wave 1 so
these paths can be driven, wave 2 so the messages this wave changes actually
arrive.

Wave 2 made the existing messages reach the screen. Three of them are the wrong
message: a player is told they lack admin permission, a permanent collision is
described as a transient failure, and an unlink says nothing about what it
changes. This wave is about accuracy, not delivery.

| Task | Touches | Size |
|---|---|---|
| T3.1 | `pages/challonge_oauth.py` — stop guessing which flow a callback completes | medium |
| T3.2 | `application/services/challonge_service.py` — the collision pre-check the other two providers run | small |
| T3.3 | measure what an unlink does, then say it | medium |

Three independent commits. T3.3 starts with a measurement and may end in a
question rather than a diff — read it before scheduling the wave.

---

## T3.1 — A callback that belongs to neither flow belongs to neither flow

Challonge registers one redirect URI for two flows — the STAFF service-account
connect and the player identity link — and disambiguates by which CSRF `state` is
pending in the session:

```python
if player_state is not None and (state == player_state or service_state is None):
    …player link…
else:
    …service connect…
```

When **neither** state is pending — a replayed callback, a stale tab, a
hand-typed URL, a bookmark — the condition is false and control falls into the
`else`. The service flow's default return is `_ADMIN_RETURN =
'/admin/challonge'`, so a player is answered *"403 Forbidden — You don't have
permission to view the admin area."* True, useless, and it reads as *linking is
staff-only*, which is the opposite of the truth.

**Replace the guess with three explicit outcomes.** Match the returned state
against each pending state by name, and give the no-match case its own exit:

1. `state` equals `player_state` → complete the player link (unchanged).
2. `state` equals `service_state` → complete the service connect (unchanged).
3. Neither matches, but exactly **one** flow is pending → complete *that* one
   with `code=None`, so it reports cancelled/failed and returns to its own return
   path. This preserves today's behaviour for the case the `or service_state is
   None` clause was written for (a provider redirect that carries an error and no
   usable state), which is why that clause must not simply be deleted.
4. Nothing pending, or both pending and neither matched → **complete nothing.**
   Stash a notice and return to the *profile*, never the admin area.

The fourth branch's copy has one job: name the flow the user was probably in and
give them the next step, without asserting a permission problem. Something in the
register of *"That Challonge link didn't complete. Try again from your profile."*
— wording is yours, but it must not say "permission", must not say "admin", and
must not name a state or a token.

**Why profile and not admin:** a player can always reach their profile; a staff
member can too. The reverse is not true, and the current default optimises for
the rarer actor. If a staff member replays a service-connect callback they land on
their profile with an accurate message, which is a strictly better failure than a
player landing on a 403.

**Watch the shared-callback invariant.** Both pending states are `pop`ped before
the branch runs, so they are consumed exactly once whichever way this goes —
keep that. A refactor that reads them without popping turns a replayed callback
into a repeatable one.

This is also where the audit's F3 stops being a Challonge quirk: the same
"one callback, two flows, disambiguate by state" shape will apply to any future
provider with a service-level and a player-level connection. The branch you write
here is the reference for that — keep it readable.

---

## T3.2 — The collision pre-check Challonge skips

`User.challonge_user_id`, `twitch_user_id` and `racetime_user_id` are each
`unique=True`. Two of the three write paths respect that in advance:

| Path | Pre-checks? | What the user sees |
|---|---|---|
| `IdentityLinkService.record_player_link` (racetime, Twitch, OAuth) | **yes** | *"That racetime account is already linked to PlayerOne."* |
| `ChallongeService.link_player_by_id` (staff override) | **yes** | *"That Challonge account is already linked to PlayerOne."* |
| `ChallongeService.record_player_link` (**the OAuth callback**) | **no** | *"Could not link Challonge. Please try again."* |

The third hits the unique index, raises `IntegrityError`, is swallowed by the
callback's `except Exception`, and produces advice that will fail identically
every time it is followed. Wave 1's T1.2 makes this a two-click reproduction
(two users linking at the same `MOCK_CHALLONGE_IDENTITY`), so capture both
strings — the racetime one and the Challonge one — side by side in the write-up.
The A/B is the evidence.

**Add the pre-check to `ChallongeService.record_player_link`,** mirroring
`link_player_by_id`: strip, reject empty with *"A Challonge account id is
required to link this user."*, look for another `User` holding that id, and raise
`ValueError(f'That Challonge account is already linked to {existing.username}.')`.
The callback's existing `except ValueError` then shows it verbatim.

**In the service, not the page.** A pre-check written into `challonge_oauth.py`
would put a business rule in the presentation layer (`enforce_architecture.py`
will block the model query outright) and would leave the REST and MCP surfaces
with the old behaviour.

**Expect the DRY hook to have an opinion.** `record_player_link` and
`link_player_by_id` will now differ only in the `'manual': True` audit detail —
and `IdentityLinkService.record_player_link` is a third copy of the same
validation. `check_dry_regressions.py` may flag it, and it would be right. The
clean resolution is one private helper on `ChallongeService` that both public
methods call, keeping their distinct audit details at the call site. Do **not**
reach further and try to fold Challonge into `IdentityLinkService`: Challonge has
a service-account half, its own feature flag, and `@requires_feature` on every
method — that is a bigger refactor than this wave, and a tempting one to
misjudge.

**The race survives and that is acceptable.** Two users linking the same id in
the same instant still reach the unique index. The pre-check turns the common
case (someone else already linked it, minutes or days ago) into a message that
tells the truth; the generic message remains correct for the genuinely rare
collision. Say that in the commit rather than reaching for a transaction.

**Tests** — `tests/services/` has the home for this:

```python
async def test_challonge_oauth_link_rejects_an_id_another_user_holds()
async def test_challonge_oauth_link_rejects_a_blank_id()
async def test_all_three_providers_report_a_collision_the_same_way()
```

The third is the one worth writing carefully: parameterise over racetime, Twitch
and Challonge, assert each raises `ValueError` naming the holding user, and it
becomes the guard that a fourth provider cannot be added without it.

---

## T3.3 — Measure what an unlink does before writing copy about it

The audit's F4 is `code-read` and its framing is incomplete. Profile's unlink
control says exactly `'{provider} account unlinked.'` and nothing else, and it
takes **one click with no confirmation** — which puts it squarely in the audit's
own cross-cutting theme, *"confirmation is spent on the reversible actions"*.

For Twitch and racetime an unlink is genuinely cheap: the identity is used for
attribution and auto-open eligibility, and re-linking restores it. Challonge is
not, and the mechanism is worth stating precisely because it decides what the
copy must say:

- `ChallongeParticipant` rows carry both `challonge_user_id` and a `user` FK,
  resolved at sync time from the linked account.
- Profile's read-only auto-enrolment reads `ChallongeParticipant.filter(user=…)`.
- `unlink_player` clears the three `User` columns and **nothing else** — the
  participant rows keep pointing at the user.

Read together (`code-read` — this is the part to verify, not to trust): unlinking
does not change the enrolment display at all, and the change lands invisibly at
the *next sync*, when the participant no longer resolves to a user and their
mirrored participation quietly detaches. A consequence that arrives hours later,
triggered by a worker, is the worst shape a consequence can have.

**So T3.3 is a measurement first.** With `MOCK_CHALLONGE` on and the seeded
mirror in place (wave 1), as a user who is a linked participant:

1. record the Profile enrolment state and the mirrored match rows;
2. unlink Challonge;
3. re-read both — is the checkbox still ticked? is the user still on the match?
4. run the Challonge sync;
5. re-read both again.

Write the before/during/after as a table, every row `measured`.

**Then, and only then, two outcomes:**

- **A confirmation dialog with accurate copy** — `ConfirmationDialog`
  (`theme/dialog/confirmation_dialog.py`, `tone='negative'`, and give it a `title`
  naming the provider; its message renders `pre-line`, so a two-paragraph body is
  fine). The Challonge body states what the measurement showed; Twitch and
  racetime get a shorter one, or none — do not put a modal in front of a
  genuinely cheap action just for symmetry, which is the mistake the crew-signup
  audit found. The per-provider text belongs on `LinkSectionConfig` as a new
  optional field, beside `unlinked_message`, so `_render_provider_row` stays
  provider-agnostic (wave 4 renders the config fields that already exist there;
  this adds one more in the same spirit).
- **A question, if the measurement shows participation detaching silently.**
  Whether `unlink_player` should clear `ChallongeParticipant.user` immediately —
  making the consequence visible at the moment of the click instead of at the
  next sync — is a **behaviour change with bracket implications**, and it is not
  this plan's call. Bring the measurement and the question to the user. Do not
  quietly implement it, and do not quietly skip it: an accurate warning about a
  consequence that arrives invisibly later is the minimum, not the resolution.

---

## Verify

At 1500px and 430px, tagging every row `measured`:

| Probe | Expect |
|---|---|
| `/t/default/challonge/oauth/callback` as `player_three`, nothing pending | Profile, an accurate message, **no 403 and no admin page** |
| the same as `staff_user`, nothing pending | Profile, the same message — not a silent admin landing |
| a genuine pending player link, mock | unchanged: link recorded, success toast |
| a genuine pending service connect, mock, as `staff_user` | unchanged: connection saved, returns to `/admin/challonge` |
| two users at the same `MOCK_CHALLONGE_IDENTITY` | *"That Challonge account is already linked to …"*, matching the racetime wording |
| unlink Challonge as a linked participant | the confirmation states what T3.3 measured; the toast is unchanged |
| unlink racetime | unchanged, or a short confirm — whatever T3.3 concluded |

`poetry run pytest` green; `scripts/ui_flag_sweep.sh` still clean (T3.2 touches a
`@requires_feature` service — a flags-off tenant must still get
`FeatureDisabledError`, not a collision message).

Commit T3.1 as *"Stop answering a stray Challonge callback with an admin
refusal"*, T3.2 as *"Tell a Challonge player their account is already linked"*,
T3.3 as *"Say what unlinking Challonge changes"* (or, if it ends in the question,
commit the measurement into the wave write-up and raise it).
