from datetime import datetime, timezone
from typing import List, Optional

from tortoise.exceptions import IntegrityError

from models import User, WebPushSubscription


class WebPushRepository:
    """Repository for WebPushSubscription data access."""

    async def get_by_endpoint(self, endpoint: str) -> Optional[WebPushSubscription]:
        return await WebPushSubscription.get_or_none(endpoint=endpoint)

    async def get_by_id(self, subscription_id: int) -> Optional[WebPushSubscription]:
        return await WebPushSubscription.get_or_none(id=subscription_id)

    async def list_for_user(self, user: User) -> List[WebPushSubscription]:
        return await WebPushSubscription.filter(user=user).order_by('created_at').all()

    async def list_for_discord_id(self, discord_id: int) -> List[WebPushSubscription]:
        return await WebPushSubscription.filter(user__discord_id=discord_id).all()

    async def upsert(
        self,
        user: User,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: Optional[str],
    ) -> WebPushSubscription:
        # A browser can re-subscribe with an endpoint we already hold (page
        # reload, or a different account logging in on the same device) — the
        # endpoint uniquely identifies the device subscription, so the row is
        # reassigned rather than duplicated.
        subscription = await self.get_by_endpoint(endpoint)
        if subscription is None:
            try:
                return await WebPushSubscription.create(
                    user=user, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent
                )
            except IntegrityError:
                # Lost a check-then-insert race on the unique endpoint
                # (double-click subscribing) — update the row that won.
                subscription = await self.get_by_endpoint(endpoint)
                if subscription is None:
                    raise
        subscription.user = user
        subscription.p256dh = p256dh
        subscription.auth = auth
        subscription.user_agent = user_agent
        await subscription.save()
        return subscription

    async def delete(self, subscription: WebPushSubscription) -> None:
        await subscription.delete()

    async def delete_by_endpoint(self, endpoint: str) -> int:
        return await WebPushSubscription.filter(endpoint=endpoint).delete()

    async def touch_last_used(self, subscription: WebPushSubscription) -> None:
        subscription.last_used_at = datetime.now(timezone.utc)
        await subscription.save(update_fields=['last_used_at'])
