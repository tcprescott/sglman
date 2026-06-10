from nicegui import ui


def admin_help_page() -> None:
    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Admin Help').classes('page-title')
        ui.separator().classes('separator-spacing')

        with ui.expansion('Match Lifecycle', icon='loop').classes('card-full-width'):
            ui.markdown("""
Every match moves through four states. Buttons in the Schedule tab advance the match forward.

| State | Condition | Available action |
|---|---|---|
| Scheduled | Match created, not yet checked in | Seat players (check-in) |
| Checked In | Players seated, waiting to start | Start match |
| In Progress | Match started, waiting for result | Finish match |
| Finished | Result recorded | Confirm result |

- **Seat** — marks players as checked in and opens the match for play. Optionally assign station numbers.
- **Start** — records the start time and begins the match clock.
- **Finish** — opens the result dialog to enter finish ranks for each player.
- **Confirm** — finalises the result and triggers Discord notifications.

Matches can also be edited or deleted at any state by staff or tournament admins.
""")

        with ui.expansion('Schedule Management', icon='schedule').classes('card-full-width'):
            ui.markdown("""
The **Schedule** tab is the primary tool for managing match logistics.

**Creating a match**
- Click **Add Match** to open the match dialog.
- Fill in tournament, stream room, scheduled time (Eastern), and players.
- Save to create the match. A Discord notification is sent to enrolled players.

**Editing a match**
- Click the pencil icon on any match row to edit it.
- Changes to scheduled time or stream room send an update notification to players.

**Generating a seed**
- For randomizer tournaments, click the seed icon to generate and attach a randomizer seed to the match.
- The seed preset is configured per tournament in Tournament Settings.

**Station assignment**
- During check-in (Seat action), you can assign each player to a physical station number.
- Station numbers appear on the schedule and in player notifications.

**Deleting a match**
- Click the trash icon. Deletion sends a cancellation notification to players.
""")

        with ui.expansion('User Management', icon='people').classes('card-full-width'):
            ui.markdown("""
The **Users** tab (Staff only) manages global roles across the platform.

**Global roles**

| Role | Access |
|---|---|
| Staff | Full admin access — all tabs, all tournaments |
| Proctor | Schedule tab access; can seat/start/finish/confirm matches |
| Stream Manager | Stream Rooms tab; can manage stream stages |

**Granting a role**
- Find the user in the table (use the role filter to narrow results).
- Click the edit icon and toggle the desired role on.

**Revoking a role**
- Same as granting — open the user dialog and toggle the role off.

**Per-tournament roles** (Tournament Admin, Crew Coordinator) are managed from the Tournaments tab, not here.
""")

        with ui.expansion('Tournament Settings', icon='emoji_events').classes('card-full-width'):
            ui.markdown("""
The **Tournaments** tab lets staff and tournament admins configure tournament metadata.

**Creating a tournament**
- Click **Add Tournament** and fill in the name, abbreviation, and any seed preset.

**Editing a tournament**
- Click the edit icon on a row to update settings.
- Key fields:
  - **Name / Abbreviation** — displayed on the schedule and in notifications.
  - **Seed preset** — controls which randomizer and settings are used when generating seeds.
  - **Tournament Admins** — users with TA role for this tournament (can manage matches, triforce texts).
  - **Crew Coordinators** — users who can approve crew signups and access reports for this tournament.

**Announcements**
- Announcements can be added to a tournament and appear on the home schedule.
""")

        with ui.expansion('Stream Rooms', icon='tv').classes('card-full-width'):
            ui.markdown("""
The **Stream Rooms** tab (Staff and Stream Managers) manages the named stages shown on the schedule.

**Adding a stream room**
- Click **Add Stream Room** and enter a name (e.g. "Stage 1", "Commentary Room B").

**Editing / disabling**
- Click the edit icon to rename a room or mark it inactive.
- Inactive rooms no longer appear in match creation dropdowns but retain their history.
""")

        with ui.expansion('Triforce Texts', icon='svguse:/static/triforce.svg#triforce|0 0 512 512').classes('card-full-width'):
            ui.markdown("""
The **Triforce Texts** tab (Staff and Tournament Admins) moderates player text submissions for ALTTP tournaments.

**Reviewing submissions**
- The table shows all pending, approved, and rejected entries filtered by tournament.
- Each row shows the player, their three lines, and the current approval status.

**Approving or rejecting**
- Click the approve (✓) or reject (✗) button on a row.
- Approved texts are locked in for use; the player is notified via Discord DM.
- Rejected texts can be edited and resubmitted by the player.

**Filtering**
- Use the status filter to view only Pending, Approved, or Rejected entries.
""")

        with ui.expansion('Reports', icon='analytics').classes('card-full-width'):
            ui.markdown("""
The **Reports** tab provides operational summaries. Use the report selector at the top to switch views.

| Report | Purpose |
|---|---|
| **Dashboard** | High-level summary: match counts by state, upcoming matches today |
| **Capacity** | Stream room utilisation — how many matches are scheduled per room per day |
| **Crew** | Commentator and tracker signup status; who is approved, pending, or missing |
| **Match Ops** | Detailed match-by-match log with timestamps for each lifecycle transition |
| **Stream Rooms** | Room-level breakdown of scheduled vs completed matches |
| **Audit** | Full log of admin actions — who changed what and when |

**Filtering**
- Most reports accept a date range, tournament, or stream room filter.
- The audit log can be filtered by action type and actor.

**Exporting**
- Use your browser's print or save function to export a report view. Tabular data can be selected and copied.
""")
