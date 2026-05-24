from typing import List, Optional

from models import MatchNotificationLevel, TournamentNotificationPreference, Tournament, User


class TournamentNotificationRepository:
    """Repository for TournamentNotificationPreference data access."""

    async def get_by_user_and_tournament(self, user: User, tournament: Tournament) -> Optional[TournamentNotificationPreference]:
        return await TournamentNotificationPreference.get_or_none(user=user, tournament=tournament)

    async def get_all_for_user(self, user: User) -> List[TournamentNotificationPreference]:
        return await TournamentNotificationPreference.filter(user=user).prefetch_related('tournament').all()

    async def upsert(
        self,
        user: User,
        tournament: Tournament,
        match_notifications: MatchNotificationLevel,
    ) -> TournamentNotificationPreference:
        pref, _ = await TournamentNotificationPreference.get_or_create(
            user=user,
            tournament=tournament,
        )
        pref.match_notifications = match_notifications
        await pref.save()
        return pref

    async def get_match_notification_subscribers(self, tournament_id: int, has_stream_room: bool) -> List[User]:
        """
        Return users who qualify for a match-scheduled notification.

        'all' subscribers always qualify.
        'streamed' and 'streamed_and_candidates' subscribers only qualify when the match
        has a stream room assigned.
        """
        if has_stream_room:
            qualifying_levels = [
                MatchNotificationLevel.ALL,
                MatchNotificationLevel.STREAMED,
                MatchNotificationLevel.STREAMED_AND_CANDIDATES,
            ]
        else:
            qualifying_levels = [MatchNotificationLevel.ALL]

        prefs = await TournamentNotificationPreference.filter(
            tournament_id=tournament_id,
            match_notifications__in=qualifying_levels,
        ).prefetch_related('user').all()

        return [
            p.user for p in prefs
            if p.user.discord_id and p.user.dm_notifications
        ]

    async def get_stream_candidate_subscribers(self, tournament_id: int) -> List[User]:
        """Return users who opted in to stream candidate alerts."""
        prefs = await TournamentNotificationPreference.filter(
            tournament_id=tournament_id,
            match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES,
        ).prefetch_related('user').all()

        return [
            p.user for p in prefs
            if p.user.discord_id and p.user.dm_notifications
        ]
