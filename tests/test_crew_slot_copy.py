"""Crew match DMs name the slot the reader holds: commentator, tracker, or both."""

from application.utils.discord_messages import (
    AUDIENCE_CREW,
    AUDIENCE_WATCHER,
    crew_slot_line,
    crew_slot_title,
    rescheduled_dm,
    scheduled_dm,
    stage_cleared_dm,
)


def test_crew_slot_title_replaces_crew_slot():
    assert crew_slot_title('📺 Your crew slot is on stage', ('tracker',)) == (
        '📺 Your tracker slot is on stage'
    )


def test_crew_slot_title_appends_to_a_shared_title():
    assert crew_slot_title('🔴 Match started', ('commentator', 'tracker')) == (
        '🔴 Match started · your commentator and tracker slot'
    )


def test_no_slot_leaves_copy_alone():
    assert crew_slot_title('🔴 Match started', ()) == '🔴 Match started'
    assert crew_slot_line('hi', ()) == 'hi'


def test_crew_slot_line_adds_a_sentence():
    assert crew_slot_line('hi', ('tracker',)) == "hi\n\nYou're on this match as tracker."


def test_builders_name_the_slot_for_crew_only():
    assert scheduled_dm('Cup', 'now', audience=AUDIENCE_CREW, crew_roles=('tracker',)).startswith(
        "A match you're tracking in **Cup**"
    )
    assert rescheduled_dm(
        'Cup', 'now', audience=AUDIENCE_CREW, crew_roles=('commentator', 'tracker'),
    ).startswith("A match you're commentating and tracking in **Cup**")
    assert stage_cleared_dm('Cup', 'now', audience=AUDIENCE_CREW).startswith(
        "A match you're on crew for"
    )
    assert scheduled_dm(
        'Cup', 'now', audience=AUDIENCE_WATCHER, crew_roles=('tracker',),
    ).startswith("A match you're watching")
