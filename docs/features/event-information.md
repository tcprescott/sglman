# Event Information

A per-community handbook at `/event-info`, public and flag-gated. Where
[`/help`](help.md) documents **the app** — identical for every community — this
documents **one community's event**: what is on and when, what happens when you
sit down to play, and who to find when something needs a decision.

Behind `FeatureFlag.EVENT_INFO`, which **ships dark**. Only communities a
super-admin grants it on `/platform` have the section at all.

## Why it is separate from help

Help is written from the source: it describes controls that exist and states the
code produces, and it goes stale only when the code changes. The player and
proctor articles were the exception — they also carried **room procedure the code
does not encode**, which came from the community and goes stale on the event's
clock, not the repo's. That content is now here, where it belongs.

The split is worth stating plainly, because it decides where a new paragraph
goes:

| | Help | Event Information |
|---|---|---|
| Answers | "how does this app work?" | "what about *this* event?" |
| True for | every community | one community |
| Goes stale when | the code changes | the event changes |
| Example | the six steps to run a match on the Proctor Station | who the on-call admin is, and that you fetch them in person |

Two help articles were trimmed when this landed: `player.md` lost check-in, the
tournament room, stages, what to do when something breaks and turnover;
`proctor.md` lost looking after the room, game integrity, escalation, shift
handover and "what you cannot do". Both keep a pointer to Event Information
written **without a link**, deliberately — a community without the flag has no
`/event-info` for the link to reach.

## Where the content lives

`application/event_info/content/<tenant-slug>/*.md` — one directory per
community, in the repo, reviewed in PRs. Inside the package for the same reason
help's is: `.dockerignore` drops `docs` and root-level `*.md` from the build
context.

