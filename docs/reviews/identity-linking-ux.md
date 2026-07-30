# Identity linking UX (Challonge / Twitch / racetime) — evaluation

**Scope:** the shared account-linking engine
([`pages/_oauth_link.py`](../../pages/_oauth_link.py)), its three provider
sections on Profile
([`racetime_link_section.py`](../../pages/home_tabs/racetime_link_section.py),
[`twitch_link_section.py`](../../pages/home_tabs/twitch_link_section.py),
[`challonge_link_section.py`](../../pages/home_tabs/challonge_link_section.py) over
[`_link_section.py`](../../pages/home_tabs/_link_section.py)), the callback pages,
and `IdentityLinkService` / `OAuthHandoffService`. Discord login itself is out of
scope.

**Method:** the three providers are **real OAuth** and this environment has no
credentials for any of them (`.env` carries only DB, storage, `MOCK_DISCORD`,
`MOCK_SEEDGEN`), so the happy path cannot be driven here. What *was* measured is
the state every fresh deployment starts in plus the failure entry points that need
no provider: the Profile page with no provider configured, each callback page hit
without a code, and the cross-host claim route with a bad token. Everything else is
read from the code. **Every finding below is tagged `measured` or `code-read`** —
mixing the two silently would make this report untrustworthy.

**Headline:** the configuration gate is right — a provider with no credentials is
hidden rather than offered, which is the opposite of the dead-dropdown pattern
found elsewhere in this app. The failure paths are where it thins out: the engine
contains four distinct, well-written failure messages and **none of them reached
the screen** in any probe. A stale claim link lands the user on the community
picker with nothing said, and a callback hit without a code silently renders
Profile as though nothing happened.

---

## What is measured

| Probe | Result |
|---|---|
| Profile with no provider configured | **No connected-accounts section at all.** Page = Personal information, Notifications, Tournament enrollment, API tokens; 1,854 px. No Challonge/Twitch/racetime UI anywhere |
| `/t/default/twitch/oauth/callback` with no code | HTTP 200 → **renders Profile silently**, no notification |
| `/t/default/racetime/oauth/callback` with no code | HTTP 200 → **renders Profile silently**, no notification |
| `/t/default/challonge/oauth/callback` as a non-admin | HTTP 200 → **the admin 403 page**: *"You don't have permission to view the admin area."* |
| `/oauth/link/claim?token=nope`, signed in | HTTP 200 → redirected to `/home/profile` **on the platform host**, which renders the **community picker**. No notification |
| same, signed out | identical — community picker, no notification |
| `/oauth/link/start` (no params) | HTTP 307 |

The hiding behaviour is deliberate and documented: each section's docstring says
`render_connected_accounts_section` *"hides any provider whose integration isn't
configured"*, and each provider is a small `LinkSectionConfig` declaring its title,
description, route, labels and service factory.

---

## Findings, ranked

### F1 — Major · `measured` · Four written failure messages, none of which arrive

The engine has specific copy for each way a link can fail
([`_oauth_link.py:335-364`](../../pages/_oauth_link.py#L335)):

- *"Link session expired or already used. Please try again."*
- *"Link is not valid for this browser. Please try again."*
- *"Please log in and try linking again."*
- *"Could not link {provider}. Please try again."*

Probed with an invalid claim token — the exact shape of a stale link, a second
click, or a back-button retry — the page issued **no notification at all** and
redirected to `/home/profile` on the platform host, where the route falls through
to the **community picker**. A user who was on their Profile in a community ends up
choosing a community, with no idea the link failed. The likely mechanism (`code-read`)
is that `ui.notify` is followed by a navigation that discards it; the fix shape is a
message that survives the redirect (a query flag the landing page renders, or
landing on the tenant Profile rather than the platform host).

### F2 — Major · `measured` · A callback hit without a code silently renders Profile

`read_callback_code` logs an `error` param and returns nothing
([`:104-115`](../../pages/_oauth_link.py#L104)); the Twitch and racetime callback
pages then render the profile as if the user had simply navigated there. Probed
directly: HTTP 200, Profile, no message. So the two most ordinary real-world
failures — the user denies consent at the provider, or a callback is replayed —
look exactly like success-with-nothing-linked. The log knows; the screen does not.

### F3 — Minor · `measured` · Challonge's callback answers a player with an admin refusal

`/challonge/oauth/callback` rendered *"403 Forbidden — You don't have permission to
view the admin area."* for a plain user. Challonge has both a service-level
(admin) connection and a player-level identity link, and the two callbacks are
different routes — but a player who lands on the wrong one is told they lack admin
permission, which is true and useless. It reads as "linking is staff-only", which
is wrong.

### F4 — Minor · `code-read` · Unlinking Challonge silently changes tournament enrolment

Profile's enrolment section deliberately preserves manual enrolments and carries
Challonge-managed ones separately
([`player_edit_info.py:105-107`](../../pages/home_tabs/player_edit_info.py#L105), and
the page states *"Challonge-linked tournaments enroll you automatically from the
bracket"*). The unlink control's own copy is just
`{provider} account unlinked.` — nothing warns that the auto-enrolments it created
are affected, and nothing says what happens to a bracket the user is mid-way
through. Not driven (no credentials), so the actual post-unlink state is unverified.

### F5 — Minor · `code-read` · The cross-host handoff cannot be exercised in dev, and that is itself worth recording

The handoff exists because a custom-domain tenant cannot receive the provider
callback directly: `maybe_start_link_handoff` redirects to the platform host's
`/oauth/link/start`, the provider callback runs there, and the verified identity is
handed back to the tenant host's `/oauth/link/claim` with a one-use token bound to
the browser (`_bind_matches`, [`:218-231`](../../pages/_oauth_link.py#L218)). The
reasoning is careful — there is even a comment explaining why stale markers from a
handoff abandoned at the consent screen must be dropped rather than reused. None of
it can be tested without a second host and real credentials, so the riskiest path in
the flow has no measured coverage and no automated test. A dev recipe (a second
hostname pointing at the same app, plus one provider's sandbox credentials) would be
worth more than any UI change listed here.

---

## What works

- **Unconfigured providers are hidden, not offered.** Measured: with no
  credentials, the Profile page shows no linking UI at all. Compare
  [match-operations-ux F4](match-operations-ux.md#f4--critical--two-thirds-of-the-tournament-dropdown-cannot-be-scheduled-and-you-find-out-after-submitting),
  where a dropdown offers ten tournaments and six cannot work — this surface got
  the same problem right.
- **One engine, three thin providers.** Each provider is a declarative
  `LinkSectionConfig`; the OAuth mechanics, state validation, browser binding and
  handoff live once in `_oauth_link.py`.
- **Each provider says what the link buys** — *"Link your racetime.gg account so we
  can attribute your race results and check auto-open eligibility."* That sentence
  is at the point of decision, which is where the
  [bracket audit](bracket-creation-ux.md) noted most of this app's explanations are
  *not*.
- **The security reasoning is explicit** — one-use token, browser binding,
  state-mismatch handling, and the stale-marker drop, each with a comment saying
  why.
- **Enrolment respects the boundary** between Challonge-managed and manual
  registrations rather than overwriting one with the other.

## Not covered

Everything requiring provider credentials: the happy path, consent denial at the
provider, expiry and reuse of a live token, wrong-browser claims, already-linked
collisions, and the custom-domain handoff end to end. All five are the audit this
report cannot be until a dev credential path exists (F5).
