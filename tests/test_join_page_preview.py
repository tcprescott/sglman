"""What the join page shows someone who is not a member yet.

Two previews with different rules. Published brackets are already world-readable
pages, so the door just makes them reachable — no opt-in, only the BRACKETS
feature gate. Today's matches are the opposite: names and times are exactly what
the membership gate was added to keep from a stranger, so they appear only where
staff turned the preview on, and on the community's own clock rather than the
reader's.

``resolve_join_preview`` is plain async Python — the rendering half is covered
by the browser loop, not here.
"""

from datetime import time
from types import SimpleNamespace

from application.services.feature_flag_service import reset_flag_cache
from application.services.system_config_service import KEY_JOIN_PREVIEW, SystemConfigService
from application.tenant_context import tenant_scope
from models import (
    Bracket,
    BracketFormat,
    BracketState,
    FeatureFlag,
    GeneratedSeeds,
    Match,
    MatchPlayers,
    Role,
    SystemConfiguration,
    TenantFeatureFlag,
    Tournament,
    User,
    UserRole,
)
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.factories import make_user
from theme.join_page import PREVIEW_LIMIT, resolve_join_preview, roster_label


async def _staff() -> User:
    user = await make_user(discord_id=7001, username='staff-join')
    await UserRole.create(user=user, role=Role.STAFF, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


def _fake_match(names: list[str], title: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        players=[SimpleNamespace(user=SimpleNamespace(preferred_name=n)) for n in names],
        title=title,
    )


async def _match_today(tournament: Tournament, hour: int = 19) -> Match:
    from application.utils.timezone import combine_local, today_local

    match = await Match.create(
        tournament=tournament,
        scheduled_at=combine_local(today_local(), time(hour, 0)),
        generated_seed=await GeneratedSeeds.create(
            seed_url='https://alttpr.com/h/abcd1234', generator='alttpr',
        ),
    )
    for n in (1, 2):
        player = await make_user(discord_id=7100 + match.id * 10 + n,
                                 username=f'p{match.id}-{n}',
                                 display_name=f'Player {match.id}-{n}')
        await MatchPlayers.create(match=match, user=player)
    return match


class TestMatchPreview:
    async def test_off_by_default(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            tournament = await Tournament.create(name='Cup')
            await _match_today(tournament)

            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.matches_enabled is False
        assert preview.matches == []

    async def test_on_lists_todays_matches_with_names(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await SystemConfigService.set_raw(KEY_JOIN_PREVIEW, 'true', await _staff())
            tournament = await Tournament.create(name='Cup')
            await _match_today(tournament)

            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.matches_enabled is True
        assert len(preview.matches) == 1
        row = preview.matches[0]
        assert ' vs ' in row.players
        assert row.tournament == 'Cup'
        assert row.time
        assert preview.timezone_label

    async def test_on_with_nothing_scheduled_says_so_rather_than_nothing(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await SystemConfigService.set_raw(KEY_JOIN_PREVIEW, 'true', await _staff())
            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.matches_enabled is True
        assert preview.matches == []

    async def test_a_junk_value_reads_as_off(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await SystemConfiguration.create(
                name=KEY_JOIN_PREVIEW, value='perhaps', tenant_id=DEFAULT_TEST_TENANT_ID,
            )
            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.matches_enabled is False


class TestRosterLabel:
    """A door is not a schedule board: one line per match, and it stays one line."""

    def test_two_players_read_as_a_matchup(self):
        assert roster_label(_fake_match(['Alice', 'Bob'])) == 'Alice vs Bob'

    def test_a_long_roster_is_counted_rather_than_listed(self):
        names = [f'Racer {n}' for n in range(1, 11)]
        assert roster_label(_fake_match(names)) == 'Racer 1 vs Racer 2 +8 more'

    def test_an_empty_roster_falls_back_to_the_title(self):
        assert roster_label(_fake_match([], title='Grand Finals')) == 'Grand Finals'
        assert roster_label(_fake_match([], title=None)) == 'TBD'


class TestPreviewLimit:
    async def test_beyond_the_limit_the_rest_are_counted(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await SystemConfigService.set_raw(KEY_JOIN_PREVIEW, 'true', await _staff())
            tournament = await Tournament.create(name='Cup')
            for _ in range(PREVIEW_LIMIT + 3):
                await _match_today(tournament)

            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert len(preview.matches) == PREVIEW_LIMIT
        assert preview.more_matches == 3

    async def test_a_finished_match_is_not_todays_news(self, db):
        from application.utils.timezone import combine_local, today_local

        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            await SystemConfigService.set_raw(KEY_JOIN_PREVIEW, 'true', await _staff())
            tournament = await Tournament.create(name='Cup')
            done = await _match_today(tournament, hour=9)
            done.finished_at = combine_local(today_local(), time(10, 0))
            await done.save()

            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.matches == []


class TestBracketPreview:
    async def test_published_stages_are_listed_once_per_tournament(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            tournament = await Tournament.create(name='Cup')
            for order, name in enumerate(('Group Stage', 'Playoffs')):
                await Bracket.create(
                    tournament=tournament, name=name, stage_order=order,
                    format=BracketFormat.SINGLE_ELIM, state=BracketState.ACTIVE,
                )
            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.tournaments == [(tournament.id, 'Cup')]

    async def test_unpublished_stages_stay_hidden(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            tournament = await Tournament.create(name='Cup')
            await Bracket.create(
                tournament=tournament, name='Seeding draft',
                format=BracketFormat.SINGLE_ELIM, state=BracketState.DRAFT,
            )
            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.tournaments == []

    async def test_nothing_is_listed_when_brackets_is_off(self, db):
        with tenant_scope(DEFAULT_TEST_TENANT_ID):
            tournament = await Tournament.create(name='Cup')
            await Bracket.create(
                tournament=tournament, name='Playoffs',
                format=BracketFormat.SINGLE_ELIM, state=BracketState.ACTIVE,
            )
            await TenantFeatureFlag.filter(
                tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.BRACKETS.value,
            ).update(enabled=False)
            reset_flag_cache()

            preview = await resolve_join_preview(DEFAULT_TEST_TENANT_ID)

        assert preview.tournaments == []
