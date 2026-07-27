# Agent guide

**[CLAUDE.md](CLAUDE.md) is canonical.** Read it before writing code — it carries the
three-layer architecture rules, coding conventions, audit/event publishing, timezone
handling, multitenancy scoping, feature flags, authentication, and the NiceGUI
anti-patterns.

Orientation beyond that:

- [docs/README.md](docs/README.md) — documentation index and source-area coverage map
- [docs/architecture.md](docs/architecture.md) — tech stack, process model, directory map
- [docs/development.md](docs/development.md) — local setup, `MOCK_DISCORD`, fixtures, tests

`.claude/` holds the guardrail hooks that reject architecture, audit, and test-fixture
violations at write time; see [`.claude/README.md`](.claude/README.md) for what each
one checks.
