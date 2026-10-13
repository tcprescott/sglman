---
name: changelog
description: >-
  Add or update the in-app changelog (/changelog, "What's new") for a change
  people will notice. Use before opening a PR that adds a feature, changes a
  workflow or what a role can do, fixes a bug users hit, or closes a security
  hole; also when asked to update the changelog or catch it up from git history.
  Entries are weekly and user-facing; a PR adds its own file under
  application/changelog/changes/ rather than editing changelog.md.
---

# Keeping the changelog current

`application/changelog/` is the "What's new" page. It is read by players, crew,
volunteers and community staff, not by developers. Every PR that changes what
one of them sees or can do adds a line to it in the same PR, as a file of its
own.

## Does this PR need an entry?

Yes when a reader would notice: a new page, tab, button, DM or integration; a
changed workflow or permission; a bug fix someone hit; a security fix; a rename.

No for refactors, tests, guardrail hooks, CI, docs-only changes, dependency
bumps without a security reason, and fixes to something that never shipped. Say
so in the PR's Checklist instead of adding a line.

## Where the line goes

Add a new file; don't edit `changelog.md`. Every PR merged in a week used to
append to that week's entry, so any two PRs in flight conflicted there.

```
application/changelog/changes/2026-10-13-equipment-help.md
```

```markdown
### New
- Help has a new article on borrowing equipment: scanning a loaner's QR code,
  giving it back, and running the equipment desk.
```

1. Name it `YYYY-MM-DD-<topic>.md`: lowercase, hyphens, a topic no other PR
   will pick (the feature, not "help" or "fix"). The date only has to land in
   the right Monday-to-Sunday week; use today, or the day you expect it to merge
   if that's next week.
2. Bullets under category headings, nothing else: no `## ` heading, no intro
   paragraph. One bullet per change a reader would notice; a big PR may have
   several, under more than one category. The categories, in page order:
   - `### New`: something a reader couldn't do before.
   - `### Improved`: works better, looks different, moved or was renamed.
   - `### Fixed`: a bug someone hit.
   - `### Security`: a hole closed, or private data kept private.
   - `### Behind the scenes`: work a reader only notices indirectly (error
     reporting, dependency bumps with a security reason, speed-ups).

   A bullet that does several things goes under its biggest part. A bullet
   outside a category shows under "More changes" and fails the test.
3. Revising the line later means editing *your* file, never someone else's.

The page folds each file into the `changelog.md` entry covering its date. A week
with no entry there gets one titled **Updates**. If the week deserves a
headline, add a bare heading for it to `changelog.md` with no body
(`## 2026-10-12/2026-10-18 Help for staff`); the files fill it. That one line is
the only edit to `changelog.md` a normal PR ever makes.

Folding a finished week's files into a hand-written entry in `changelog.md` (and
deleting the files) is optional tidying for a dedicated PR. Entries there cover
whole weeks, Monday to Sunday, newest first; quiet weeks may share one entry
spanning several, but never split a week into days.

`tests/test_changelog.py` fails the build on a misnamed change file, one holding
anything but categorized bullets, a malformed heading, an entry that doesn't start on a
Monday and end on a Sunday, overlapping entries, or entries out of order.

## How to write a bullet

Follow "Writing user-facing text" in CLAUDE.md. In particular:

- Say what changed for the reader, in their words: "Players can ask staff to
  move a match", not "Add RescheduleRequestService".
- No class names, file paths, PR numbers or flag keys.
- Plain prose, no "**Bold term**: explanation" bullets, no em dashes.
- Name a feature that only some communities have switched on as what it is;
  don't promise it's available everywhere.

Both are parsed by `application/content` (the help renderer): bullets,
`**bold**`, `*italic*`, `` `code` `` and links to `/…` or `https://…`. In
`changelog.md` nothing goes before the first `## ` heading.

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

Group by ISO week (`--date=format:%G-W%V`), write one entry per week with its
bullets under the same `### ` category headings, and fold weeks with only a
commit or two into their neighbour. A catch-up is the one time
you write entries in `changelog.md` directly: the weeks are over, so no other
PR is adding to them.
