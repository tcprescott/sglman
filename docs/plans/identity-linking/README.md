# Identity linking — implementation plan

Make the account-linking flow (Challonge / Twitch / racetime.gg) tell the user
what happened. The engine is well-factored and its security reasoning is sound;
what it does not do is *speak*. Four carefully-written failure messages exist and
none of them reaches a screen, a player who lands on the wrong callback is told
they lack admin permission, and the two sentences explaining what each link buys
are configured but never rendered.

**Read this file completely before starting any task.** It carries the evidence,
the design decisions and the ground rules the wave files do not repeat.

**Input:** [`docs/reviews/identity-linking-ux.md`](../../reviews/identity-linking-ux.md).
Read it too — but read the *Corrections* section at its end first: planning
against the code overturned two of its claims, and the waves below follow the
corrected picture.

## Wave files

| Wave | File | Theme | Migration? |
|---|---|---|---|
| 1 | [wave-1-drive-it.md](wave-1-drive-it.md) | Turn the dev loop on, so waves 2–4 can be measured rather than reasoned about | no |
| 2 | [wave-2-failure-visible.md](wave-2-failure-visible.md) | A notice that survives the redirect; return the user where they were | no |
| 3 | [wave-3-right-message.md](wave-3-right-message.md) | Stop guessing which flow a callback completes; say what a collision and an unlink actually mean | no |
| 4 | [wave-4-point-of-decision.md](wave-4-point-of-decision.md) | Render the copy the section already carries and never shows | no |

**No wave changes a model, so no wave has a migration.** That is unusual for a
plan this size and it is the point: every finding here is a message, a redirect
target, or a branch — nothing needs new state.

Wave 1 is a **prerequisite for measuring** waves 2–4: without it, the flows those
waves change cannot be driven at all in dev, and their verification sections
collapse back into code-reading. Do it first even if you intend to stop early.

**You can stop after wave 2** — F1 and F2, the two Majors, are both fixed there.
Waves 3 and 4 are smaller and independent of each other.

Do not start wave N+1 until wave N is merged.

## The scope

The shared engine [`pages/_oauth_link.py`](../../../pages/_oauth_link.py); the
three provider sections on Profile
([`_link_section.py`](../../../pages/home_tabs/_link_section.py) plus one
`LinkSectionConfig` per provider); the callback pages
([`racetime_oauth.py`](../../../pages/racetime_oauth.py),
[`twitch_oauth.py`](../../../pages/twitch_oauth.py),
[`challonge_oauth.py`](../../../pages/challonge_oauth.py)); and
`IdentityLinkService` / `ChallongeService`'s player-link half /
`OAuthHandoffService`.

**Discord login is out of scope** — but note that `pages/auth.py`'s callback has
the *same* notify-then-navigate shape wave 2 fixes, so wave 2's mechanism is
built to be reusable there and wave 2 names that follow-up explicitly.

## The evidence this exists to fix

Read against the branch this plan was written on.

**Every failure message is discarded by the navigation that follows it.** The
shape appears five times — `_finish_link`, `_finish_player_link`,
`_finish_service_connect`, and twice in the `/oauth/link/claim` handler:

```python
ui.notify('…', color='warning')
ui.navigate.to(return_path)     # the browser unloads; the toast dies with it
```

`ui.notify` enqueues a `notify` message on *this* client's outbox
(`nicegui/functions/notify.py`); `ui.navigate.to` then unloads the document the
toast would render in. The audit probed this and got HTTP 200, a rendered page,
and **no notification** — for a bad claim token, for a codeless Twitch callback,
and for a codeless racetime callback. Nine written strings across the four
modules are unreachable in practice.

**Two of the claim route's three failure exits go to a hardcoded path.** The
handler computes `next_path` from the token payload, then the
expired-token and wrong-browser branches navigate to the literal `/home/profile`
and the signed-out branch to `/login`, ignoring it. In path mode that path has no
`/t/<slug>` prefix, so it resolves on the platform host and renders the community
picker.

**The claim route has no mode guard, and its sibling does.**
`/oauth/link/start` opens with `if not host_oauth_handoff_enabled(): return
RedirectResponse('/login')`. `/oauth/link/claim` has no equivalent, so it serves
path-mode requests it structurally cannot complete — which is exactly what the
audit's F1 probe hit. F1 is therefore *two* defects wearing one symptom: the lost
message (real, and just as true of the in-place callbacks) and a route answering
a request that isn't addressed to it.

