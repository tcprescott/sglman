# Community Events

A members-only listing — the **Community** view of Home's Event tab (`/home/community`) — of the meetups, panels, side
tournaments and board game nights that attendees run for each other during the
onsite event. Members submit events, staff approve them, and anyone can subscribe
to a listed event for a Discord DM shortly before it starts.

Behind `FeatureFlag.COMMUNITY_EVENTS`, which **ships dark**.

Every surface carries the same disclaimer (`theme/community_events.py`
`DISCLAIMER`): these events are run by members, not event staff, and listing one
is not an endorsement.

## Lifecycle

Staff approval is a per-community switch, **Require staff approval** under
Admin → Settings → Community Events (`community_event_require_approval`, on by
default). Turned off, a member's submission is listed straight away, audited as
submitted plus an automatic approval, and staff get no DM. Staff can still take
an event down, and the host's edit of a taken-down event goes back to review
either way, so the switch can't be used to dodge a take-down.

| Status | Set by | Listed? | Reminded? |
|---|---|---|---|
| `PENDING` | a member's submission while approval is required; a host editing a rejected event | no (host and staff only) | no |
| `APPROVED` | staff approving; any staff submission, and any member submission when approval is off (auto-approved) | yes | yes |
| `REJECTED` | staff rejecting a submission or taking a listed one down, with a reason | no | no |
| `CANCELLED` | the host or staff | no | no |

- **Edits by the host go live without re-review** on an approved event. Staff
  take a bad edit down with Reject ("Take down"), which DMs the host the reason
  and tells subscribers it's off.
- Moving an approved event's start DMs its subscribers and clears their
  `reminder_sent_at` so the reminder fires at the new time. Text-only edits are
  silent.
- A cancelled event is frozen: no edits, no approval.
- The listing shows approved events until they **end**
  (`starts_at + duration_minutes`), with a "Happening now" chip while running.

## Who is told what

| Trigger | Recipient | Link button |
|---|---|---|
| Member submits, or resubmits a rejected event | every STAFF member except the host | Admin → Community Events with the review dialog open (`?community_event=<id>`) |
| Staff approve | host | the event page |
| Staff reject / take down | host (with the reason) | the event page, labelled "Edit the event" |
| Approved event moves | subscribers | the event page |
| Approved event cancelled or taken down | subscribers | the event page |
| `lead` minutes before start (worker) | subscribers | the event page |

All DMs go through `discord_queue` and are mirrored to web push; `send_dm` drops
the Discord copy for anyone with `dm_notifications` off. Senders live in
`application/services/_community_event_notifications.py`, copy in
`application/utils/discord_messages_community_events.py`.

## RSVPs

A host can tick **Take RSVPs** when submitting or editing, with an optional cap.
Members then see an **RSVP** button instead of **Remind me**; RSVPing marks
their subscription `going`, so it also gets them the reminder, and cancelling
removes both. At the cap the button reads **Full**. The cap is checked with the
event row locked, so two people can't take the last place. Everyone sees "N of M
going"; the host and staff also see the names on the event page. Turning RSVPs
off keeps the rows but stops counting them. RSVPs aren't audited, like
subscriptions.

## Reminders

`application/services/community_event_reminder.py` ticks every 60s. It scans
(cross-tenant) un-reminded subscriptions to approved events starting within 24
hours, then per subscription re-checks the flag and the community's lead
(`community_event_reminder_lead_minutes`, Admin → Settings → Community Events,
default 30). It stamps before sending, so a failure never double-sends. Drive it
by hand with `poetry run python scripts/run_worker_tick.py community_event_reminder`.

## Descriptions and the editor

Descriptions are markdown written in `theme.markdown_editor.MarkdownEditor`, a
reusable NiceGUI element wrapping [Tiptap](https://tiptap.dev) (MIT). The writer
sees formatted text and a toolbar; the value is markdown. The toolbar offers only
what the closed block parser (`application/content/blocks.py`) renders: bold,
italic, inline code, links (https/mailto/relative), two heading levels, lists and
notes (blockquotes). Descriptions are rendered with `parse_blocks` +
`render_blocks`, never `ui.markdown`.

The Tiptap bundle is vendored in `theme/markdown_editor/dist/` (third-party
notices in `dist/THIRD_PARTY_LICENSES.txt`). To change it, edit
`theme/markdown_editor/package.json` or `src/`, then run `npm ci && npm run build`
in that directory and commit `dist/` and the lockfile. `node_modules/` is
git-ignored.

## Surfaces

| Surface | Who | Gate |
|---|---|---|
| Home → Event → **Community** (`/home/community`) | members | an `EventView` gated on `COMMUNITY_EVENTS` (`pages/home_tabs/event.py`); builder `community_events_view` in `pages/community_events.py` |
| `/community-events` | members | `@protected_page(feature=COMMUNITY_EVENTS)`; redirects to `/home/community` |
| `/community-events/{id}` | members (non-approved events: host and staff only, else 404) | same |
| Admin → Community Events | STAFF | `FeatureFlag.COMMUNITY_EVENTS in live` |
| Admin → Settings → Community Events | STAFF | same |

No REST router or MCP tool exists yet.

## What's new

`CommunityEventSeen` (one row per member per community, migration 100) holds
when the member last opened the Community view. An event is **new** to them when
it's approved, not finished, not their own, and `listed_at(event)` (its
`reviewed_at`, else `created_at` for one listed without review) is after that.
No row means everything listed is new. `CommunityEventService.unseen_ids` reads
it; `mark_seen` moves it to now, and opening the view calls both, in that order,
so the New chips show on that visit only.

The count rides the Event tab's `badge` (drawer and bottom nav) and the
Community segment of the view switcher, all registered under the `Event` label
in `theme/nav_badges.py`, so `set_nav_count('Event', 0)` clears every copy when
the view opens. `community_new_count` (in `pages/home_tabs/event.py`) returns 0
rather than raising when the flag is off or the viewer can't see the listing.

## Audit and webhooks

`AuditActions.COMMUNITY_EVENT_{SUBMITTED,UPDATED,APPROVED,REJECTED,CANCELLED}`,
each paired with the same-named `EventType` through `write_and_publish`. Details
carry `community_event_id`, `title`, `starts_at`, `status`; the event adds
`host_id`. Subscriptions are private and neither audited nor published.
