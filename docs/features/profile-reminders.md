# Profile reminders

A community's STAFF pick profile items every member should have done (Challonge
linked, pronouns set, ...). A signed-in member missing one sees a red banner at
the top of every framed page until they complete it or, if the rule allows,
dismiss it. Not behind a feature flag: a community with no rules shows no banner.

## Pieces

| Piece | Where | Notes |
|---|---|---|
| Rule catalogue | `CHECKS` in [`profile_nudge_service.py`](../../application/services/profile_nudge_service.py) | One `ProfileCheckSpec` per `ProfileCheck`: staff label, banner prompt, button label, the Profile card that fixes it (`ProfileSection`), and an `is_met(user)` predicate |
| Rules | `Tenant.config['profile_nudges']` | `{'rules': [{'check', 'dismissible', 'note'}]}`. Read totally (`_clean_rules` drops unknown/duplicate checks), written by `ProfileNudgeService.set_rules` (STAFF, audited `profile_nudges.updated`) |
| Dismissals | `ProfileNudgeDismissal` | One row per tenant × user × check; audited `profile_nudge.dismissed`. Kept when a rule is switched off, so re-enabling does not re-nag; ignored while a rule is mandatory |
| Admin tab | Admin → Community → **Profile Reminders** ([`admin_profile_reminders.py`](../../pages/admin_tabs/admin_profile_reminders.py)) | Tick a check, choose whether members may dismiss it, add an optional note shown on the banner |
| Banner | [`theme/profile_nudge_banner.py`](../../theme/profile_nudge_banner.py), drawn by `BaseLayout.render` | Only for members, never on chromeless pages. A lookup failure logs and draws nothing |
| Deep link | `/home/profile?focus=<section>` | The Profile tab scrolls to and outlines the card with id `profile-<section>` (`personal`, `connected-accounts`, `matcherino`) |

## Checks and when they apply

A configured rule only shows where a member could actually do it here; otherwise
it goes quiet rather than linking to a control that isn't rendered.

| Check | Met when | Applies when |
|---|---|---|
| `challonge` | `User.challonge_user_id` set | `CHALLONGE` flag live and the integration configured |
| `twitch` | `User.twitch_user_id` set | Twitch integration configured |
| `racetime` | `User.racetime_user_id` set | racetime integration configured |
| `pronouns` | `User.pronouns` non-blank | always |
| `timezone` | `User.timezone` set | the community follows each member's clock (`MODE_USER`) |
| `matcherino` | `User.matcherino_username` non-blank | `PAYOUTS` flag live |

Adding a check: a `ProfileCheck` member, a `ProfileCheckSpec` in `CHECKS`, its
availability in `unavailable_reasons`, and an `id` on the Profile card it points at.

## Cost

`pending_for` runs on every framed page build: one tenant read when the community
has no rules, plus the feature-flag/timezone reads (both request-cached) and one
dismissal query only when the viewer has an unmet rule.
