# PR 2 — Racetime identity linking (OAuth)

> Feature 5 prerequisite. Roadmap phase 2. Small, self-contained; mirrors the
> existing Twitch/Challonge identity links almost exactly.

**Goal:** a user links their racetime.gg identity to their global `User`, so race
results attribute cleanly and auto-open eligibility can be checked.

**Depends on:** PR 0 (light). **Unblocks:** PR 6 (result attribution / eligibility),
PR 10 (live races).

## Deliverables

- **`User` fields** (global, identity-only): `racetime_user_id` (unique, nullable),
  `racetime_username` (cached), `racetime_linked_at`; migration. Token is used once
  during linking and **discarded** — no `access_token` stored (match the Twitch link).
- **`pages/racetime_oauth.py`**: one-time racetime OAuth (read identity scope),
  mirroring `pages/challonge_oauth.py`. Verify server-side; never trust a
  client-supplied id (the [`DiscordLinkService`](../../../application/services/discord_link_service.py)
  discipline from `main`).
- **Profile UI**: link / unlink, with the linked handle shown (mirror the Twitch/
  Challonge profile controls).
- **`MOCK_RACETIME` (identity half)**: a mock client that records a fake verified
  racetime identity, mirroring `MockTwitchClient`; refused under
  `ENVIRONMENT=production` like other mock flags.
- **Env**: racetime OAuth client id/secret + redirect URL (distinct from the bot
  credentials in PR 3 — call them out separately). Add to `.env.example` +
  [deployment.md](../../deployment.md).
- **Docs**: [reference/authentication.md](../../reference/authentication.md) +
  [data-model.md](../../reference/data-model.md) `User` section.

## Decisions that apply

Racetime is the third verified-identity link (identity only, token discarded);
verified-linking discipline from `DiscordLinkService`.

## Reference implementations

- **sahabot2**: `models/user.py` (`racetime_id` / `racetime_name` + OAuth token
  fields — note sglman does **not** persist the token).
- **sglman**: `pages/challonge_oauth.py`, the Twitch linking flow + `User.twitch_*`
  fields, `application/utils/` mock flags (`MockTwitchClient`).

## Acceptance criteria

- A user completes racetime OAuth and `User.racetime_user_id` is set; unlink clears
  it. Under `MOCK_RACETIME`, linking works with no real OAuth. Verify via
  `ui-validation`.
- Uniqueness holds (one racetime id → one user).

## Out of scope

The bot connection and room lifecycle (PR 3/4/6). This PR is identity only.
