"""Discord Message Templates: event check-in

The DM :mod:`application.services.matcherino_login_service` sends the person a
community picked to hear when Matcherino stops accepting its saved login. It
never carries the token, only that the login needs replacing and why.
"""


def matcherino_login_refused_dm(community_name: str, reason: str) -> str:
    """DM when a check-in sync is refused by Matcherino.

    ``reason`` is the client's own message, which names the setting but never
    the secret.
    """
    return (
        f"**{community_name}**'s check-in can't read badge sales right now. The desk keeps its "
        f'current roster until a fresh token is saved.\n\n{reason}'
    )
