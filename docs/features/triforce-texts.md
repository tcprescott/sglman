# Triforce Texts

Player-submitted end-game triforce-screen lines for ALTTPR (ported from
sahasrahbot), moderated by staff and baked into the generated seed. Gated by
[`FeatureFlag.TRIFORCE_TEXTS`](feature-flags.md), enforced on every public method
of `TriforceTextService`.

Both surfaces are **tabs**, not routes: submission on the "Triforce Texts" home
tab ([`pages/home_tabs/triforce_texts.py`](../../pages/home_tabs/triforce_texts.py),
with inline tournament selection), moderation on the admin tab of the same name
([`pages/admin_tabs/triforce_texts.py`](../../pages/admin_tabs/triforce_texts.py)).
Logic lives in
[`triforce_text_service.py`](../../application/services/triforce_text_service.py)
over `TriforceText` (in [`models/tournament.py`](../../models/tournament.py)).

## Behaviour

- **`approved` is tri-state**: `None` pending, `True` approved, `False` rejected —
  with `approved_by` / `approved_at` recording the moderator. One method covers
  both outcomes: `moderate(text_id, approved, actor)`.
- **Per tournament.** Each row belongs to a `Tournament`; the submission tab lists
  only tournaments whose seed generator supports texts
  (`SeedGenerationService.supports_triforce_texts`) and that are active. Admins
  see every submission, filterable by tournament.
- **Submitting is a paid option.** `AuthService.can_submit_triforce_text` requires
  the `TRIFORCE_SUBMITTER` role (staff override) on top of those two tournament
  conditions, and `submit()` re-checks it rather than trusting the tab.
- **Exactly three lines, ≤19 characters each**, matched against the allowed
  character set, at least one non-blank — enforced in `submit()`.
- Moderating and deleting are Staff or tournament-admin only and audited
  (`triforce_text.*`); delete is confirmation-gated in the UI.

**See also:** [seed-generation.md](../reference/seed-generation.md) — how approved
texts reach the ALTTPR seed.
