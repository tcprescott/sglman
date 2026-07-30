# Wave 1 — make the flow drivable

**Read [README.md](README.md) first.**

Nothing in this wave changes what a production user sees. It changes what a
developer can *see fail*, which is the precondition for waves 2–4 being measured
rather than reasoned about. The audit that produced this plan had to tag five of
its findings `code-read` and gave up on two entirely — not because the tooling
was missing, but because nobody switched it on.

| Task | Touches | Size |
|---|---|---|
| T1.1 | `scripts/setup_env.sh`, `start.sh` — turn the three provider mocks on | small |
| T1.2 | `scripts/seed_dev.py`, `scripts/seed_online.py` — the link states a dev needs | small |
| T1.3 | `docs/development.md` — the recipe, including how to force each failure | small |
| T1.4 | `pages/_oauth_link.py`, `pages/challonge_oauth.py` — make the cross-host handoff reachable under mock | medium |

T1.1–T1.3 are one commit. T1.4 is its own commit and carries the wave's only
risk; read its "If you drop this task" note before starting it.

---

## What already exists (do not rebuild it)

Confirm this before writing anything — the temptation in this wave is to build a
mock layer that is already there.

| Provider | Switch | Mock client | Canned identities |
|---|---|---|---|
| racetime.gg | `MOCK_RACETIME` | `MockRacetimeClient` | `mockrt0001`…`mockrt0004` / `MockRacerOne`…`Four` |
| Twitch | `MOCK_TWITCH` | `MockTwitchClient` | four, same shape |
| Challonge | `MOCK_CHALLONGE` | `MockChallongeClient` | `1001`…`1004` / `mockone`…`mockfour` |

Each mock client's `get_me` reads `MOCK_<PROVIDER>_IDENTITY` (default `1`) and
returns that entry, so which identity the next link binds to is a process-level
choice. Each `is_mock_*()` helper raises `RuntimeError` when
`ENVIRONMENT=production`. Each service's `is_configured()` returns `True` under
its mock, which is what makes the Connected accounts card appear.

`MOCK_RACETIME` also appears in the racetime *bot* runtime, but that runtime is
separately gated by `RACETIME_BOT_ENABLED` (off by default), so turning the mock
on does not start a bot. Verify that when you test T1.1 — a bot connection
attempt in `/tmp/app.log` means something else is wrong.

---

## T1.1 — Switch the mocks on in the dev environment

Two files, and they are inconsistent with each other today: `setup_env.sh` writes
`MOCK_DISCORD` + `MOCK_SEEDGEN` into a fresh `.env`; `start.sh mock` exports
`MOCK_DISCORD` + `MOCK_CHALLONGE` + `MOCK_SEEDGEN`. Neither covers racetime or
Twitch, and the two disagree about Challonge.

- **`scripts/setup_env.sh`** — add `MOCK_RACETIME=true`, `MOCK_TWITCH=true`,
  `MOCK_CHALLONGE=true` to the heredoc that writes `.env`, and update both the
  header comment (line ~13) and the `say` line (~80) that enumerate what goes in
  it. Do **not** touch the `else` branch: an existing `.env` stays untouched by
  design, so say in T1.3's docs that an existing dev environment needs the three
  lines added by hand (or `./start.sh mock`).
- **`start.sh`** — add the two missing exports to the `mock` branch and update its
  `echo` so the mode announces what it actually mocks.
- **`README.md`** (repo root, line ~56) enumerates the mock flags. Update it.

**Verify (`measured`):** boot, log in as `player_three`, open
`/t/default/home/profile`. A **Connected accounts** card must now be present with
three rows — Challonge, Twitch, racetime.gg. Screenshot it at 1500px and 430px;
this is the baseline waves 2 and 4 are measured against, and it is a surface no
screenshot in this repo has ever captured. Click **Link** on racetime.gg: it must
return to Profile showing *"Linked as MockRacerOne"*.

---

## T1.2 — Seed the link states a developer needs

`scripts/seed_online.py::link_racetime_identities` links `player_one` and
`player_two` to racetime (`aBcDeFg1` / `hIjKlMn2`), and
`scripts/seed_challonge.py` links the same two to Challonge (`cu_1001` /
`cu_1002`). **No seeded user has a Twitch link at all**, and no seeded state
produces the already-linked collision.

Add, keeping every write idempotent (`get_or_create` / `if … is None`) and the
users tenant-agnostic (identity is global — `User` has no tenant FK, and these
seeds already respect that):

1. **A Twitch link on `player_one`.** The natural home is a
   `link_twitch_identities` beside `link_racetime_identities` in
   `scripts/seed_online.py`, called from `seed_dev.py` next to it. Use ids that
   cannot collide with the mock client's canned set, the way the racetime seed
   already does — that non-collision is deliberate, so a linked seeded user
   clicking **Link** rebinds rather than erroring.
2. **`player_three` and `player_four` linked to nothing.** Assert it rather than
   assume it: they are the fixtures every link probe starts from, and a later
   seed change that links them silently removes the only unlinked user.

Do **not** seed a pre-made collision. The collision is *producible* and that is
better than fixture state: with `MOCK_RACETIME_IDENTITY` at its default, link
`player_three` (binds `mockrt0001`) and then `player_four` (tries the same id) —
the second attempt is the collision. Document that in T1.3 instead of encoding it
in the seed, where it would just be two users who cannot both link.

**Verify (`measured`):** after `seed_dev.py`, `player_one`'s Profile shows all
three providers linked and `player_three`'s shows none. Then run the two-user
racetime sequence above and capture what the second user is told — verbatim,
because wave 3 needs that string as its racetime baseline.

