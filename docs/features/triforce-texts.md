# Triforce Texts

Player-submitted end-game triforce-screen lines for ALTTPR (ported from
sahasrahbot), moderated by staff and baked into the generated seed. Gated by
[`FeatureFlag.TRIFORCE_TEXTS`](feature-flags.md), enforced with `@requires_feature`
on every entry method of `TriforceTextService` (submit, the list reads, moderate,
delete); the two text-picking helpers (`get_balanced_text` / `get_random_text`) are
seed-roll integration points and carry no guard.

Neither surface is its own route. Submission is a **Triforce Texts** button on
each supporting tournament's card on the home **Tournaments** tab, opening a
dialog ([`pages/home_tabs/triforce_texts.py`](../../pages/home_tabs/triforce_texts.py);
the old standalone home tab is gone, and `/home/triforce-texts` is now an alias for
Tournaments). Moderation is the admin **Triforce Texts** tab
([`pages/admin_tabs/triforce_texts.py`](../../pages/admin_tabs/triforce_texts.py)),
shown to staff and tournament admins. REST exposes the same service at
`/api/triforce-texts` (`GET /mine`, `GET`, `POST`, `POST /{id}/moderate`,
`DELETE /{id}`), gated by `require_feature` on the router mount.
Logic lives in
[`triforce_text_service.py`](../../application/services/triforce_text_service.py)
over `TriforceText` (in [`models/tournament.py`](../../models/tournament.py)).

## Behaviour

- **`approved` is tri-state**: `None` pending, `True` approved, `False` rejected —
  with `approved_by` / `approved_at` recording the moderator. One method covers
  both outcomes: `moderate(text_id, approved, actor)`.
- **Per tournament.** Each row belongs to a `Tournament`; the button appears only
  on tournaments whose seed generator supports texts
  (`SeedGenerationService.supports_triforce_texts`) and that are active
  (`list_supporting_tournaments`). Admins see every submission, filterable by
  tournament.
- **Submitting is a paid option.** `AuthService.can_submit_triforce_text` requires
  the `TRIFORCE_SUBMITTER` role (staff override) on top of those two tournament
  conditions, and `submit()` re-checks it rather than trusting the dialog. A
  viewer without the role sees the tournament's `triforce_access_message` (set in
  the tournament editor, rendered as plain text) or a default "paid option" line.
- **Exactly three lines, ≤19 characters each**, matched against the allowed
  character set (`TEXT_LINE_REGEX`: letters, digits, space, basic punctuation,
  arrows, hiragana/katakana), at least one non-blank — enforced in `submit()`.
- Moderating and deleting are Staff or tournament-admin only and audited
  (`triforce_text.submitted` / `.approved` / `.rejected` / `.deleted`, audit only,
  no events); delete is confirmation-gated in the UI.

**See also:** [seed-generation.md](../reference/seed-generation.md) — how approved
texts reach the ALTTPR seed.
