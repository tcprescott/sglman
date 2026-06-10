from nicegui import ui


def help_tab() -> None:
    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('Help').classes('page-title')
        ui.separator().classes('separator-spacing')

        with ui.expansion('Schedule', icon='schedule').classes('card-full-width'):
            ui.markdown("""
The **Schedule** tab shows all upcoming and recent matches for the current tournament.

**Reading the table**
- Each row is one match. Columns show the scheduled time (Eastern), tournament, stream room, players, and crew slots.
- Times are displayed in US/Eastern time.

**Filtering**
- Use the filter bar at the top to narrow results by date, tournament, stream room, or match state.

**Watching a match**
- If you are logged in, a watch column appears. Click the eye icon on any match to subscribe to notifications for that match.
- To manage your notification preferences across all tournaments, click **Manage Notifications** in the header.
""")

        with ui.expansion('Crew Signup', icon='mic').classes('card-full-width'):
            ui.markdown("""
Crew members can sign up as a **Commentator** or **Tracker** directly from the Schedule tab.

**Commentator**
- Click the microphone icon in the Commentator column for a match.
- Fill in your name/handle and any notes, then submit.
- Your signup goes to the tournament admin for approval.

**Tracker**
- Click the tracker icon in the Tracker column for a match.
- Fill in your details and submit.
- Approvals are handled by the tournament admin or crew coordinator.

You can remove your own pending signup by clicking the icon again and cancelling.
""")

        with ui.expansion('Notifications', icon='notifications').classes('card-full-width'):
            ui.markdown("""
SGLMan can send you Discord DMs when match events happen.

**Setting your preferences**
- Click **Manage Notifications** in the Schedule tab header.
- Choose a notification level for each tournament you are enrolled in.

**Notification levels**

| Level | What you receive |
|---|---|
| None | No notifications |
| My Matches | Updates for matches you are playing in |
| All Matches | Updates for every match in the tournament |

Match events that trigger notifications include: match scheduled, check-in opened, match started, and results confirmed.
""")

        with ui.expansion('Profile', icon='people').classes('card-full-width'):
            ui.markdown("""
The **Profile** tab lets you manage your personal information and tournament registrations.

**Display name**
- Set a preferred display name that appears on the schedule and in match notifications.
- If left blank, your Discord username is used.

**Tournament registration**
- Check the box next to a tournament to register as a player.
- Uncheck to de-register. Changes take effect immediately.
""")

        with ui.expansion('Player', icon='videogame_asset').classes('card-full-width'):
            ui.markdown("""
The **Player** tab shows your personal match schedule — only matches you are enrolled in as a player.

- Matches are shown in chronological order with time, tournament, stream room, and opponent(s).
- Use this tab to quickly see what is coming up for you without the full tournament schedule.
""")

        with ui.expansion('Triforce Texts', icon='img:/static/triforce.svg').classes('card-full-width'):
            ui.markdown("""
Some ALTTP tournaments collect **Triforce Text** submissions — the three lines of custom text shown on the triforce screen at the end of a game.

**Submitting your text**
- Open the **Triforce Texts** menu entry to see the tournaments accepting submissions, then pick yours.
- Submitting is a paid option — if you don't yet have access, the tournament page explains how to get it.
- Enter up to three lines of text (subject to the tournament's character limits).
- Submissions are reviewed and approved by tournament staff before use.

**Editing your submission**
- You can update your submission until it is approved. Return to the same link and edit your entry.
""")