| Tenant | Articles |
|---|---|
| `sgl26` | `schedule` (What's on, and when) · `attending` (Attending the event) · `who-to-ask` (Who to ask) · `proctoring` (Running a room — **role-gated**) |
| `default` | `attending` · `proctoring` — the **dev fixture**, see below |

A tenant with no directory has **no articles**, not an error: a community that
has just been granted the feature and written nothing renders an empty state.

> **The directory name is the tenant's `slug`, exactly.** Slugs live in the
> database and directories live in the repo, so nothing can check the two agree at
> import time — a mismatch renders the empty state, which looks identical to
> "nobody has written anything yet". This has already been hit once: the SGL
> handbook was first filed under `sgl` for a tenant whose slug is `sgl26`.
> `_root_for` logs a one-off warning naming the slug and the path it looked for,
> which is the only signal you get. Check the slug with the Wizzrobe MCP
> `list_tenants`, or `/platform`, before creating a directory.

The SGL articles are written from
[sglive.speedgaming.org](https://sglive.speedgaming.org) and its announcement
posts (read 2026-08-01): dates, venue and room block, ticket tiers, the on-site
and online tournament lists with their prize pools, the volunteer form and its
badge-comp tiers, the lanyard convention, the Discord, and the Twitch channels.
**Prize pools are community-funded and grow until the event**, so those figures
are a snapshot — the article says so rather than implying they are fixed.

> **What is still `TODO:`** renders as visible note blocks, because it is not
> published anywhere to copy: the **daily agenda** (the most-asked question), each
> tournament's **format and entry requirements**, **badge collection**, the room
> and stage **locations**, **lost property / accessibility / first aid**, and a
> **code of conduct** — neither `sglive.speedgaming.org` nor `speedgaming.org`
> publishes one that could be linked. One more is a genuine conflict: the site
> gives hotel check-out as the 27th and the announcement as the 26th.
>
> The flag is dark, so none of this reaches a reader until the gaps are filled and
> a super-admin grants it.

### This is v1 of a database-backed surface

The intended end state is DB-driven and staff-editable. Everything above the
loader is already shaped for that: the flag, the routes, the page, the nav and
the tests all go through `EventInfoService`, and none of them knows the content
is files. The change is `application/event_info/catalog.py` and nothing else.
The safe document model is already the one editable prose would need.

## Article format

The same front matter as a help article, plus `roles:`:

```markdown
---
title: Running a room
slug: proctoring
icon: sports_esports
order: 40
roles: VOLUNTEER, PROCTOR, STAFF   # optional — omit for a public article
feature: VOLUNTEERS                # optional — as in help
summary: One line for the index card.
---
```

`feature:` and `roles:` **degrade in opposite directions, on purpose**:

- an unknown `feature:` is logged and the article is treated as **ungated** — a
  typo in a header must not take the section down;
- an unknown role in `roles:` is logged and **dropped**, keeping the rest. An
  article whose every role is a typo becomes unreadable, which is a visible
  authoring bug. Falling open would be an invisible leak.

Roles are an **OR**: a reader holding any one of them qualifies.

## Gating

Three gates, resolved in `EventInfoService`:

| Gate | Applies to | Effect when it fails |
|---|---|---|
| `EVENT_INFO` | the whole section | `@public_page(feature=…)` 404s; the service raises `FeatureDisabledError` |
| `feature:` | one article | article withheld, same answer as missing |
| `roles:` | one article | article withheld, same answer as missing |

All three give the **same answer as "no such article"**. A reader who followed a
stale link should not learn which optional features their community has off, nor
that a page exists for people with more access than them.

**The page is public and stays public.** The role filter subtracts from what a
reader sees; it never redirects to `/login`. A signed-out visitor gets the public
articles, which is most of them and the ones they came for.

### The role gate is not the Volunteer flag

`roles: VOLUNTEER, PROCTOR, STAFF` mirrors the Volunteer hub's own gate
(`pages/volunteer.py`), so anyone who can reach the Proctor Station can read the
procedure it describes. It is deliberately **not** also gated on
`FeatureFlag.VOLUNTEERS`: `AuthService.can_run_match` admits staff and tournament
admins as well as proctors, so a community running matches without the volunteer
subsystem still has people who need the floor standard. This is a narrower
version of the known consequence [help.md](help.md#feature-gating) documents for
`proctor-result`.

## Help icons resolve across both sections

`help_icon` looks in help first, then this community's handbook. An icon names a
**snippet**, not a section, so the eight snippets that moved out of help kept
working — the popup simply links to `/event-info/…` now, via
`ContentSnippet.base_path`.

Two consequences worth knowing:

- **`help_icon` resolves `EVENT_INFO` itself** rather than letting the service
  raise. It is called from surfaces that are *not* gated on the flag (the Player
  tab, the Proctor Station), and an ungated surface must not inherit a raise from
  a feature its community does not have. It renders nothing instead.
- **Handbook snippets are per tenant**, so an icon wired to one opens only for a
  community that ships it. That is why the `default` fixture carries every moved
  snippet name — without it the dev loop and the browser sweep would quietly show
  a Player tab with three dead icons. `test_the_dev_tenant_carries_every_snippet_the_app_wires`
  is the guard.

Pass `user=` to `help_icon` from any surface that already resolved one; without
it the helper has to look the viewer up itself, once per icon. The Player tab and
the Proctor Station both pass it.

## The shared prose loader

Help and Event Information share `application/content/`:

- `blocks.py` — the closed document model (six block kinds, seven span kinds).
  **Never `ui.markdown`**; see [help.md](help.md#the-safe-document-model).
- `catalog.py` — front matter, `:::snippet` regions, heading anchors, and a
  parse cache keyed by directory (`catalog_for(root, base_path)`).

`application/help/` and `application/event_info/` are thin bindings over it: help
has one root, the handbook has one per tenant slug. Help's public names are
re-exported unchanged, so nothing outside these packages moved.

## Surfaces

- `/event-info` — index cards, and a line pointing at `/help` for anyone who
  arrived looking for app mechanics.
- `/event-info/{slug}` — sidebar (article list + this article's `##` headings)
  and the body, reusing the help section's renderer and `wiz-help-*` styling.
- **The drawer**, immediately above Help, ungated on `self.user` — the handbook
  answers the questions people have before they sign in.

## Tests

`tests/test_event_info_service.py` (the three gates, tenant scoping, snippet
inheritance) and `tests/test_event_info_content.py` (every shipped article
parses, roles parse to real roles, links resolve in both directions, the moved
snippet names survived).

The default test tenant's slug is `default`, which is the dev fixture's
directory — so the service tests run against real shipped content rather than a
synthetic one.

No new model, so no migration and no `tests/tenancy/` leak test: scoping here is
the content-root lookup, covered by
`test_one_communitys_article_is_not_readable_from_another`.