---

## T1.3 — Write the recipe down

`docs/development.md` is where the mock loop lives. Add a short subsection under
it covering:

- the three switches and what each one makes appear;
- `MOCK_<PROVIDER>_IDENTITY` and its four canned identities per provider;
- **how to force each failure without provider credentials**, which is the part
  that has never been written down and the part waves 2–4 verify against:

  | Failure | How to reach it |
  |---|---|
  | Consent denied / codeless callback | open `/t/default/racetime/oauth/callback` with no query string, signed in |
  | State mismatch | open the same route with `?code=x&state=wrong` |
  | Already linked to someone else | two users link at the same `MOCK_*_IDENTITY` (T1.2) |
  | Wrong door (Challonge) | open `/t/default/challonge/oauth/callback` as a non-admin |
  | Stale / replayed claim | open `/oauth/link/claim?token=nope` |

- the caveat that mock mode **short-circuits the OAuth round trip entirely** —
  `is_mock()` is checked in the `/…/link` page and the link is recorded on the
  spot — so the mocks prove the happy path and the section states, and the table
  above is how the failure paths are reached instead.

Keep it a table plus a few lines, per the docs conventions: prose that restates
code is what rots.

---

## T1.4 — Make the cross-host handoff reachable under mock

**Depends on:** T1.1.

This is the audit's F5 — the riskiest path in the flow, with no measured coverage
and no browser-drivable route to one. The blocker is an ordering, not a missing
capability. In both `register_identity_link_pages`'s `link` page and
`challonge_oauth.challonge_link`, the mock branch is tested **before**
`maybe_start_link_handoff`:

```python
if flow.is_mock():          # ← returns here, so …
    …record the link…
    return RedirectResponse(...)
handoff = await maybe_start_link_handoff(...)   # ← never runs under mock
```

So the entire handoff — start leg, platform-host callback, mint, claim, browser
binding — is unreachable in the one environment that can be driven.

**The change, in two parts:**

1. **Try the handoff before the mock short-circuit** in both link pages.
   `maybe_start_link_handoff` already returns `None` unless host mode *and*
   `HOST_OAUTH_MODE=handoff` *and* the tenant has a domain, so path-mode dev and
   every current production deployment are unaffected — a fact worth a test of
   its own rather than a comment.
2. **Give the start leg a mock exit.** With the reorder, `/oauth/link/start`
   would redirect to `provider.authorize_url(state)` — a real provider URL that
   cannot answer under mock. Add `is_mock` and the provider's callback path to
   `LinkHandoffProvider` (both are available at registration: `flow.is_mock` /
   `flow.callback_route`, and `is_mock_challonge` /
   `'/challonge/oauth/callback'`), and when the provider is mocked have the start
   leg redirect to its own callback on the platform host with `?code=mock&state=`
   the state it just stored. Everything downstream then runs for real:
   `handle_link_handoff_callback` matches the state, calls the mock `exchange`,
   mints a genuine host-bound single-use token, and hands back to the target
   domain's `/oauth/link/claim`.

**What this must not do.** It adds one branch to the *start* leg. It must not
touch `handoff_service.claim`, `_bind_matches`, `_pop_link_handoff_keys`, or any
accept/reject decision — the token minted under mock is a real token and must be
validated by the real code. A diff that relaxes validation to make the mock work
has broken the thing it was meant to test; stop and ask.

**The production guard is the test.** `is_mock_*()` raises under
`ENVIRONMENT=production`, so the branch is unreachable there — assert that
directly rather than trusting it:

```python
def test_link_start_never_self_redirects_in_production()
def test_maybe_start_link_handoff_is_none_in_path_mode()
def test_link_page_prefers_handoff_over_mock_on_a_custom_domain()
```

Extend `tests/test_link_handoff.py`; it already has the `link` fixture,
`_secret_and_reset`, and the URL-builder and `_bind_matches` coverage these build
on.

**The two-host dev recipe** goes in `docs/development.md` beside T1.3, and needs
no `/etc/hosts` edit: `*.localtest.me` resolves to `127.0.0.1`. Set
`PLATFORM_HOST=platform.localtest.me:8000`, `HOST_OAUTH_MODE=handoff`, give the
`default` tenant `domain=tenant.localtest.me:8000`, and drive
`http://tenant.localtest.me:8000/t/…`. Confirm the tenant's `domain` value and
`is_active` match what `TenantService.get_by_domain` and
`normalize_hostname` expect — the start leg allow-lists the target host against
active tenant domains and silently redirects to `/` when it does not match, which
is the first thing to check if the flow dead-ends.

**If you drop this task:** say so explicitly, and note in wave 2's write-up that
its claim-route changes are verified by pytest only. Waves 2–4 do not depend on
it — every finding they fix is reachable through the T1.3 table on a single host.
It is here because the handoff is the one part of this flow nobody has ever
watched work.

---

## Verify

`poetry run pytest` green, plus the flags-off sweep (`scripts/ui_flag_sweep.sh`)
— the Challonge row is flag-gated and must still vanish when `CHALLONGE` is off,
mock or not.

Then, at 1500px **and** 430px, screenshot and read back:

- `/t/default/home/profile` as `player_three` — three unlinked rows
- the same as `player_one` — three linked rows, each naming its account
- one full link and one full unlink, mock mode, captured end to end

Commit T1.1–T1.3 as *"Turn the provider mocks on so account linking can be
driven in dev"* and T1.4 as *"Let the cross-host link handoff run under mock"*.
