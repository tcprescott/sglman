# Wave 2 — every failure reaches the screen

**Read [README.md](README.md) first. Wave 1 must be merged** — without it the
Connected accounts card does not render in dev and nothing below can be measured.

This wave fixes the audit's two Majors, F1 and F2, which share one mechanism: a
message is written, then thrown away by the navigation that follows it. It adds no
copy — all nine strings already exist. It makes them arrive.

| Task | Touches | Size |
|---|---|---|
| T2.1 | `theme/notice.py` (new) + three drain points | small |
| T2.2 | `pages/_oauth_link.py`, `pages/challonge_oauth.py` — five notify-then-navigate sites | small |
| T2.3 | `/oauth/link/claim` — a mode guard, and return where the user was | medium |
| T2.4 | the cross-host hand-back, which the session stash cannot reach | medium |

T2.1 and T2.2 are one commit; they are meaningless apart. T2.3 and T2.4 are
separate commits.

---

## The mechanism

One carrier, one drain point per frame, no exceptions (see the README's design
decisions). A notice is a *presentation* concern: a service still raises
`ValueError`, and only a page that is about to redirect decides the message must
outlive the redirect.

`ui.notify` enqueues on the current client's outbox; a client that has not
connected yet still receives it when it does. That is what makes drain-at-frame
work — the notice is emitted while the *next* page is being built, before its
websocket is up, and Quasar shows it on connect.

### T2.1 — `theme/notice.py`

A sibling of `theme/notify.py`, same register: a docstring explaining the
convention, two functions, nothing else.

```python
def stash_notice(message: str, *, color: str = 'warning') -> None:
    """Queue a toast for the next page this browser loads.

    For the notify-then-redirect case only: ``ui.notify`` followed by
    ``ui.navigate.to`` loses the toast with the document it was queued against.
    """

def drain_notice() -> None:
    """Show and consume a notice stashed before a redirect. Idempotent."""
```

Store it in `app.storage.user` under one key, single-slot, last-write-wins — a
queue would let two notices pile up across an aborted redirect chain and surface
a stale one later. `drain_notice` pops before notifying, so a re-render cannot
replay it.

**The three drain points.** `/home` is a bare `ui.page`, not a `_tenant_page`, so
the `protected_page` wrapper is *not* a universal drain point — do not put it
there and assume coverage.

| Frame | Where | Covers |
|---|---|---|
| `BaseLayout.render()` (`theme/base.py`) | first line of `render` | `/home/*`, `/admin/*`, `/volunteer/*` — every return path in this flow |
| `render_error_page()` (`theme/error_page.py`) | before the card | a notice must still show on the 403/404 a bad return lands on |
| the login page (`pages/auth.py`, both the real and the mock `@ui.page('/login')`) | after the authenticated-redirect check | *"Please log in and try linking again."* |

Three call sites is the honest cost of NiceGUI's page model here. Say so in the
module docstring so the next person does not go hunting for the one hook that
would have covered everything.

### T2.2 — Convert the five sites

Mechanical. Every `ui.notify(...)` **immediately followed by**
`ui.navigate.to(...)` becomes `stash_notice(...)` with the same message and
colour.

| Site | Strings |
|---|---|
| `_oauth_link._finish_link` | *"{provider} linking was cancelled or failed."*, the `ValueError` text, *"Could not link {provider}…"*, and the success *"{provider} account linked."* |
| `challonge_oauth._finish_player_link` | the same four, Challonge-worded |
| `challonge_oauth._finish_service_connect` | the same four, connect-worded |
| `_oauth_link.link_claim` — expired/used | *"Link session expired or already used. Please try again."* |
| `_oauth_link.link_claim` — wrong browser, not-logged-in, record failure | the other three |

**Convert the success toast too.** *"{provider} account linked."* is queued and
then discarded by the very same redirect — the happy path is silent as well, and
the audit could not see that because it could not reach the happy path. Wave 1
makes it visible; fix it here.

