#!/usr/bin/env python3
"""Print every Discord DM and ephemeral reply the bot can send, with sample data.

Calls the real builders in ``application/utils/discord_messages.py`` — no bot, no
Discord connection, no database. This is how you "see" the Discord surface: the
copy is fully determined by these functions. Run from the repo root:

    poetry run python .claude/skills/discord-ux/render_surface.py

If a builder's signature changes, update the sample call below to match.
See .claude/skills/discord-ux/SKILL.md for the full reconstruction workflow.
"""

import os
import sys

sys.path.insert(0, os.getcwd())

from application.utils import discord_messages as m  # noqa: E402

# Representative sample data (two players → "A vs B"; a stage; an Eastern time).
P = ["Player One", "Player Two"]
T = "SGL Dev Tournament"
WHEN = "2026-07-19 22:41 EDT"
STAGE = "Stage 2"
SHIFT = ("Race Proctor", "Shift 1", "2026-07-19 08:00 EDT", "2026-07-19 12:00 EDT")

# Buttons that ride each DM (see docs/reference/discord-integration.md flow table).
NOTIFICATIONS = [
    ("Acknowledgment request (new match)", "[Acknowledge]",
     m.acknowledgment_request_dm(T, WHEN, rescheduled=False, stream_room_name=STAGE, player_names=P)),
    ("Acknowledgment request (rescheduled)", "[Acknowledge]",
     m.acknowledgment_request_dm(T, WHEN, rescheduled=True, stream_room_name=STAGE, player_names=P)),
    ("Scheduled — crew/subscriber info", "[Unwatch] (watchers only)",
     m.scheduled_dm(T, WHEN, player_names=P, stream_room_name=STAGE)),
    ("Rescheduled — crew/subscriber info", "[Unwatch] (watchers only)",
     m.rescheduled_dm(T, WHEN, player_names=P, stream_room_name=STAGE)),
    ("Checked in", "[Unwatch] (watchers only)",
     m.checked_in_dm(T, player_names=P, scheduled_at_display=WHEN, stream_room_name=STAGE)),
    ("State changed — Started (also Finished/Confirmed)", "[Unwatch] (watchers only)",
     m.state_changed_dm(T, "Started", player_names=P, scheduled_at_display=WHEN, stream_room_name=STAGE)),
    ("Stream candidate alert", "[Sign up as Commentator] [Sign up as Tracker]",
     m.stream_candidate_dm(T, WHEN, player_names=P)),
    ("Crew signup invitation (subscribers)", "[Sign up as Commentator] [Sign up as Tracker]",
     m.scheduled_dm(T, WHEN, player_names=P, stream_room_name=STAGE)),
    ("Crew approved", "[Acknowledge]",
     m.crew_assignment_dm("commentator", "Player One vs Player Two", WHEN, STAGE, P)),
    ("Seed generated", "(no buttons)",
     m.seed_dm("Player One", T, "https://alttpr.com/en/h/abcd1234",
               player_names=P, scheduled_at_display=WHEN, stream_room_name=STAGE)),
    ("Volunteer shift assigned", "[Acknowledge]",
     m.volunteer_assignment_dm(*SHIFT)),
    ("Volunteer shift reminder", "[Acknowledge]",
     m.volunteer_reminder_dm(*SHIFT)),
]

EPHEMERAL = [
    ("crew signup", m.crew_signup_confirmation("commentator", "Player One vs Player Two")),
    ("match ack", m.match_ack_confirmation("Player One vs Player Two")),
    ("crew ack", m.crew_ack_confirmation("commentator", "Player One vs Player Two")),
    ("volunteer ack", m.volunteer_ack_confirmation("Race Proctor")),
    ("unwatch (was watching)", m.unwatch_confirmation("Player One vs Player Two", True)),
    ("unwatch (was not)", m.unwatch_confirmation("Player One vs Player Two", False)),
    ("no account", m.MSG_NO_ACCOUNT),
]


def _rule(char: str = "─") -> str:
    return char * 72


def main() -> None:
    print(_rule("="))
    print("DISCORD NOTIFICATION DMs  (plain text + button row — no embeds)")
    print(_rule("="))
    for name, buttons, text in NOTIFICATIONS:
        print(f"\n### {name}\nbuttons: {buttons}\n{_rule()}")
        print(text)
    print(f"\n{_rule('=')}")
    print("EPHEMERAL REPLIES  (private, shown after a button click)")
    print(_rule("="))
    for name, text in EPHEMERAL:
        print(f"\n[{name}]  {text}")
    print()


if __name__ == "__main__":
    main()
