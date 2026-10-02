"""Discord Message Templates: ADA accommodation requests

The DMs :mod:`application.services.accommodation_service` sends a community's
staff. None of them carries the member's details or the staff notes: the
feature's rule is that no free text leaves the app, and a DM is mirrored to
web-push as well. The name and the fact of the request are what staff need to
open it; the button does the rest.
"""


def accommodation_requested_dm(community_name: str, member_name: str) -> str:
    """DM to staff when a member asks for an accommodation (or asks again)."""
    return (
        f'**{member_name}** has asked **{community_name}** for an ADA accommodation. '
        'Open the request to read it and set its status.'
    )


def accommodation_changed_dm(community_name: str, member_name: str) -> str:
    """DM to staff when a member edits a request staff already arranged.

    It stays Arranged, so the proctors' icon doesn't vanish over a typo, but
    staff still need to check the arrangement covers what it now says.
    """
    return (
        f'**{member_name}** changed their ADA accommodation request in '
        f'**{community_name}** after it was arranged. It\'s still marked Arranged. '
        'Open it to see what changed and mark it reviewed.'
    )
