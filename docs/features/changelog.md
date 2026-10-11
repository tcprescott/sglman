# In-App Changelog

A public `/changelog` page, titled **What's new**, listing the bigger changes to
Wizzrobe a week or more at a time, newest first. It is written for the people
who use the app (players, crew, volunteers, community staff), not for
developers, so entries describe what changed for a reader rather than which
module moved.

## Where the content lives

`application/changelog/changelog.md`, beside its loader
(`application/changelog/catalog.py`). Like the help articles it lives inside the
package because `.dockerignore` drops `docs/` and root-level `*.md` from the
image.

Each entry opens with a level-two heading carrying an ISO 8601 date interval and
a title, and runs to the next heading:

```markdown
## 2026-10-05/2026-10-11 Event check-in, race rooms and a Challonge overhaul

- One bullet per change a reader would notice.
```

The interval is plain calendar dates, so no timezone is applied. The page shows
it as `Oct 5 – 11, 2026` (`ChangelogEntry.period`) and anchors the entry at its
start date (`/changelog#2026-10-05`).

The body is parsed by `application.content.parse_blocks` and drawn by
`theme.help.render.render_blocks`, the same closed-vocabulary renderer as
[`/help`](help.md). It never goes near `ui.markdown`.

## Rules the file keeps

`tests/test_changelog.py` enforces the structure, so a malformed entry fails CI
rather than vanishing from the page:

- every `## ` line is a well-formed entry heading, and nothing precedes the first;
- entries are newest first and do not overlap;
- every entry starts on a Monday and ends on a Sunday, which is what keeps the
  page at a week or coarser. Quiet weeks fold into one entry spanning several.

At runtime the parser is forgiving instead: a heading it can't read is logged
and that section skipped, so a typo can't take the page down.

## Keeping it current

The rule is in CLAUDE.md under **Changelog**: any PR that changes what a reader
sees or can do adds a bullet to the current week's entry in the same PR. The
[`changelog` skill](../../.claude/skills/changelog/SKILL.md) carries the format,
the wording rules and the git commands for rebuilding missed weeks from merged
PRs, and the PR template has a checklist line for it.

The initial entries (February 2025 to October 2026) were reconstructed from the
merged PRs and commit history.

## The surface

`/changelog` is a `@public_page` in `pages/changelog.py`: it describes the app,
not a community's data, so a signed-out visitor can read it. It has no drawer
item: a **What's new** card at the top of the `/help` index opens it, and the
page links back with "← All help".
