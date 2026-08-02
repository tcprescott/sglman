"""Tournament signup — the player's own way in, and out.

Signing up used to be a checkbox on the Profile tab with no window, no
membership check and no event: the UI listed every active tournament in the
tenant and enrolled whoever ticked a box. Everything that makes it a real
opt-in lives here — the window check, the membership gate, the Challonge
carve-out, and the audit-plus-event pair every enrolment change shares,
whoever made it.

Mixed into :class:`~application.services.tournament_service.TournamentService`
— the same composition ``application/services/_bracket/`` and the async
qualifier use — so the orchestration module stays inside the file-length
guideline.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from application.events import EventType
from application.repositories import TournamentRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.tenant_membership_service import TenantMembershipService
from application.utils.discord_embeds import COLOR_SCHEDULED
from application.utils.tournament_signup import SignupWindow, signup_window_state
from models import FeatureFlag, Tournament, User

logger = logging.getLogger(__name__)

# Blurple, the same informational tone the join-request and crew DMs use — a
# signup confirmation is news, not something to act on.
COLOR_SIGNUP = COLOR_SCHEDULED


@dataclass
class TournamentSignupCard:
    """One tournament as the Tournaments tab, REST and MCP all describe it.

    A single shape because the three surfaces have to agree about what "you can
    sign up for this" means: the tab drawing a Sign up button the API would
    refuse is the exact bug that the enrollment checkbox had, only louder.
    """

    tournament: Tournament
    window: SignupWindow
    enrolled: bool
    entrant_count: int
    entrants: List[User] = field(default_factory=list)
    # Roster comes from a synced Challonge bracket, so nobody signs up here.
    challonge_managed: bool = False

    @property
    def can_sign_up(self) -> bool:
        return (
            not self.enrolled
            and not self.challonge_managed
            and self.window is SignupWindow.OPEN
        )

    @property
    def can_withdraw(self) -> bool:
        return (
            self.enrolled
            and not self.challonge_managed
            and self.window is SignupWindow.OPEN
        )


class TournamentSignupMixin:
    """Player self-service signup, mixed into ``TournamentService``.

    The two collaborators below are set up by the host's ``__init__``; they are
    annotated here so this module type-checks on its own rather than relying on
    whoever mixes it in.
    """

    repository: TournamentRepository
    audit_service: AuditService

    async def _challonge_managed_ids(self) -> set[int]:
        """Tournaments whose roster is driven by a synced Challonge bracket.

        Empty when the community has the feature off, so a leftover
        ``challonge_tournament_id`` on a tenant that has since disabled Challonge
        does not silently freeze a tournament nobody can sign up for.
        """
        from application.services.feature_flag_service import FeatureFlagService

        if FeatureFlag.CHALLONGE not in await FeatureFlagService().enabled_flags():
            return set()
        rows = await self.repository.get_all(active_only=False)
        return {t.id for t in rows if t.challonge_tournament_id}

    async def list_signup_cards(
        self, user: Optional[User] = None, now: Optional[datetime] = None,
    ) -> List[TournamentSignupCard]:
        """Every active tournament, with this viewer's signup state on each.

        One place resolves the window, the enrolment and the entrant list, so the
        tab, the REST payload and the MCP tool cannot describe the same
        tournament differently.
        """
        tournaments = await self.repository.get_all(active_only=True)
        if not tournaments:
            return []
        ids = [t.id for t in tournaments]
        counts = await self.repository.enrolment_counts()
        entrants = await self.repository.entrants_by_tournament(ids)
        enrolled_ids = (
            await self.repository.enrolled_tournament_ids(user.id) if user else set()
        )
        challonge_ids = await self._challonge_managed_ids()
        return [
            TournamentSignupCard(
                tournament=t,
                window=signup_window_state(t.signups_open_at, t.signups_close_at, now),
                enrolled=t.id in enrolled_ids,
                entrant_count=counts.get(t.id, 0),
                entrants=entrants.get(t.id, []),
                challonge_managed=t.id in challonge_ids,
            )
            for t in tournaments
        ]

    async def _signup_target(self, tournament_id: int) -> Tournament:
        """Load a tournament a player may act on, or say why they may not."""
        tournament = await self.repository.get_by_id(tournament_id)
        if tournament is None or not tournament.is_active:
            raise ValueError('That tournament is not accepting signups.')
        if tournament.id in await self._challonge_managed_ids():
            raise ValueError(
                f'{tournament.name} takes its roster from its Challonge bracket — '
                'link your Challonge account instead.'
            )
        state = signup_window_state(tournament.signups_open_at, tournament.signups_close_at)
        if state is SignupWindow.UPCOMING:
            raise ValueError(f'Signups for {tournament.name} have not opened yet.')
        if state is SignupWindow.CLOSED:
            raise ValueError(
                f'Signups for {tournament.name} are closed. Ask staff if you still want in.'
            )
        return tournament

    async def self_enroll(self, tournament_id: int, user: User) -> Tournament:
        """Sign the caller up for a tournament, from the Tournaments tab.

        The membership check is the one the Profile-tab checkbox never had: it
        listed every active tournament in the tenant and enrolled whoever ticked
        a box, with no gate at all between the widget and the row.
        """
        tournament = await self._signup_target(tournament_id)
        if not await TenantMembershipService().is_member(user):
            raise ValueError('Join this community before signing up for its tournaments.')
        if await self.repository.is_player_enrolled(tournament, user):
            raise ValueError(f'You are already signed up for {tournament.name}.')
        await self.repository.enroll_player(tournament, user)
        await self._record_enrolment(user, user, tournament, added=True)
        await self._notify_signup(user, tournament)
        return tournament

    async def self_withdraw(self, tournament_id: int, user: User) -> Tournament:
        """Withdraw the caller, while the signup window is still open.

        Once it closes, withdrawing is staff's call — a roster the bracket has
        already been seeded from should not lose an entrant silently.
        """
        tournament = await self._signup_target(tournament_id)
        if not await self.repository.is_player_enrolled(tournament, user):
            raise ValueError(f'You are not signed up for {tournament.name}.')
        await self.repository.unenroll_player(tournament, user)
        await self._record_enrolment(user, user, tournament, added=False)
        return tournament

    async def _record_enrolment(
        self, actor: User, target: User, tournament: Tournament, *, added: bool,
    ) -> None:
        """The audit row and the event every enrolment change shares.

        Deliberately the same audit action for all four screens that can make
        this change — the Tournaments tab, the roster dialog, the admin user
        dialog and the match dialog's auto-enrol — because it is one fact reached
        from several places. The event splits by direction, since a subscriber
        mirroring a roster needs to know which way it moved.
        """
        details = {
            'target_user_id': target.id,
            'added_tournament_ids': [tournament.id] if added else [],
            'removed_tournament_ids': [] if added else [tournament.id],
        }
        await self.audit_service.write_and_publish(
            actor,
            AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED,
            details,
            EventType.TOURNAMENT_ENROLLED if added else EventType.TOURNAMENT_WITHDRAWN,
            event_extra={'tournament_id': tournament.id, 'user_id': target.id},
        )

    async def _notify_signup(self, user: User, tournament: Tournament) -> None:
        """Confirm a signup by DM, with a button back to the tab that made it.

        Best-effort: a Discord outage must not undo an enrolment that already
        committed, so every failure below is swallowed.
        """
        if not user.discord_id:
            return
        try:
            from application.services import notification_links
            from application.services.discord import DiscordService, discord_queue
            from application.services.tenant_service import TenantService
            from application.utils.discord_embeds import notification_embed

            community = await TenantService.current_community_name()
            body = (
                f"You're signed up for **{tournament.name}**. "
                'Staff can now schedule you into its matches.'
            )
            embed = notification_embed(
                title='🏁 Signed up',
                color=COLOR_SIGNUP,
                community_name=community,
                description=body,
            )
            link = await notification_links.home_tournaments()
            discord_queue.enqueue(
                DiscordService().send_dm(
                    int(user.discord_id), body, embed=embed, link=link,
                )
            )
        except Exception:
            logger.exception('tournament signup DM failed for user %s', user.id)

