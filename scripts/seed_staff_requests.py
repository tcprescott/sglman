"""Dev seed: remembered staff request DMs (see application/services/staff_request_dms.py)."""

from models import (
    AccommodationRequest,
    AccommodationStatus,
    CommunityEvent,
    CommunityEventStatus,
    MatchRescheduleRequest,
    StaffRequestDM,
    StaffRequestKind,
    Tenant,
    TenantJoinRequest,
    User,
)


async def seed_staff_request_dms(tenant: Tenant, users: dict[str, User]) -> None:
    """One remembered staff DM per request kind, so deciding a seeded request in
    mock mode prints the ``[MOCK Discord DM edit]`` line. The ids are made up:
    a mock edit never reaches Discord."""
    staff = users['staff_user']
    targets = (
        (StaffRequestKind.COMMUNITY_EVENT, CommunityEvent.filter(
            tenant=tenant, status=CommunityEventStatus.PENDING)),
        (StaffRequestKind.ADA_REQUEST, AccommodationRequest.filter(
            tenant=tenant, status=AccommodationStatus.NEW)),
        (StaffRequestKind.JOIN_REQUEST, TenantJoinRequest.filter(tenant=tenant)),
        (StaffRequestKind.RESCHEDULE_REQUEST, MatchRescheduleRequest.filter(tenant=tenant)),
    )
    for n, (kind, query) in enumerate(targets, start=1):
        target = await query.order_by('id').first()
        if target is None:
            continue
        await StaffRequestDM.get_or_create(
            tenant=tenant, kind=kind, object_id=target.id, user=staff,
            defaults={'channel_id': int(staff.discord_id or 0),
                      'message_id': 900_000_000 + tenant.id * 10 + n},
        )