Do not change a single word of any message in this task. Copy changes are wave 3
and wave 4; mixing them in makes it impossible to tell whether a message arrived
because the carrier works or because it was rewritten.

**The one shape that must not change:** where a handler notifies and then keeps
rendering the same page — `_link_section.py`'s `unlink`, which notifies and calls
`row.refresh()` — `ui.notify` is correct and must stay. `stash_notice` is only for
a notify that precedes a navigation.

---

## T2.3 — The claim route: guard the mode, return where the user was

**Depends on:** T2.1.

Two defects, both visible in the audit's F1 probe, and they are not the same bug.

**(a) It answers requests it cannot complete.** `/oauth/link/start` opens with:

```python
if not host_oauth_handoff_enabled():
    return RedirectResponse('/login')
```

`/oauth/link/claim` has no equivalent. In path mode (every current dev
environment, and the audit's probe) it renders, fails to validate a token that
was never minted, and redirects. Add the same guard, and prefer `/` to `/login`
as its target — a signed-in user who hits a route that does not apply to their
deployment is not having an authentication problem.

This is the honest explanation of half of F1's symptom: the community picker the
audit landed on was not a notification bug, it was a route serving a request that
was not addressed to it. Say so in the wave write-up rather than filing it under
the missing toast.

**(b) Its failure exits ignore the return path it computed.** The handler derives
`next_path` from the token payload, then:

- expired/used token → `ui.navigate.to('/home/profile')`
- browser-binding mismatch → `ui.navigate.to('/home/profile')`
- no logged-in user → `ui.navigate.to('/login')`

The first two land on an unprefixed path — correct on a custom domain, wrong
anywhere `/t/<slug>` is in play. Route them through the same `safe_next`-guarded
target the success path uses.

The ordering is the constraint: `next_path` is currently computed *after* the
token check, from the payload, and the expired-token branch has no payload to read
it from. Resolve that explicitly — hoist a default (each
`LinkHandoffProvider.profile_return` is `/home/profile`, so the default is the
same string, but derived rather than hardcoded in three places) and let the
payload override it when there is one. **Keep `safe_next` on every path**; it is
the open-redirect guard and a hoist is exactly the kind of edit that drops it.

The not-logged-in branch keeps `/login` — that one is right — and now stashes its
notice, which the login page drains (T2.1).

**Do not touch** `handoff_service.claim` or `_bind_matches`. Which tokens are
accepted does not change in this task; only what the user is told and where they
land.

---

## T2.4 — The cross-host hand-back

**Depends on:** T2.3. **Measurable only with wave 1's T1.4**; if that was
dropped, verify by pytest and say so.

`handle_link_handoff_callback` runs on the **platform** host. When it gives up —
consent denied, state mismatch, unknown provider, or an exchange that raised — it
does:

```python
ui.navigate.to(_cross_host_url(host, next_path))
```

The user arrives back on their community with nothing said, and this is the one
place the session stash cannot help: the notice would be written into the
*platform host's* session and the user is now on a different origin, whose cookie
never saw it.

**The fix is to keep the hand-back going through one door.** The platform host
already knows how to address the target domain's claim route
(`_link_claim_url`); extend that so a failure hands back to
`/oauth/link/claim?r=<reason>&next=<path>` instead of jumping straight to
`next_path`. The claim route — which by T2.3 already owns "what the user is told
about a handoff that did not complete" — maps the reason to a message, stashes it,
and redirects to `safe_next(next)`. One door, one carrier, and the messages live
next to the ones T2.2 just fixed.

Keep the reason vocabulary small and opaque; it is a URL parameter a user can
edit, so it selects from a fixed dict and an unrecognised value falls back to the
generic message. Two reasons plus a default is enough:

| Reason | Message |
|---|---|
| `denied` | the provider returned an error, no code, or a state mismatch |
| `failed` | `provider.exchange` raised |
| anything else / absent | the existing generic *"Could not link…"* wording |

`next` arrives from the platform host and must go through `safe_next` on the way
in — it crosses a host boundary as a bare query parameter, so treat it exactly as
untrusted as the token path already does.

The one case with no target host (`provider is None or not host`) cannot hand
back at all — there is nowhere to hand back *to*. Leave it as it is; note in the
commit that it is unreachable by a genuine provider redirect, since the markers
it reads are only ever written by `/oauth/link/start`.

---

## Tests

`tests/test_link_handoff.py` is the home for the claim-route work; add a new file
for the notice carrier since it is a `theme/` unit with no handoff involvement.

```python
# tests/theme/test_notice.py
def test_stash_then_drain_emits_one_notification()
def test_drain_is_idempotent()                       # second call emits nothing
def test_drain_with_nothing_stashed_is_a_noop()

# tests/test_link_handoff.py
def test_claim_route_is_disabled_in_path_mode()
def test_claim_failure_returns_to_the_payloads_next_path()
def test_claim_failure_path_is_safe_next_guarded()    # a cross-host `next` is rejected
def test_handoff_failure_hands_back_through_the_claim_route()
def test_unknown_reason_code_falls_back_to_the_generic_message()
```

And the mechanical guard that keeps this wave from being undone — the reason the
bug survived nine written strings in the first place:

```python
def test_no_link_page_notifies_immediately_before_navigating()
```

Scan the source of `pages/_oauth_link.py`, `pages/challonge_oauth.py` and
`pages/auth.py` for a `ui.notify(` line followed (within a couple of lines, past
blanks and comments) by `ui.navigate.to(` or `RedirectResponse(`, and fail with
the file and line. It is a source-text test, which is coarse — say so in its
docstring — but it is the only thing that stops the shape reappearing, and it
covers `pages/auth.py`'s Discord-login callback, which has the identical bug.

**On `pages/auth.py`:** the guard above will fail on it. That is deliberate and it
is a decision to make, not to sidestep. Either convert its three
notify-then-navigate sites in this wave (they are three lines, the drain point is
already there from T2.1, and Discord login is the flow *every* user hits), or
exempt the file with a comment naming the follow-up. Converting is the
recommendation — the README lists auth as out of scope for *findings*, not for a
one-line fix to the same bug — but if you convert it, say so prominently in the
commit message, because it changes behaviour on the login path and that deserves
to be reviewed on purpose rather than found in a diff.

---

## Verify

Every probe below produced **no notification** before this wave; each must now
produce exactly one, and the text must be legible at 430px (the four claim
messages are long enough to test `notify_error`'s multi-line threshold — check
whether they truncate, and route them through `notify_error`'s long-message
handling if they do).

Signed in as `player_three` at 1500px and 430px, tag each `measured`:

| Probe | Expect |
|---|---|
| `/t/default/racetime/oauth/callback` (no query) | *"racetime linking was cancelled or failed."*, lands on Profile **with the `/t/default` prefix intact** |
| `/t/default/twitch/oauth/callback` (no query) | the Twitch equivalent |
| `/t/default/racetime/oauth/callback?code=x&state=wrong` | the same message (state mismatch is indistinguishable to the user, and should be) |
| `/oauth/link/claim?token=nope`, path mode | redirect to `/`, no stack trace, no community picker with a silent failure behind it |
| a successful mock link | *"racetime.gg account linked."* — the happy-path toast that was also being lost |
| a successful mock unlink | *"racetime.gg account unlinked."* — unchanged, still an in-place `ui.notify` |

With `HOST_OAUTH_MODE=handoff` and the two-host recipe (wave 1 T1.4), also drive a
denied handoff and confirm the message crosses the host boundary and the user
lands on their own community.

Commit T2.1+T2.2 as *"Carry link failures through the redirect that was eating
them"*, T2.3 as *"Stop serving the claim route where it cannot work, and return
the user to their community"*, T2.4 as *"Tell the user when a cross-host link was
denied"*.
