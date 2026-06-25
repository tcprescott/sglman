---
description: Mine this repo's Claude Code session + git history for recurring (AI-generated) bug classes and add mechanical guardrail hooks that prevent them.
---

Audit THIS repository's Claude Code **session history** *and* **git history** to find
recurring bug classes — especially bugs characteristic of AI-generated code — and add
mechanical guardrails (Claude Code hooks) that prevent them, following this repo's
existing hook conventions.

Work **entirely locally**. Treat transcripts as private: they may contain secrets or
tokens — never send them anywhere, and redact anything sensitive you surface.

## 1. Mine two sources

**Session transcripts** — the richest source, because it captures bugs that were
introduced and fixed *within a session* before they ever became a commit (something
`git log` can't show):

- Find the transcript folder for this repo: run `ls ~/.claude/projects/` and pick the
  entry matching this repo — it's the repo's absolute path with `/` (and `.`) turned
  into `-`, e.g. `/home/me/myrepo` → `-home-me-myrepo`. Each file is one session as
  newline-delimited JSON (`.jsonl`); each line is one event.
- Signals that an AI bug was introduced and then chased down:
  - a `tool_result` whose text contains a traceback, `ImportError` /
    `ModuleNotFoundError` / `NameError` / `SyntaxError` / `AttributeError` /
    `TypeError`, a failing test, a linter error, or a **hook exit-2 stderr** message;
  - assistant `Edit`/`Write` tool calls that touch the **same file or lines
    repeatedly** within a session (churn = a bug being hunted);
  - user turns like "that broke", "still failing", "revert that", "wrong", "crash",
    "doesn't start".
- Practical tip: these files are large. Grep for the signal strings first
  (`rg -l 'ImportError|Traceback|SyntaxError' ~/.claude/projects/<folder>/`), then read
  only the surrounding events of each hit.

**Git history** — the durable record: `git log` filtered to commits with
`Co-Authored-By: Claude` / `Claude-Session:` trailers, and `git show <hash>` on each fix
commit to read its root cause (commit bodies here narrate the bug).

## 2. Build a taxonomy

For each bug class you find, record: an example session/commit, the root cause, and
whether an **existing** `.claude/scripts/` hook already covers it (read
`.claude/README.md` for the current guardrails — there are already a dozen). Then split
the classes into:

- **Mechanically detectable** — catchable by a content regex, a whole-file AST check, or
  cross-file import resolution. These are hook candidates.
- **Not mechanical** — domain/business logic, CSS/contrast, external config (OAuth URIs,
  deploy manifests). Note them, but don't force a hook; a bad hook is worse than none.

## 3. Add a guardrail for each uncovered, detectable class

Match this repo's hook conventions **exactly** (study `.claude/README.md` and an
existing script such as `.claude/scripts/enforce_no_orm_writes.py`):

- A **self-contained** script in `.claude/scripts/` that reads the tool JSON from stdin
  and signals via exit code. Re-implement the ~10-line stdin/extract idiom rather than
  sharing a module (independence is intentional).
- **Fail open** (exit 0) on ANY ambiguity: malformed stdin, a missing/empty/non-`.py`
  file, a parse error, or a path under `/.claude/`. Exit **2** with a stderr message in
  the house style (`HEADER in '<file>' (line N): cause … Fix: …`) only on a *real*
  violation.
- Pick the event deliberately:
  - **PreToolUse** — content regex on the incoming fragment, to *block before* the write
    (import rules, banned commands).
  - **PostToolUse** — `ast.parse` the resulting file, for whole-file semantic checks.
  - **Stop** — a whole-repo sweep, for cross-file invariants where the broken file
    isn't the one being edited (e.g. import resolution). Drain stdin; derive the repo
    root with `git rev-parse --show-toplevel`.
- **Low false-positive bias is the cardinal rule.** Before you wire anything up,
  prototype the check and run it over the CURRENT codebase: it must report ~0 false
  positives (a noisy guardrail gets disabled). Also demonstrate it *would* have caught
  the historical bug you're targeting. Report both numbers.
- Do **not** add an external-linter dependency — this repo deliberately uses
  self-contained scripts (see the "Why we did not add ruff" note in `.claude/README.md`).

## 4. Ship

Implement the validated hooks, register each in `.claude/settings.json` under the right
matcher/event, document each under "The guardrails" in `.claude/README.md` (mirroring the
existing entries), and run the README's stdin test snippets to confirm exit 0 on clean
input and exit 2 on the bug pattern. Finish with a short summary: which bug class each new
hook prevents, and the measured false-positive count for each.
