"""Discord Message Templates: community events

The DMs :mod:`application.services.community_event_service` and its reminder
worker send. Each one is also the web-push text, so it reads on its own; the
embed beside it carries the time as native ``<t:…>`` markup so every recipient
sees their own clock.
"""


def submitted_to_staff_dm(community_name: str, host_name: str, title: str) -> str:
    """DM to staff when a member submits an event, or resubmits a rejected one."""
    return (
        f'**{host_name}** submitted **{title}** to the community events listing for '
        f'**{community_name}**. Open it to approve or reject it.'
    )


def approved_dm(community_name: str, title: str) -> str:
    """DM to the host when staff approve their event."""
    return (
        f'**{title}** is approved and now listed in **{community_name}**\'s community '
        'events. Members can subscribe to it for a reminder before it starts.'
    )


def rejected_dm(community_name: str, title: str, reason: str, was_listed: bool) -> str:
    """DM to the host when staff reject their event or take a listed one down."""
    what = 'was taken off' if was_listed else "wasn't approved for"
    return (
        f'**{title}** {what} **{community_name}**\'s community events listing.\n'
        f'Reason from staff: {reason}\n'
        'You can edit it and submit it again.'
    )


def reminder_dm(title: str, starts_display: str, location: str | None) -> str:
    """DM to a subscriber shortly before an event starts."""
    where = f' at {location}' if location else ''
    return f'**{title}** starts {starts_display}{where}.'


def time_changed_dm(title: str, starts_display: str) -> str:
    """DM to subscribers when the host or staff move an approved event."""
    return f'**{title}** has moved. It now starts {starts_display}.'


def cancelled_dm(title: str) -> str:
    """DM to subscribers when an approved event is called off or taken down."""
    return f'**{title}** has been cancelled, so you won\'t get a reminder for it.'
