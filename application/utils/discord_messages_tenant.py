"""Discord Message Templates: community membership

The DM copy for :mod:`application.services.tenant_membership_service` — the ask
that reaches a community's staff, and the answer that goes back to whoever
asked.

A sibling of :mod:`application.utils.discord_messages` rather than more lines in
it, on the same rule the qualifier and reschedule copy already follow: joining a
community is a domain of its own, and the parent module holds the match
lifecycle. The convention is otherwise identical — all Discord text lives in a
builder, and none of it is inlined in service or handler code.
"""


def join_requested_dm(community_name: str, requester_name: str, message: str = '') -> str:
    """DM to a community's staff when someone asks to join.

    A request nobody sees is worse than no request, which is why this exists at
    all — the staff queue alone would be a page nobody visits.
    """
    lines = [f'**{requester_name}** has asked to join **{community_name}**.']
    if message:
        lines.append(f'> {message}')
    lines.append('Approve or deny it on the Users tab.')
    return '\n\n'.join(lines)


def join_decided_dm(community_name: str, approved: bool) -> str:
    """DM to the requester once staff decide.

    Sent on **both** outcomes: notification that only fires on success leaves the
    other half of the people who asked wondering whether anyone saw it.
    """
    if approved:
        return (
            f'Your request to join **{community_name}** was approved. '
            f'You can open the community now.'
        )
    return (
        f"Your request to join **{community_name}** wasn't approved this time. "
        f"Reach out to the community if you'd like to know more."
    )
