---
name: changelog
description: >-
  Add or update the in-app changelog (/changelog, "What's new") for a change
  people will notice. Use before opening a PR that adds a feature, changes a
  workflow or what a role can do, fixes a bug users hit, or closes a security
  hole; also when asked to update the changelog or catch it up from git history.
  Entries are weekly, user-facing, and live in application/changelog/changelog.md.
---

# Keeping the changelog current

`application/changelog/changelog.md` is the "What's new" page. It is read by
players, crew, volunteers and community staff, not by developers. Every PR that
changes what one of them sees or can do adds a line to it in the same PR.

## Does this PR need an entry?

Yes when a reader would notice: a new page, tab, button, DM or integration; a
changed workflow or permission; a bug fix someone hit; a security fix; a rename.

No for refactors, tests, guardrail hooks, CI, docs-only changes, dependency
bumps without a security reason, and fixes to something that never shipped. Say
so in the PR's Checklist instead of adding a line.

## Where the line goes

Entries cover whole weeks, Monday to Sunday, newest first:

```markdown
## 2026-10-05/2026-10-11 Event check-in, race rooms and a Challonge overhaul

- One bullet per change a reader would notice.
- Behind the scenes: optional last bullet for invisible-but-notable work.
```

1. Find the week the PR will merge in (Monday to Sunday, by date).
2. If the top entry already covers that week, add a bullet to it. Merge into an
   existing bullet when it's the same feature. Retitle the entry if its headline
   no longer fits the week's biggest change.
3. If not, add a new entry **above** the current top one. Quiet weeks may be
   merged into one entry spanning several weeks; never split a week into days.

`tests/test_changelog.py` fails the build on a malformed heading, an entry that
doesn't start on a Monday and end on a Sunday, overlapping entries, or entries
out of order.

## How to write a bullet

Follow "Writing user-facing text" in CLAUDE.md. In particular:

- Say what changed for the reader, in their words: "Players can ask staff to
  move a match", not "Add RescheduleRequestService".
- No class names, file paths, PR numbers or flag keys.
- Plain prose, no "**Bold term**: explanation" bullets, no em dashes.
- Name a feature that only some communities have switched on as what it is;
  don't promise it's available everywhere.

The file is parsed by `application/content` (the help renderer): bullets,
paragraphs, `**bold**`, `*italic*`, `` `code` `` and links to `/…` or
`https://…`. Nothing goes before the first `## ` heading.

## Catching up from git history

When the changelog has fallen behind, rebuild the missing weeks from the
merged PRs rather than the raw commits:

```bash
git fetch origin main
git log origin/main --first-parent --merges --since=<last entry end> \
  --format='%ad %s%n  %b' --date=short
# a merge whose body is empty: list the PR's own commits
git log --no-merges --format='  - %s' <merge>^1..<merge>^2
```

Group by ISO week (`--date=format:%G-W%V`), write one entry per week, and fold
weeks with only a commit or two into their neighbour.
