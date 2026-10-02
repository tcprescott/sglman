"""Source-shape guards for player-journey fixes the SQLite suite cannot drive.

Each was a live bug found by driving the app (docs/reviews/player-journey-ux.md)
in code that only runs inside a NiceGUI client, so the assertion is on the shape
of the call rather than its behaviour.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO / rel).read_text()


class TestTriforceButton:
    def test_the_card_hands_the_client_to_the_dialog(self):
        # A background task has an empty slot stack: ui.dialog() raised and the
        # button did nothing. check_slot_context cannot see this one because the
        # coroutine is imported, not defined beside its call site.
        source = _read('pages/home_tabs/tournaments.py')
        assert 'open_triforce_dialog(tourney, user, context.client)' in source

    def test_the_dialog_reenters_the_client(self):
        source = _read('pages/home_tabs/triforce_texts.py')
        opener = source[source.index('async def open_triforce_dialog'):]
        opener = opener[:opener.index('\nasync def ', 1)]
        assert 'with client:' in opener
