"""The words the ADA accommodation surfaces use, in one place.

The profile card and the staff panel both describe a request's status and both
show the privacy disclaimer; keeping that copy here means the requester and
staff never read the same row two different ways. Pure, so it is testable
without a client.
"""

from models import AccommodationStatus

__all__ = ['STATUS_CHIP', 'STATUS_LABELS', 'privacy_disclaimer']

STATUS_LABELS: dict[AccommodationStatus, str] = {
    AccommodationStatus.NEW: 'New',
    AccommodationStatus.ACKNOWLEDGED: 'Acknowledged',
    AccommodationStatus.ARRANGED: 'Arranged',
    AccommodationStatus.WITHDRAWN: 'Withdrawn',
}

#: ``wiz-chip`` modifier per status (see static/css/styles.css).
STATUS_CHIP: dict[AccommodationStatus, str] = {
    AccommodationStatus.NEW: 'wiz-chip--pending',
    AccommodationStatus.ACKNOWLEDGED: 'wiz-chip--live',
    AccommodationStatus.ARRANGED: 'wiz-chip--ok',
    AccommodationStatus.WITHDRAWN: 'wiz-chip--neutral',
}


def privacy_disclaimer(community: str) -> str:
    """The warning shown wherever accommodation details are written or read."""
    staff = f'{community} staff' if community else 'community staff'
    return (
        f'Only {staff} can see these notes, but we can\'t guarantee they stay '
        'private. Please don\'t put anything sensitive or personal here. If it '
        f'is sensitive, contact {staff} directly instead.'
    )
