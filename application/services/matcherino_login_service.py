"""
Matcherino Login Service - Business Logic Layer

The Matcherino account a community's check-in sync signs in as, replacing the
former process-wide ``MATCHERINO_REFRESH_TOKEN`` environment variable. Each
community saves the refresh token of an account that administers its own venues,
so one community's sync never reads ticket sales through another's account.

Matcherino publishes no way to mint a login for a bot, so staff copy the
refresh token out of a signed-in browser session and paste it here whenever
Matcherino stops accepting the old one. Saving checks the token against
Matcherino first: a typo or an access token pasted by mistake is refused at the
form rather than surfacing later as a failed sync at the desk.

**The token never leaves this module except into the check-in sync.**
:meth:`status` reports configured-or-not and whose account it is, never the
value; the audit entries never carry it; :meth:`resolve` is the single unmasked
read and only ``CheckInService`` calls it.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from application.feature_flags import requires_feature
from application.repositories import MatcherinoLoginRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.utils.clients.matcherino_client import (
    MAX_REFRESH_TOKEN_LENGTH,
    MatcherinoAPIError,
    MatcherinoAuthError,
    MatcherinoClient,
    get_matcherino_client,
    normalize_refresh_token,
)
from models import FeatureFlag, User

_STAFF_DENIED = 'Only staff can change the Matcherino login.'


@dataclass(frozen=True)
class MatcherinoLoginStatus:
    """What Admin → Check-in shows about the saved login. Never the token."""

    configured: bool
    matcherino_user_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class MatcherinoLoginService:
    """The per-community Matcherino login: status, save, remove, and sync-time resolution."""

    def __init__(
        self, client_factory: Callable[[Optional[str]], MatcherinoClient] = get_matcherino_client,
    ) -> None:
        self.repository = MatcherinoLoginRepository()
        self.audit_service = AuditService()
        self._client_factory = client_factory

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def status(self, actor: Optional[User]) -> MatcherinoLoginStatus:
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        login = await self.repository.get_current()
        if login is None:
            return MatcherinoLoginStatus(configured=False)
        return MatcherinoLoginStatus(
            configured=True,
            matcherino_user_id=login.matcherino_user_id,
            updated_at=login.updated_at,
            updated_by=login.updated_by.preferred_name if login.updated_by else None,
        )

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def set_login(self, actor: User, pasted: str) -> MatcherinoLoginStatus:
        """Check ``pasted`` with Matcherino, then save it as this community's login."""
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        token = normalize_refresh_token(pasted)
        if not token:
            raise ValueError('Paste the refresh token first.')
        if len(token) > MAX_REFRESH_TOKEN_LENGTH or any(c.isspace() for c in token):
            raise ValueError("That doesn't look like a Matcherino refresh token.")
        try:
            account_id = await self._client_factory(token).verify_login()
        except MatcherinoAuthError as e:
            raise ValueError(
                "Matcherino didn't accept that token. Copy refreshToken (not accessToken) "
                'from a session that is still signed in, then try again.'
            ) from e
        except MatcherinoAPIError as e:
            raise ValueError(f"Couldn't check that token with Matcherino: {e}") from e

        previous = await self.repository.get_current()
        await self.repository.upsert(token, account_id, actor)
        await self.audit_service.write_log(
            actor, AuditActions.MATCHERINO_LOGIN_SET,
            {
                'replaced': previous is not None,
                'matcherino_user_id': account_id,
                'previous_matcherino_user_id': previous.matcherino_user_id if previous else None,
            },
        )
        return await self.status(actor)

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def clear_login(self, actor: User) -> None:
        """Remove the saved login. Idempotent: clearing an unset one is a no-op."""
        await AuthService.ensure(await AuthService.can_manage_check_in(actor), _STAFF_DENIED)
        previous = await self.repository.get_current()
        if previous is None:
            return
        await self.repository.delete_current()
        await self.audit_service.write_log(
            actor, AuditActions.MATCHERINO_LOGIN_CLEARED,
            {'matcherino_user_id': previous.matcherino_user_id},
        )

    @requires_feature(FeatureFlag.EVENT_CHECK_IN)
    async def resolve(self) -> Optional[str]:
        """The saved refresh token, unmasked.

        The one path that returns the token, and deliberately not role-gated:
        its only caller is ``CheckInService``, whose own boundary already
        authorized the actor (the sync worker runs as the system user). Never
        call it from a page, router, or anything that renders.
        """
        login = await self.repository.get_current()
        return login.refresh_token if login else None
