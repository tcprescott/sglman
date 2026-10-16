"""The service account's Challonge grants, mixed into ``ChallongeService``.

Challonge hides brackets outside the community an OAuth grant names, so a
tenant keeps one grant per community plus one with none, and each bracket's
calls use the grant for the community it lives in.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from application.repositories import ChallongeRepository
from application.utils.clients.challonge_client import ChallongeAPIError, ChallongeClient
from models import ChallongeConnection

# Refresh the service token slightly before it actually expires.
_TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


def _as_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Treat naive datetimes (e.g. from a non-tz DB) as UTC so comparisons are safe."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class ChallongeGrantsMixin:
    """Collaborators come from ``ChallongeService``; see its ``__init__``."""

    repository: ChallongeRepository
    _oauth_client: Callable[[], ChallongeClient]

    async def get_valid_access_token(
        self, force_refresh: bool = False, community: Optional[str] = None,
    ) -> str:
        """Return a live service access token for ``community``, refreshing if expired/forced.

        Challonge hides brackets outside the community a grant names, so each
        bracket's calls use the grant for the community it lives in.
        """
        connection = await self.repository.get_connection_for(community)
        if connection is None:
            raise ValueError("Challonge is not connected. A staff member must connect the Wizzrobe account.")

        if not force_refresh and not self._token_expiring(connection):
            return connection.access_token

        if not connection.refresh_token:
            if force_refresh:
                raise ValueError("Challonge token expired and no refresh token is available; reconnect required.")
            return connection.access_token

        payload = await self._oauth_client().refresh(connection.refresh_token)
        access, refresh, expires_at = self._unpack_token(payload)
        await self.repository.update_connection_tokens(connection, access, refresh, expires_at)
        return access

    @staticmethod
    def _token_expiring(connection: ChallongeConnection) -> bool:
        expires = _as_aware_utc(connection.token_expires_at)
        if expires is None:
            return False
        return datetime.now(timezone.utc) >= (expires - _TOKEN_REFRESH_BUFFER)

    @staticmethod
    def _unpack_token(payload: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[datetime]]:
        access = payload.get('access_token')
        if not access:
            raise ChallongeAPIError(f"Challonge token response missing access_token: {payload}")
        refresh = payload.get('refresh_token')
        expires_in = payload.get('expires_in')
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in else None
        )
        return access, refresh, expires_at

    async def _not_found_message(self, identifier: str, community: Optional[str]) -> str:
        connection = await self.repository.get_connection()
        account = (connection.challonge_username if connection else None) or 'the connected account'
        message = f"Challonge can't find '{identifier}' for {account}."
        if (community or '') not in await self.repository.granted_communities():
            where = f"the '{community}' community" if community else 'brackets outside a community'
            return (
                f"{message} Wizzrobe hasn't been granted {where} yet. Reconnect in "
                f"Admin → Challonge, approve every Challonge prompt, then try again."
            )
        return (
            f"{message} Check the URL. Challonge only lets Wizzrobe read brackets {account} "
            f"created or that live in a connected community; being an admin on someone "
            f"else's bracket isn't enough, so its owner needs to move it into a community."
        )
