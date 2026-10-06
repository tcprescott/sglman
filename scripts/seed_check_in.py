"""Dev seed for event check-in.

Runs the real ``CheckInService`` sync against the MOCK_MATCHERINO venue
(``MOCK_TIERS`` and ``MOCK_PURCHASES``), so the dev database holds what a sync
actually produces (the ``CheckInTier`` and ``CheckInPass`` rows come from that
sync, not from inserts here) and pressing Sync in dev changes nothing. The sales
are lined up with fixtures (see the comment above ``MOCK_PURCHASES``) so that one
sync yields every link method the sync still produces, all four badge types, a
buyer holding two badges and a refunded buyer; on top of it the desk is put into
the states a volunteer meets:

* ``Player Three`` linked to player_three by hand, several buyers unlinked;
* jemgold and blueshell link to player_one and player_two, whose published
  shifts from ``seed_volunteers`` give them the Volunteer chip; player_three's
  only shift is an unpublished draft, so Player Three gets none;
* someone whose badge disappeared from the venue (withdrawn);
* player_one already checked in by the check-in desk volunteer;
* two walk-ups checked in by staff, one a member (racer_09) and one name-only;
* a draft event with no venue and last year's closed event, for the admin list.

Idempotent: re-running syncs again (a no-op against the same roster) and skips
anything already in place. Only tenants with check-in live get rows — the
service refuses the rest, which is the point of the flag.
"""

from datetime import datetime, timezone

from application.services.check_in_service import CheckInService
from application.services.feature_flag_service import FeatureFlagService, reset_flag_cache
from application.utils.clients.matcherino_client import (
    MOCK_REMEMBERED_ID,
    MOCK_TWITCH_RACER_ID,
    MockMatcherinoClient,
)
from models import (
    CheckInEntrant,
    CheckInEntrantSource,
    CheckInEvent,
    CheckInEventStatus,
    FeatureFlag,
    Tenant,
    User,
)
from scripts.seed_support import backfill

LIVE_EVENT = 'Wizzrobe Live — Check-in'
DRAFT_EVENT = 'Spring Meetup (walk-ups only)'
CLOSED_EVENT = 'Wizzrobe Live 2025'
VENUE_ID = 900100
WITHDRAWN_ID = '900099'


async def seed_check_in_identities(users: dict[str, User]) -> None:
    """Give two racers the identifiers the mock sales match on. Global."""
    await backfill(users['racer_05'], matcherino_user_id=str(MOCK_REMEMBERED_ID))
    await backfill(users['racer_07'], twitch_user_id=MOCK_TWITCH_RACER_ID)
    print('  check-in identities ok (racer_05/07 match the mock Matcherino sales)')


async def seed_check_in_for_tenant(tenant: Tenant, users: dict[str, User]) -> None:
    reset_flag_cache()
    if not await FeatureFlagService().is_enabled(FeatureFlag.EVENT_CHECK_IN):
        print(f'    [{tenant.slug}] check-in skipped (feature not live here)')
        return

    staff, desk = users['staff_user'], users['checkin_desk']
    service = CheckInService(client=MockMatcherinoClient())

    event = await CheckInEvent.get_or_none(tenant=tenant, name=LIVE_EVENT)
    if event is None:
        event = await service.create_event(
            staff, LIVE_EVENT, venue_id=VENUE_ID, status=CheckInEventStatus.OPEN,
        )
    if not await CheckInEntrant.exists(event=event, matcherino_user_id=WITHDRAWN_ID):
        await CheckInEntrant.create(
            tenant=tenant, event=event, source=CheckInEntrantSource.MATCHERINO,
            matcherino_user_id=WITHDRAWN_ID, display_name='Changed Their Mind',
            auth_provider='gplus',
            withdrawn_at=datetime.now(timezone.utc),
        )
    await service.sync_event(staff, event.id, audit=False)

    roster = await service.roster(event)
    rows = {row.matcherino_user_id: row for row in roster if row.matcherino_user_id}
    manual = rows.get('900003')
    if manual is not None and manual.user_id is None and manual.link_method is None:
        await service.link(staff, manual.id, users['player_three'].id)
    first = rows.get('100234')
    if first is not None and first.checked_in_at is None:
        await service.check_in(desk, first.id)
    if not any(row.user_id == users['racer_09'].id for row in roster):
        await service.add_walk_up(staff, event.id, user_id=users['racer_09'].id)
    if not any(row.display_name == 'Walk-in Wendy' for row in roster):
        await service.add_walk_up(staff, event.id, name='Walk-in Wendy')

    if not await CheckInEvent.exists(tenant=tenant, name=DRAFT_EVENT):
        await service.create_event(staff, DRAFT_EVENT)
    if not await CheckInEvent.exists(tenant=tenant, name=CLOSED_EVENT):
        await service.create_event(staff, CLOSED_EVENT, status=CheckInEventStatus.CLOSED)
    print(f'    [{tenant.slug}] check-in ok (open event with synced badge sales, a draft, a closed one)')
