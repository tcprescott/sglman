# Match Participation: Crew, Acknowledgment, Watching

How people attach themselves to a match — signing up as crew, confirming they will
be there, and subscribing to updates. The DMs these flows send are documented in
[discord.md](discord.md); the button handlers behind them in
[reference/discord-integration.md](../reference/discord-integration.md).

## Crew signup and approval

Commentators and Trackers (collectively "crew") sign up per match, and a staff
member approves them. Signup works from the web or from Discord DM buttons — both
land in the same service, so the rules and audit trail are identical.

1. Signup inserts a `Commentator` or `Tracker` row with `approved=False`, either from the web UI or from the buttons on a stream-candidate DM (`discordbot/crew_signup.py`).
2. A staff member approves from the approval toggle beside the crew member's name in the match table (both directions confirm first).
3. The approved crew member acknowledges — web UI or DM button.

Both directions DM the crew member: approving sends the assignment DM with the
Acknowledge button, and withdrawing approval sends a withdrawal notice — a
withdrawal also clears `acknowledged_at`, so without it someone who confirmed
they would cover a match is dropped from it silently.

```python
from application.services import CrewService

await CrewService().signup_crew(match_id, user, 'commentator')
await CrewService().undo_crew_signup(match_id, user, 'commentator')

crew = await CrewService().get_crew_member_by_id(crew_id, 'commentator')
await CrewService().approve_crew_member(crew, 'commentator', actor=actor)
await CrewService().update_crew_approval(crew, 'commentator', approved=False, actor=actor)
await CrewService().acknowledge_crew_assignment(crew_id, 'commentator', user)
```

The REST crew endpoints return only `approved=True` rows — enforced by a Pydantic
validator, so an unapproved signup is never exposed. Signup, approval and undo all
audit through `AuditActions.CREW_SIGNUP_CREATED` / `CREW_APPROVAL_CHANGED`.

## Acknowledgment

Two flows, both confirming someone has seen and accepted a match.

**Players** get a DM with an Acknowledge button (`match_ack:ack:<match_id>`) when a
match is scheduled. The handler in `discordbot/match_acknowledgment.py` calls
`MatchService.acknowledge_match(match_id, user)`, which upserts a
`MatchAcknowledgment` row — one per player per match.

**Crew** acknowledge after approval, via the web UI prompt on their assignments view
or the DM button in `discordbot/crew_acknowledgment.py`, routing to
`CrewService.acknowledge_crew_assignment`.

The admin schedule highlights matches with unacknowledged players; per-player state
comes from `MatchAcknowledgmentRepository.list_for_match()` / `list_for_matches()`.

## Watching

Any logged-in user can watch a match to get DMs on its state changes — watchers are
observers, not participants, and watching is independent of acknowledgment.

`MatchWatcherService.watch(match_id, user)` inserts a `MatchWatcher` row from the
schedule tab or the match dialog. Lifecycle DMs to a watcher carry an Unwatch button
(`match_watch:unwatch:<match_id>`) handled in `discordbot/watch_buttons.py`. Watching
itself is web-only — there is no Watch button on Discord, only Unwatch.

Someone who is both a player and a watcher gets one DM per event, not two; dedup
happens in `MatchScheduleService` before the send loop.

## Check-in and the station pool

Check-in is **per match**, not per player: a proctor checks a match in once both
players are in the room, which stamps the single match-level `Match.seated_at`.
The same flow seats each player at a numbered station.

### The station pool

`Station` is the venue's fixed pool of physical seats — managed by STAFF on
**Admin → Settings → Station Pool** (`StationService`), beneath the
`StationFormat` control it belongs with. A station has a `name` (the label), an
optional free-text `section` ("North wall") that is display-only, a `sort_order`,
and an `is_active` flag. Names are unique per tenant.

`MatchPlayers.assigned_station` stores the **label**, not an FK. Two consequences
follow, and both are deliberate:

- **The pool is advisory until it exists.** A community with zero `Station` rows
  keeps the historical free-text field validated only by the `StationFormat`
  regex. This is why the station pool has no per-tenant feature flag — it
  self-gates.
- **Deleting a station does not rewrite history.** Past matches keep their text.
  Deactivate rather than delete.

