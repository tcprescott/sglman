"""The DM a player gets when staff leave them a comment on their match.

Enqueued on ``discord_queue`` by ``MatchCommentService``. Everything it needs is
passed in, because the queue worker awaits it outside the enqueuing request's
tenant scope.
"""

import logging
from datetime import datetime
from typing import Optional, Sequence

from application.services.discord.discord_service import DiscordService
from application.utils.discord_embeds import COLOR_RESCHEDULED, match_embed
from application.utils.discord_messages import match_comment_dm
from models import User

logger = logging.getLogger(__name__)

# Discord caps an embed description at 4096 characters; the rest of the comment
# is one tap away on the match.
_BODY_LIMIT = 1500


async def notify_match_comment(
    *,
    match_id: int,
    tournament_name: str,
    author_name: str,
    body: str,
    when: Optional[datetime],
    player_names: Sequence[str],
    recipients: Sequence[User],
) -> None:
    """DM each recipient the comment. Never raises; failures are logged."""
    from application.services import notification_links

    try:
        if len(body) > _BODY_LIMIT:
            body = body[:_BODY_LIMIT].rstrip() + '…'
        message = match_comment_dm(author_name, tournament_name, body)
        embed = match_embed(
            title='💬 Staff comment on your match',
            color=COLOR_RESCHEDULED,
            description=message,
            tournament=tournament_name,
            player_names=list(player_names),
            when=when,
        )
        link = await notification_links.player_match(match_id, label='Open the match')
        discord_service = DiscordService()
        for user in recipients:
            if not user.discord_id:
                continue
            success, err = await discord_service.send_dm(
                user.discord_id, message, embed=embed, link=link,
            )
            if not success:
                logger.warning("notify_match_comment DM failed for %s: %s", user.discord_id, err)
    except Exception:
        logger.exception("notify_match_comment unexpected error for match %s", match_id)
