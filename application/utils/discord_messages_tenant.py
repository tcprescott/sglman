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


def join_decided_dm(
    community_name: str, approved: bool, ask_again_from: str = '', has_invite: bool = False,
) -> str:
    """DM to the requester once staff decide.

    Sent on **both** outcomes: notification that only fires on success leaves the
    other half of the people who asked wondering whether anyone saw it. A
    decline says when they can ask again (``ask_again_from`` is Discord
    ``<t:…>`` markup, so it reads in their own zone) and, when the community has
    a Discord invite, points at the button that opens it.
    """
    if approved:
        return (
            f'Your request to join **{community_name}** was approved. '
            f'You can open the community now.'
        )
    lines = [f"Your request to join **{community_name}** wasn't approved this time."]
    if ask_again_from:
        lines.append(f'You can ask again from {ask_again_from}.')
    if has_invite:
        lines.append("If you'd like to know more, ask in the community's Discord server.")
    else:
        lines.append("Reach out to the community if you'd like to know more.")
    return ' '.join(lines)


def member_added_dm(community_name: str, *, by_staff: bool) -> str:
    """DM to someone who just became a member without being approved by the queue.

    ``by_staff`` is Add Member. Otherwise it's a role grant or the Discord
    role sync, which only sends this when it closed a request they'd filed, so
    their "you'll get a message either way" promise is kept.
    """
    if by_staff:
        return f'Staff added you to **{community_name}**. You can open the community now.'
    return (
        f"You're now a member of **{community_name}**, so your request to join "
        'is closed. You can open the community now.'
    )


def member_removed_dm(community_name: str) -> str:
    """DM to someone staff removed from a community."""
    return (
        f'Staff removed you from **{community_name}**. You can no longer open its '
        "pages. Reach out to the community if you think that's a mistake."
    )


def auto_joined_dm(community_name: str, member_name: str) -> str:
    """DM to staff when someone walks in through Discord auto-join.

    The other ways in already reach staff (a request DMs them, Add Member is
    them). Without this, auto-join was the one that didn't.
    """
    return (
        f'**{member_name}** joined **{community_name}** automatically, as a member '
        "of its Discord server. They hold no roles yet."
    )
