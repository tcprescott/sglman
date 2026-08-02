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
2. Whoever `can_approve_crew` admits — staff, the tournament's admin, **or its crew coordinator** — approves from the toggle beside the crew member's name in the match table (both directions confirm first).
3. The approved crew member acknowledges — from **My Crew**, the schedule board, or the DM button.

Each side has a surface of its own for the work it owns:

| Who | Where | What it carries |
|---|---|---|
| Staff / TA / crew coordinator | Admin → Schedule, the crew strip | *"3 commentators and 1 tracker awaiting approval"* with a one-click filter to exactly those matches |
| The volunteer | Home → **My Crew** (`home_tabs/my_crew.py`) | Their own signups across both roles, soonest first, each card naming the match and its state — awaiting approval / approved-please-confirm / confirmed / played — with Confirm and Withdraw |

My Crew is on Home rather than the Volunteer hub deliberately: crew signup is
behind neither a role nor `FeatureFlag.VOLUNTEERS`, so anyone who can sign up
must be able to see what they signed up for. It is the crew twin of
**My Shifts**, which volunteers who work shifts have had all along.

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

# The volunteer's own list (My Crew), both roles merged and sorted by when.
await CrewService().list_my_commitments(user, upcoming_only=True)
# What else this person is committed to while that match runs — players count,
# because someone racing at 19:00 cannot commentate at 19:00 either.
await CrewService().find_scheduling_conflicts(user, match, 'commentator')
```

**Approving checks for a clash.** `find_scheduling_conflicts` answers, in one
query across all three roles, what else the person is committed to in the
match's window (the tournament's `average_match_duration`, or 90 minutes), and
the approval confirmation names what it found. Approval used to be decided from
a dialog showing one line — the person's name — and no conflict check existed
anywhere in the crew path.

The REST crew endpoints return only `approved=True` rows — enforced by a Pydantic
validator, so an unapproved signup is never exposed. Signup, approval and undo all
audit through `AuditActions.CREW_SIGNUP_CREATED` / `CREW_APPROVAL_CHANGED`.

**A tournament can opt out of a role.** `Tournament.required_commentators` /
`required_trackers` (Tournament edit → Entry & administration → Stream crew)
say how much approved crew a streamed match needs; `0` means the tournament does
not use that role at all. The schedule board renders no **Sign up** for it, and
`signup_crew` refuses it — the Discord button and the REST route reach past the
hidden control, so the rule lives in the service. `undo_crew_signup` is
deliberately *not* gated: a signup made before the requirement changed has to
stay removable. The same numbers drive the coverage reports
([admin-reports](admin-reports.md#what-covered-means)).

## Acknowledgment

Two flows, both confirming someone has seen and accepted a match.

**Players** get a DM with an Acknowledge button (`match_ack:ack:<match_id>`) when a
match is scheduled. The handler in `discordbot/match_acknowledgment.py` calls
`MatchService.acknowledge_match(match_id, user)`, which upserts a
`MatchAcknowledgment` row — one per player per match.

**Crew** acknowledge after approval, from **My Crew**, the schedule board's crew
cell, or the DM button in `discordbot/crew_acknowledgment.py` — all three route to
`CrewService.acknowledge_crew_assignment`.

The admin schedule highlights matches with unacknowledged players; per-player state
comes from `MatchAcknowledgmentRepository.list_for_match()` / `list_for_matches()`.

**A player with no acknowledgment row is invisible to all of it** — no icon in the
board's players cell, no Acknowledge button (it is gated on the row existing), and
an admin dialog that reports nobody assigned. The SpeedGaming sync used to produce
exactly that, syncing players and no rows; it now calls
`MatchParticipants.reconcile_acknowledgments`, which creates the missing rows and
drops the stale ones **without rewriting the answers already given**. That is the
distinction to keep: `seed_acknowledgments` is destructive by design (an admin
rewriting the roster is restarting the question), so a caller that runs repeatedly
over the same match wants the reconciling one.

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

### Randomizing the seating

The check-in dialog's **Randomize** button draws a station for each player
instead of the proctor picking two by hand. It calls
`MatchService.suggest_stations`, which **proposes and never writes** — the
values land in the pickers, the proctor can override any of them, and the
commit is still the same `assign_stations` call with its full validation ladder.

Two rules, both soft:

1. **Opposite sides.** The two players are drawn from different `Station.side`
   values, so they end up in different halves of the room.
2. **Spread out.** Within a side, a station whose neighbours are free is
   preferred over one beside a match already in play. Neighbours are same
   `side`, same `section`, `position` one apart.

Anything the draw could not honour comes back as a sentence and is shown as a
warning toast: one side full, no sides recorded on the pool at all, or a room
busy enough that somebody had to sit next to a live match. The draw refuses
outright only when it has nothing to work with — a match that does not have
exactly two players, a community with no station pool, or fewer than two free
stations. Which specific seat a player gets is deliberately arbitrary;
`secrets.choice` picks within whichever tier survived the rules above.

The button appears only for a two-player match on a community that has defined
a pool. `Station.side` and `Station.position` are set under Admin → Settings →
Station Pool and are both optional — a community that leaves them null gets a
plain random draw with a note explaining why the players were not split.

## Disputed results

The agreed model is *the proctor records their best guess and the admin
overrides during confirmation*. The dispute signal that makes that workable is
**a flag, not a workflow** — there is no dispute state, no assignment, no
thread, no note, and no notification beyond the domain event.

One column on `Match` carries it: `needs_review` (bool). The match stays
`Finished` throughout; nothing about the state machine changes.

**Raising it.** The proctor ticks *Flag for admin review* in the result dialog
(`theme/dialog/match_result_dialog.py`) when they record the winner. The
checkbox exists only in the dialog's `record` mode — the admin reaching the same
dialog in `edit` mode to correct a winner *is* the review, so offering them the
flag would let them raise a dispute with themselves. The dialog calls
`MatchService.flag_for_review` **after** its `on_submit` finishes the match,
because a match that is not finished yet cannot be flagged (`ValueError`). Gate:
`can_run_match` — this is the proctor's own action, and they are the one in the
room who saw the disagreement.

There is deliberately **no note field**. A proctor raising the flag is standing
in a room mid-event; what happened is a conversation with the admin, not a
textarea to fill in between matches. The audit trail records that the dispute
happened and who raised it.

**Seeing it.** `MatchDisplayService` puts `needs_review` on every table row. The
desktop State cell shows a "Needs review" chip above the Confirm button with
what the flag means on a tooltip; the mobile card renders the same chip **and
that sentence as text**, because a tooltip is unreachable on a touch screen. The
admin Schedule tab's review-queue strip counts flagged matches separately from
merely-unconfirmed ones, since a contested result needs a decision and an
uncontested one needs a click.

The **confirm dialog repeats it** rather than relying on the row behind it
(`confirm_result_message` in `theme/tables/match_lifecycle.py` — pure, so its
copy is unit-tested). That body names the winner (`Record <name> as the winner of
match #N?`), says who beat whom, and for a flagged result says the proctor
flagged it and warns that confirming clears the flag.