### Double-booking

`MatchService.assign_stations` runs one validation ladder, reporting the most
specific problem first:

1. the same station assigned to both players of this match;
2. the label fails the tenant's `StationFormat` regex;
3. the label is not in the pool — *only* once the pool is non-empty;
4. the station is already in use by another match in play.

**Occupancy is derived, never stored.** A station is in use when some match that
is **seated and not finished** has a player assigned to it. It frees up when that
match *finishes*, not when an admin confirms it — the seat is physically empty at
that point. The lookup (`MatchRepository.occupied_stations`) excludes the match
being edited, so re-assigning a match to the station it already occupies is
allowed, and it is tenant-scoped, so two communities that both call a station "1"
never block each other.

There is **no pairing rule**: which two stations a proctor picks is their
judgment, and the app neither computes nor suggests opposite-side pairs.

## Disputed results

The agreed model is *the proctor records their best guess and the admin
overrides during confirmation*. The dispute signal that makes that workable is
**a flag plus a note, not a workflow** — there is no dispute state, no
assignment, no thread, and no notification beyond the domain event.

Two columns on `Match` carry it: `needs_review` (bool) and `review_note` (text).
The match stays `Finished` throughout; nothing about the state machine changes.

**Raising it.** The proctor ticks *Flag for admin review* in the result dialog
(`theme/dialog/match_result_dialog.py`) when they record the winner, and types
what happened. The checkbox exists only in the dialog's `record` mode — the
admin reaching the same dialog in `edit` mode to correct a winner *is* the
review, so offering them the flag would let them raise a dispute with
themselves. The dialog calls `MatchService.flag_for_review` **after** its
`on_submit` finishes the match, because a match that is not finished yet cannot
be flagged (`ValueError`). Gate: `can_run_match` — this is the proctor's own
action, and they are the one in the room who saw the disagreement.

**Seeing it.** `MatchDisplayService` puts `needs_review` / `review_note` on
every table row. The desktop State cell shows a "Needs review" chip above the
Confirm button with the note on a tooltip; the mobile card renders the same chip
**and the note as text**, because a tooltip is unreachable on a touch screen.
The admin Schedule tab's review-queue strip counts flagged matches separately
from merely-unconfirmed ones, since a contested result needs a decision and an
uncontested one needs a click.

The **confirm dialog repeats it** rather than relying on the row behind it
(`confirm_result_message` in `theme/tables/match_lifecycle.py` — pure, so its
copy is unit-tested). That body names the winner (`Record <name> as the winner of
match #N?`), says who beat whom, and for a flagged result quotes the proctor's
note and warns that confirming clears the flag. The desktop row's note lives in a
hover tooltip, which is the wrong place for the one fact that explains why the
match is in front of the admin at all.

**Resolving it.** *Confirming the match is the resolution* — an admin
confirming has, by definition, looked at it, so `confirm_match` clears
`needs_review` and writes a second `match.review_cleared` audit row carrying the
note (`resolved_by: 'confirmation'`). `MatchService.clear_review` drops the flag
without confirming, for "looked at it, nothing to fix, not confirming yet";
it is gated on `can_confirm_match`, so a proctor cannot unflag their own
dispute. **Neither clears `review_note`** — the note is the record of *why* the
result was contested, and a resolved dispute still happened.

Both directions are also reachable over REST as `POST /matches/{id}/review`
(`{needs_review, note?}`), with the same split gates. Both emit domain events
(`match.flagged_for_review`, `match.review_cleared`): a contested result is
exactly what an alerting webhook subscriber wants to hear about.

The dispute flag has **no per-tenant feature flag** — like the station pool it
self-gates, since a community that never ticks the box never sees it.

## Models

| Model | Holds |
|---|---|
| `Commentator`, `Tracker` | crew signups; `approved` bool, `acknowledged_at` timestamp |
| `MatchAcknowledgment` | per-player acknowledgment state per match |
| `MatchWatcher` | user × match watch subscriptions |
| `Station` | the venue's pool of physical seats (per tenant; label-referenced) |

Field-level detail: [reference/data-model.md](../reference/data-model.md).