**Challonge's shared callback guesses, and guesses towards staff.** One
registered redirect URI serves both the service-connect and the player-link
flow, disambiguated by which CSRF state is pending. When *neither* is pending —
a replay, a stale tab, a hand-typed URL — the `if player_state is not None …`
condition is false and control falls to the `else`, i.e. the service flow, whose
default return is `_ADMIN_RETURN = '/admin/challonge'`. A player is answered
*"403 Forbidden — You don't have permission to view the admin area."*

**One provider skips the collision check the other two run.**
`User.challonge_user_id`, `twitch_user_id` and `racetime_user_id` are each
`unique=True`. `IdentityLinkService.record_player_link` (racetime, Twitch) and
`ChallongeService.link_player_by_id` (the staff override) both pre-check and
raise `ValueError('That … account is already linked to {username}.')`.
`ChallongeService.record_player_link` — the one the OAuth callback calls — does
not. It hits the unique index, raises `IntegrityError`, is caught by the
callback's `except Exception`, and the user is told *"Could not link Challonge.
Please try again."* — advice that will fail identically every time.

**The section's explanatory copy is configured and never rendered.**
`LinkSectionConfig` declares `description` and `link_button_label`;
`_render_provider_row` reads neither. The button is the literal string `'Link'`.
So *"Link your racetime.gg account so we can attribute your race results and
check auto-open eligibility."* exists in the source, is quoted approvingly in the
audit, and has never appeared on a screen. This is the audit's own
[cross-cutting theme](../../reviews/README.md#cross-cutting-themes) —
*"capabilities nobody wired are invisible"* — landing on the audit itself.

**The dev loop was never switched on.** `MOCK_RACETIME`, `MOCK_TWITCH` and
`MOCK_CHALLONGE` all exist, each with a canned four-identity client and a
`MOCK_<PROVIDER>_IDENTITY` env hint choosing between them, and each provider's
`is_configured()` returns `True` under its mock. But `scripts/setup_env.sh`
writes only `MOCK_DISCORD` and `MOCK_SEEDGEN`, and `start.sh mock` exports only
`MOCK_DISCORD` / `MOCK_CHALLONGE` / `MOCK_SEEDGEN`. That is why the audit saw a
Profile page with no linking UI at all and had to code-read half its findings.
**The capability the audit asked for in F5 is already built; nothing turns it
on.** Wave 1 is that switch.

## Design decisions

Fixed. **If a task seems to contradict one of these, the task is wrong — stop
and ask.**

- **No new feature flag.** Linking is existing infrastructure, not a gated
  subsystem: Challonge already sits behind `FeatureFlag.CHALLONGE` (and
  `player_edit_info.py` correctly omits its row when the flag is off), while
  racetime and Twitch are gated by whether credentials are configured. A fourth
  gate would only add a way to be inconsistent. Per
  [CLAUDE.md](../../../CLAUDE.md) step 0 this was asked and answered — do not
  add one.
- **One carrier for post-redirect notices, one drain point.** Wave 2 introduces
  exactly one mechanism and every call site uses it. Two carriers (a session
  stash *and* a query flag) is how the four messages get lost again in a corner
  nobody drains.
- **The notice is presentation, not domain.** It lives in `theme/`, is a sibling
  of `theme/notify.py`, and no service knows it exists. Services keep raising
  `ValueError`; only the redirecting page decides a message must outlive the
  redirect.
- **A provider label comes from the provider.** `provider_label` /
  `LinkSectionConfig.title` already carry it. A new hardcoded `'racetime.gg'` or
  `'Challonge'` in a shared module is a bug — the engine is shared precisely so
  a fourth provider needs no edits to it.
- **The mocks make the flow drivable; they do not become the test suite.** Mock
  mode is for the browser loop. Every behaviour change in waves 2–4 also needs a
  pytest that fails without it, because `MOCK_*` short-circuits are refused in
  production and prove nothing about the real path.
- **No new events.** Link/unlink are audited (`AuditActions.TWITCH_LINKED`,
  `CHALLONGE_PLAYER_LINKED`, …) and publish nothing on the bus. That is the
  status quo and this plan keeps it: `EventType` is an external contract, and
  adding link events is a separate decision with subscribers to consider.
- **Do not touch the security reasoning.** The one-use token, the browser
  binding (`_bind_matches`, fail-closed), the state-mismatch handling and the
  stale-marker drop are correct and each carries a comment saying why. Wave 2
  changes *where the user lands and what they are told*; it must not change
  which tokens are accepted. Any diff that alters an accept/reject decision in
  `handoff_service.claim` or `_bind_matches` is out of scope — stop and ask.

## Not in scope

Discord login (`pages/auth.py`) beyond noting the shared bug; the Challonge
service-account connection except where its callback collides with the player
flow; bracket participant matching; link/unlink events on the bus; and any change
to `OAuthHandoffService`'s crypto.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit:

**Three-layer pattern.** `enforce_architecture.py` blocks violations at write
time. These waves are almost entirely presentation: the pages decide what to say
and where to go. The one service-layer change is wave 3's collision pre-check,
which belongs in `ChallongeService` and nowhere else — a pre-check written into
the callback page would be a business rule in the presentation layer, and it
would leave `link_player_by_id`'s and the REST surface's behaviour inconsistent
with it.

**Errors.** Services raise `ValueError` (user-facing) / `PermissionError`
(authorization); presentation catches and calls `notify_error(e)` from
`theme/notify.py`. Prefer routing new toasts through `notify_error` where the
source is an exception — it already handles the long-message case.

**Tenant scoping.** `require_tenant_id()` raises when no tenant is in scope, and
these routes are bare `@ui.page`s that can run *without* one (the platform-host
handoff legs). Read that as the constraint it is: a bare route may not perform a
tenant-scoped read. `record_player_link` writes to the global `User` row, which
is why it works there at all.

**Audit.** Link and unlink already write audit rows through
`AuditService.write_log`. Keep that; do not convert them to
`write_and_publish` (see the design decision above).

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`. Capture
`context.client` before any background task that notifies. `ui.notify` called
during page build (before the client connects) *is* delivered — the outbox
buffers it — which is what makes wave 2's drain-at-frame approach work.

**Docs.** Identity linking has no feature doc of its own. The behaviour these
waves change should end up in
[`docs/reference/authentication.md`](../../reference/authentication.md) (the link
flows and the handoff) and
[`docs/features/multitenancy.md`](../../features/multitenancy.md) (the
custom-domain handoff), with the dev recipe in
[`docs/development.md`](../../development.md). Each wave names its own.

## Verification loop

```bash
bash scripts/setup_env.sh                      # once
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/<slug>/login`: `player_one`…`player_four`,
`staff_user`, `proctor_user`. Pages live under `/t/default/…`. Chromium is at
`/opt/pw-browsers` — **never run `playwright install`**. `scripts/ui_smoke.js` is
a config-driven harness; read its header comment.

**Wave 1 changes this loop** — after it, `./start.sh mock` (or a
`setup_env.sh`-written `.env`) has all three provider mocks on and the Profile
page actually shows a Connected accounts card. Every later wave verifies through
that.

The surfaces these waves touch, at **1500px and 430px**:

- `/t/default/home/profile` as `player_one` (linked) and `player_three`
  (unlinked) — the Connected accounts card
- `/t/default/twitch/oauth/callback` and `/t/default/racetime/oauth/callback`
  hit with no query string, signed in — the codeless-callback path
- `/t/default/challonge/oauth/callback` as a non-admin — the wrong-door path
- `/oauth/link/claim?token=nope`, signed in and signed out

```bash
poetry run pytest                    # whole suite, parallel
poetry run pytest -n0 -k oauth_link  # serial, for -s / pdb
scripts/ui_flag_sweep.sh             # flags-off sweep
```

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why.
4. The affected surfaces render at both widths, verified by screenshot, with no
   new console errors.
5. Docs named in the task updated.
6. Committed with a message describing the behaviour change, not the diff.

**Tag every claim in a wave's verification write-up `measured` or `code-read`,**
the way the input audit does. Wave 1 exists so that most of them can be
`measured`; silently mixing the two is what made F4 and F5 unfixable as written.

If a task turns out to be wrong or blocked, **finish the rest of its wave and
say explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each wave
file as its wave merges; when the last lands, delete this directory, remove its
row from the "Work in flight" table, delete
[`docs/reviews/identity-linking-ux.md`](../../reviews/identity-linking-ux.md) and
its row in [`docs/reviews/README.md`](../../reviews/README.md), and make sure the
behaviour lives in the docs named above. Git history holds the rationale.
