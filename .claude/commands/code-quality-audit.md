---
description: Run a whole-codebase DRY & engineering-practices audit — fan-out reviewers, adversarial reconciliation, a report in docs/reviews/, leverage-ordered remediation waves.
---

Audit the codebase for quality drift — DRY violations, convention divergence,
correctness bugs the drift exposes — using the process that produced
[docs/reviews/2026-07-code-quality-audit.md](../../docs/reviews/2026-07-code-quality-audit.md)
(read it first: it is the reference for structure, tone, and rigor).

This is a **report-only** command: no code changes. Remediation is delegated to
follow-up work, ordered by leverage at the end of the report.

## 1. Frame the audit

- Record the audited commit (`git rev-parse HEAD`) and, if a delta window
  matters (e.g. "the last month's work"), the commit range and its size.
- Scope is the whole codebase; findings are labelled **[new]** (inside the
  window) or **[pre-existing]**.

## 2. Fan out per-section reviewers

Launch parallel subagent reviewers, one per section, each producing findings
with a `file:line` citation, a severity, an age label, and a **one-line
suggested fix** (not implemented):

- services / repositories / utilities (DRY across the application layer)
- API layer (routers, schemas, dependencies; include a "clean bill" check on
  the forbidden-import and reach-through rules)
- presentation (`pages/`, `theme/`, `discordbot/`; NiceGUI anti-patterns get a
  clean-bill check too)
- tests (fixture duplication, hazards like network calls or leaked global
  state, coverage holes)
- engineering practice (error-handling conventions, naming drift, dead code,
  config/magic values, doc drift, module-size watch)

Reviewers must also collect **positives worth preserving** — the shared
helpers and drift guards remediation must not refactor away.

## 3. Adversarial reconciliation

Re-verify every citation, count, and quantitative claim against HEAD
(`ripgrep` the numbers — do not trust the reviewers). Any finding a reviewer
wants to downgrade goes to an **independent re-checker instructed to defend
the original**; only findings that lose that exchange are dropped. Corrections
are made in place with an explicit `_[Reconciled: …]_` note, and the
reconciliation section at the top summarizes: findings retracted, corrected,
and confirmed.

## 4. Write the report

`docs/reviews/YYYY-MM-<topic>.md`, indexed from
[docs/README.md](../../docs/README.md) § Reviews. Structure (mirror the
2026-07 report):

1. header: date, audited commit, scope, status, reconciliation summary
2. executive summary table (theme / severity / age / where)
3. the top-N extractions that remove the most debt
4. findings grouped by theme, ranked by severity, every one with `file:line`
5. cross-cutting themes and a **leverage-ordered remediation list** (debt
   removed per unit of effort, safest first)
6. positives worth preserving

## 5. Close the loop

- Recurring **mechanically-detectable** classes feed `/guardrail-audit`: add a
  hook (or a ratchet test like `tests/test_leak_test_coverage.py`) so the
  class cannot recur, with the extracted shared primitive named in the block
  message — `check_dry_regressions.py` is the model.
- Judgment-level recurring classes go into
  `.claude/agents/architecture-reviewer.md` instead.
- Remediation itself lands as separate leverage-ordered waves (see PRs
  #100/#101), each wave leaving the tree green.
