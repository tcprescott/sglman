"""A filtered match board keeps its own row set as changes arrive.

``row_filter`` is not the operator's State chip — it defines what the board *is*.
The tournament-room view shows rolled seeds for unplayed matches, so two live
transitions have to work in opposite directions: a match that starts leaves the
screen, and a match that gets a seed appears on it. The second is the subtle
one, because rolling a seed publishes ``changed`` (not ``CREATED``) for a match
the board has never had a row for, which a plain in-place update would no-op.
"""

from types import SimpleNamespace

from application.events import match_live
from application.services.match.match_display_service import is_seeded_and_unplayed
from theme.tables.match import MatchTableView


class _Table:
    def __init__(self, rows):
        self.rows = rows
        self.updated = 0

    def update(self):
        self.updated += 1


def _view(rows, *, fetched=None):
    """A MatchTableView with only the pieces these paths touch."""
    view = object.__new__(MatchTableView)
    view.table = _Table(list(rows))
    view.row_filter = is_seeded_and_unplayed
    view.on_rows_changed = None
    view.on_set_stage = None
    view.refreshed = 0
    # The row-flash timer needs a live slot context, which none of these paths
    # has; the highlight is not what is under test.
    view._schedule_flash_clear = lambda _match_id: None

    async def _refresh(*_args):
        view.refreshed += 1

    view.refresh = _refresh
    view.display_service = SimpleNamespace(
        get_match_for_display=_returning(fetched),
    )
    return view


def _returning(value):
    async def _get(_match_id):
        return value
    return _get


SEEDED = {'id': 1, 'generated_seed': 'https://alttpr.com/h/abc', 'state': 'Scheduled'}
STARTED = {'id': 1, 'generated_seed': 'https://alttpr.com/h/abc', 'state': 'Started'}
UNSEEDED = {'id': 2, 'generated_seed': '', 'state': 'Scheduled'}


class TestUpdateRow:
    async def test_a_match_that_starts_leaves_the_board(self):
        view = _view([SEEDED], fetched=STARTED)

        await view.update_row_by_id(1)

        assert view.table.rows == []

    async def test_a_row_that_still_qualifies_updates_in_place(self):
        refreshed = dict(SEEDED, stage='Stage 1')
        view = _view([SEEDED], fetched=refreshed)

        await view.update_row_by_id(1)

        assert view.table.rows == [refreshed]


class TestRemoteChange:
    async def test_a_seed_rolled_for_an_unlisted_match_refreshes_the_board(self):
        view = _view([SEEDED], fetched=None)

        await view._on_remote_change(99, match_live.CHANGED)

        assert view.refreshed == 1

    async def test_a_change_to_a_listed_row_does_not_refetch_the_board(self):
        view = _view([SEEDED], fetched=SEEDED)

        await view._on_remote_change(1, match_live.CHANGED)

        assert view.refreshed == 0

    async def test_a_new_match_always_refreshes(self):
        view = _view([SEEDED], fetched=None)

        await view._on_remote_change(5, match_live.CREATED)

        assert view.refreshed == 1


class TestPredicateOnBoardRows:
    def test_the_room_board_shows_only_rolled_unplayed_matches(self):
        assert [r for r in (SEEDED, STARTED, UNSEEDED) if is_seeded_and_unplayed(r)] == [SEEDED]
