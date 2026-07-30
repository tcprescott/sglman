# Brief — Identity linking UX (Challonge / Twitch / racetime)

Lower priority. Scope, method and leads for an audit nobody has run yet; leads are
unverified suspicions from reading the code.

## Scope

The shared account-linking flow and its three consumers:

- [`pages/_oauth_link.py`](../../../pages/_oauth_link.py) — the 484-line engine:
  provider registration, the cross-host handoff (`link_start` / `link_claim`),
  browser binding, state validation, callback error handling.
- The per-provider callback pages:
  [`challonge_oauth.py`](../../../pages/challonge_oauth.py),
  [`twitch_oauth.py`](../../../pages/twitch_oauth.py),
  [`racetime_oauth.py`](../../../pages/racetime_oauth.py).
- The user-facing sections on Profile:
  [`challonge_link_section.py`](../../../pages/home_tabs/challonge_link_section.py),
  [`twitch_link_section.py`](../../../pages/home_tabs/twitch_link_section.py),
  [`racetime_link_section.py`](../../../pages/home_tabs/racetime_link_section.py),
  over [`_link_section.py`](../../../pages/home_tabs/_link_section.py).
- [`IdentityLinkService`](../../../application/services/identity_link_service.py)
  and `OAuthHandoffService`.

Discord OAuth itself (the login) is out of scope — it is documented in
[reference/authentication.md](../../reference/authentication.md) and exercised by
every other flow.

## Why this one, and why it is not first

The happy paths work in production — people have linked accounts. What has never
been examined is the **failure half**, and this flow has more failure modes than
anything else in the app: a third-party redirect, a cross-host handoff between a
custom domain and the platform host, a browser-binding secret, a one-use token, and
a user who may deny consent at any point. Each already has a `ui.notify` written
for it ([`_oauth_link.py:335-364`](../../../pages/_oauth_link.py#L335)); nobody has
checked whether a person hitting one can recover.

## What to measure

1. **Each provider's link and unlink**, on `/t/<slug>` and (if reachable in dev) on
   a custom-domain tenant. Count interactions, capture copy, and note whether the
   Profile section says what the link *buys* before asking for it — a Challonge link
   auto-enrolls you in brackets, a racetime link is how a race room recognises you,
   a Twitch link drives stream URLs. Verify each claim against the code rather than
   assuming.
2. **Denial.** Deny consent at the provider. `read_callback_code` handles an `error`
   param ([`:112`](../../../pages/_oauth_link.py#L112)); measure what the user ends
   up looking at, and whether they can try again without knowing what went wrong.
3. **Expiry and reuse.** Drive `link_claim` twice with the same token, and once after
   letting it expire — the code has distinct messages for
   "Link session expired or already used" and
   "Link is not valid for this browser". Confirm which fires when, and that neither
   leaves a half-linked state.
4. **Wrong browser.** Start the handoff in one browser context and claim it in
   another; `_bind_matches` should refuse ([`:218`](../../../pages/_oauth_link.py#L218)).
   Verify the refusal and its copy.
5. **Not-logged-in claim.** The flow has a message for it
   ("Please log in and try linking again"); check whether the link survives the
   login round trip or is simply lost.
6. **Already-linked collisions.** Link a provider account that is already attached to
   a different Wizzrobe user, and re-link the same provider to a second account.
   Establish what the service does and whether the message tells the user which
   account holds it.
7. **Unlink consequences.** Unlink Challonge while enrolled in a Challonge-linked
   tournament — [`player_edit_info.py:105-107`](../../../pages/home_tabs/player_edit_info.py#L105)
   deliberately preserves manual enrollments, so check what happens to the
   auto-enrolled ones and whether the user is warned.
8. **Mobile**, since these are redirect chains through third-party pages on a phone.

## Leads to verify

- The handoff exists because a custom-domain tenant cannot receive the provider's
  callback directly. Verify the whole cross-host path in dev, or state clearly that
  it could not be exercised and why — an untestable path is itself a finding.
- Check whether a failed link leaves rows behind (a pending handoff, a partial
  `IdentityLink`) that a retry then trips over.
- Check the signed-out and wrong-tenant cases for the callback pages: they are
  `@public_page`-ish entry points reached from outside, so they need to tolerate no
  session.
- Look for provider errors that reach the user as raw text from the third party.

## Fixtures and roles

`MOCK_DISCORD` mocks Discord only — the three providers here are real OAuth. Work
out per provider whether dev credentials exist (`docs/deployment.md` has the
env-var table) and, where they do not, drive as far as the redirect and audit the
rest by reading. Say which findings are code-read rather than measured; the two
completed audits are measured throughout, and mixing the two without labelling
them would be the one way to make this report untrustworthy.

## Deliverable

`docs/reviews/identity-linking-ux.md`, with every finding marked **measured** or
**code-read**.