**Resolving it.** *Confirming the match is the resolution* — an admin
confirming has, by definition, looked at it, so `confirm_match` clears
`needs_review` and writes a second `match.review_cleared` audit row
(`resolved_by: 'confirmation'`). `MatchService.clear_review` drops the flag
without confirming, for "looked at it, nothing to fix, not confirming yet"; it
is gated on `can_confirm_match`, so a proctor cannot unflag their own dispute.

Both directions are also reachable over REST as `POST /matches/{id}/review`
(`{needs_review}`), with the same split gates. Both emit domain events
(`match.flagged_for_review`, `match.review_cleared`): a contested result is
exactly what an alerting webhook subscriber wants to hear about.

The dispute flag has **no per-tenant feature flag** — like the station pool it
self-gates, since a community that never ticks the box never sees it.

## Stream volunteering

Players can offer their own match for stream. It is a signal and nothing more:
staff read it while they build the stream schedule, and `is_stream_candidate`
— written by whoever `can_assign_match_stream` admits — remains the decision.
Every surface that shows the control says so, because a toggle sitting beside a
Stage column reads as booking one otherwise.

`MatchStreamVolunteer` holds one row per player, not a flag on the match, so a
board can say whether one player asked or both did. `MatchStreamVolunteerService`
enforces the two rules that keep it advisory:

- **Only the match's own players may offer it.** A non-player gets
  `ValueError('Only the players in a match can offer it for stream.')`.
- **Offering never writes `is_stream_candidate`.** A player's request must not
  be able to write the decision it is asking about.

Offering is refused once the match has started — there is nothing left for staff
to schedule — but **withdrawing is not**, so a player who changes their mind is
never stuck with a request they cannot unsay. Both directions audit
(`match.stream_volunteered` / `match.stream_volunteer_withdrawn`) and publish the
matching domain events.

**Where it appears.** The player's own board (Home → Your Schedule) carries a
`Stream` column beside `Watch`: a `videocam` toggle for a player in that match,
and a count chip for anyone else. The mobile card carries a labelled *Offer for
stream* button in its actions row and names the volunteers under the Stage line.
The player match dialog has a switch with the full sentence under it. On the
staff side, `MatchDisplayService` puts `stream_volunteers` (names) on every row,
and the admin match dialog prints them directly under the *Stream candidate*
checkbox — the offer read where the decision is made.

No feature flag: a community whose players never offer a match never sees it.

## Models

| Model | Holds |
|---|---|
| `Commentator`, `Tracker` | crew signups; `approved` bool, `acknowledged_at` timestamp |
| `MatchAcknowledgment` | per-player acknowledgment state per match |
| `MatchWatcher` | user × match watch subscriptions |
| `Station` | the venue's pool of physical seats (per tenant; label-referenced) |

Field-level detail: [reference/data-model.md](../reference/data-model.md).
