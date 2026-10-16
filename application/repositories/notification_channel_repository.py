"""Data access for a person's email / Telegram notification channels."""

from datetime import datetime, timezone
from typing import Optional

from models import ContactVerification, User


class NotificationChannelRepository:
    """The channel columns on ``User`` and the pending ``ContactVerification`` rows."""

    @staticmethod
    async def replace_verification(
        user: User, channel: str, target: Optional[str], secret_hash: str, expires_at: datetime,
    ) -> ContactVerification:
        await ContactVerification.filter(user=user, channel=channel).delete()
        return await ContactVerification.create(
            user=user, channel=channel, target=target,
            secret_hash=secret_hash, expires_at=expires_at,
        )

    @staticmethod
    async def get_verification(user: User, channel: str) -> Optional[ContactVerification]:
        return await ContactVerification.get_or_none(user=user, channel=channel)

    @staticmethod
    async def get_verification_by_hash(channel: str, secret_hash: str) -> Optional[ContactVerification]:
        return await ContactVerification.get_or_none(
            channel=channel, secret_hash=secret_hash,
        ).prefetch_related('user')

    @staticmethod
    async def count_attempt(verification: ContactVerification) -> None:
        verification.attempts += 1
        await verification.save(update_fields=['attempts'])

    @staticmethod
    async def delete_verification(verification: ContactVerification) -> None:
        await verification.delete()

    @staticmethod
    async def delete_expired() -> int:
        return await ContactVerification.filter(expires_at__lt=datetime.now(timezone.utc)).delete()

    @staticmethod
    async def set_email(user: User, email: Optional[str], enabled: bool) -> None:
        user.email = email  # type: ignore[assignment]
        user.email_verified_at = datetime.now(timezone.utc) if email else None  # type: ignore[assignment]
        user.email_notifications = enabled and email is not None
        await user.save(update_fields=['email', 'email_verified_at', 'email_notifications', 'updated_at'])

    @staticmethod
    async def set_email_notifications(user: User, enabled: bool) -> None:
        user.email_notifications = enabled
        await user.save(update_fields=['email_notifications', 'updated_at'])

    @staticmethod
    async def get_by_telegram_chat(chat_id: int) -> Optional[User]:
        return await User.get_or_none(telegram_chat_id=chat_id)

    @staticmethod
    async def set_telegram(user: User, chat_id: Optional[int], username: Optional[str]) -> None:
        user.telegram_chat_id = chat_id  # type: ignore[assignment]
        user.telegram_username = username  # type: ignore[assignment]
        user.telegram_linked_at = datetime.now(timezone.utc) if chat_id else None  # type: ignore[assignment]
        user.telegram_notifications = chat_id is not None
        await user.save(update_fields=[
            'telegram_chat_id', 'telegram_username', 'telegram_linked_at',
            'telegram_notifications', 'updated_at',
        ])

    @staticmethod
    async def set_telegram_notifications(user: User, enabled: bool) -> None:
        user.telegram_notifications = enabled
        await user.save(update_fields=['telegram_notifications', 'updated_at'])

    @staticmethod
    async def get_user(user_id: int) -> Optional[User]:
        return await User.get_or_none(id=user_id)

    @staticmethod
    async def get_by_discord_id(discord_id: int) -> Optional[User]:
        return await User.get_or_none(discord_id=discord_id, is_active=True)
