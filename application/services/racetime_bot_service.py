"""Racetime Bot Service — platform administration of shared racetime bots.

A :class:`~models.RacetimeBot` is **global** (like the Discord token / VAPID
keys): one bot per game category, holding that category's OAuth credentials.
Only SUPER_ADMIN may manage them, and every mutation runs on ``/platform`` with
*no* tenant context, so the audit rows are platform-level (``tenant=NULL``).

The ``client_secret`` is a privileged secret. It is never returned to a
tenant-facing surface and never logged — :meth:`serialize` (used by the admin
tables) omits it, updates only rewrite it when a new value is supplied, and the
tenant-facing :meth:`list_authorized_for_tenant` exposes only id/category/name.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from application.repositories import RacetimeBotRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import BotStatus, RacetimeBot, RacetimeBotTenant, User


class RacetimeBotService:
    """SUPER_ADMIN CRUD + tenant authorization grants for racetime bots."""

    def __init__(self) -> None:
        self.repository = RacetimeBotRepository()
        self.audit_service = AuditService()

    # ---- serialization (secret-free) -------------------------------------

    @staticmethod
    def serialize(bot: RacetimeBot) -> Dict[str, Any]:
        """A dict safe for an admin table — the ``client_secret`` is omitted."""
        return {
            'id': bot.id,
            'category': bot.category,
            'client_id': bot.client_id,
            'name': bot.name,
            'description': bot.description or '',
            'is_active': bot.is_active,
            'handler_class': bot.handler_class or '',
            'status': bot.status,
            'status_message': bot.status_message or '',
        }

    # ---- bot CRUD (super-admin, platform-level) --------------------------

    async def list_bots(self, actor: Optional[User]) -> List[RacetimeBot]:
        await self._ensure_super_admin(actor)
        return await self.repository.list_all()

    async def get_bot(self, actor: Optional[User], bot_id: int) -> RacetimeBot:
        await self._ensure_super_admin(actor)
        return await self._require(bot_id)

    async def create_bot(
        self,
        actor: Optional[User],
        *,
        category: str,
        client_id: str,
        client_secret: str,
        name: str,
        description: Optional[str] = None,
        handler_class: Optional[str] = None,
        is_active: bool = True,
    ) -> RacetimeBot:
        await self._ensure_super_admin(actor)
        category = (category or '').strip()
        name = (name or '').strip()
        client_id = (client_id or '').strip()
        client_secret = (client_secret or '').strip()
        if not category:
            raise ValueError('A racetime category is required')
        if not name:
            raise ValueError('A bot name is required')
        if not client_id or not client_secret:
            raise ValueError('Both client id and client secret are required')
        if await self.repository.get_by_category(category) is not None:
            raise ValueError(f"A bot for category '{category}' already exists")
        bot = await self.repository.create(
            category=category,
            client_id=client_id,
            client_secret=client_secret,
            name=name,
            description=(description or '').strip() or None,
            handler_class=(handler_class or '').strip() or None,
            is_active=is_active,
        )
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_CREATED,
            {'bot_id': bot.id, 'category': bot.category},
        )
        return bot

    async def update_bot(
        self,
        actor: Optional[User],
        bot_id: int,
        *,
        category: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        handler_class: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> RacetimeBot:
        await self._ensure_super_admin(actor)
        bot = await self._require(bot_id)
        changes: Dict[str, Any] = {}
        if category is not None:
            new_category = (category or '').strip()
            if not new_category:
                raise ValueError('A racetime category is required')
            if new_category != bot.category:
                existing = await self.repository.get_by_category(new_category)
                if existing is not None and existing.id != bot.id:
                    raise ValueError(f"A bot for category '{new_category}' already exists")
            changes['category'] = new_category
        if client_id is not None:
            new_client_id = (client_id or '').strip()
            if not new_client_id:
                raise ValueError('Client id cannot be empty')
            changes['client_id'] = new_client_id
        # An empty secret means "leave the stored secret unchanged" — the admin
        # form never echoes it back, so blank is the untouched state, not a clear.
        if client_secret is not None and (client_secret or '').strip():
            changes['client_secret'] = client_secret.strip()
        if name is not None:
            new_name = (name or '').strip()
            if not new_name:
                raise ValueError('A bot name is required')
            changes['name'] = new_name
        if description is not None:
            changes['description'] = (description or '').strip() or None
        if handler_class is not None:
            changes['handler_class'] = (handler_class or '').strip() or None
        if is_active is not None:
            changes['is_active'] = is_active
        bot = await self.repository.update(bot, **changes)
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_UPDATED,
            # Never log the secret itself — only that it was among the fields set.
            {'bot_id': bot.id, 'changed_fields': list(changes.keys())},
        )
        return bot

    async def delete_bot(self, actor: Optional[User], bot_id: int) -> None:
        await self._ensure_super_admin(actor)
        bot = await self._require(bot_id)
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_DELETED,
            {'bot_id': bot.id, 'category': bot.category},
        )
        await self.repository.delete(bot)

    # ---- tenant authorization grants -------------------------------------

    async def list_grants(self, actor: Optional[User], bot_id: int) -> List[RacetimeBotTenant]:
        await self._ensure_super_admin(actor)
        await self._require(bot_id)
        return await self.repository.list_grants_for_bot(bot_id)

    async def grant_tenant(self, actor: Optional[User], bot_id: int, tenant_id: int) -> RacetimeBotTenant:
        await self._ensure_super_admin(actor)
        await self._require(bot_id)
        grant = await self.repository.get_grant(bot_id, tenant_id)
        if grant is not None:
            # Idempotent: re-granting simply re-activates a suspended grant.
            if not grant.is_active:
                grant = await self.repository.set_grant_active(grant, True)
        else:
            grant = await self.repository.create_grant(bot_id, tenant_id)
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_GRANTED,
            {'bot_id': bot_id, 'tenant_id': tenant_id},
        )
        return grant

    async def revoke_tenant(self, actor: Optional[User], bot_id: int, tenant_id: int) -> None:
        await self._ensure_super_admin(actor)
        grant = await self.repository.get_grant(bot_id, tenant_id)
        if grant is None:
            return
        await self.repository.delete_grant(grant)
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_REVOKED,
            {'bot_id': bot_id, 'tenant_id': tenant_id},
        )

    # ---- runtime health (written by the racetimebot/ connection loop) ----
    #
    # These are NOT super-admin-gated: the caller is the trusted in-process
    # connection loop acting as the system user, not an interactive admin. They
    # run with no tenant scope (the bot is global), so their audit rows are
    # platform-level (``tenant=NULL``), and the ``client_secret`` never appears
    # in the row. The health enum has no dedicated ``auth_failed`` member, so an
    # auth failure is ``ERROR`` with the reason in ``status_message`` and an
    # ``auth_failed`` flag on the audit detail (the loop uses it to stop retrying).

    async def list_active_bots(self) -> List[RacetimeBot]:
        """Active bots the runtime should hold a connection for."""
        return await self.repository.list_active()

    async def get_runtime_bot(self, bot_id: int) -> Optional[RacetimeBot]:
        """Load a bot by id with no permission gate (runtime/restart use)."""
        return await self.repository.get_by_id(bot_id)

    async def record_connected(self, bot_id: int, actor: User) -> None:
        now = datetime.now(timezone.utc)
        bot = await self.repository.get_by_id(bot_id)
        if bot is None:
            return
        await self.repository.update(
            bot,
            status=BotStatus.CONNECTED,
            status_message=None,
            last_connected_at=now,
            last_checked_at=now,
        )
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_CONNECTED,
            {'bot_id': bot_id, 'category': bot.category},
        )

    async def record_heartbeat(self, bot_id: int) -> None:
        """Refresh ``last_checked_at`` so a wedged-without-error task is visible.

        Deliberately un-audited: it fires on every liveness tick.
        """
        bot = await self.repository.get_by_id(bot_id)
        if bot is None:
            return
        await self.repository.update(bot, last_checked_at=datetime.now(timezone.utc))

    async def record_error(
        self, bot_id: int, actor: User, message: str, *, auth_failed: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        bot = await self.repository.get_by_id(bot_id)
        if bot is None:
            return
        await self.repository.update(
            bot,
            status=BotStatus.ERROR,
            status_message=(message or '').strip()[:2000] or None,
            last_checked_at=now,
        )
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_ERROR,
            {'bot_id': bot_id, 'category': bot.category, 'auth_failed': auth_failed},
        )

    async def mark_disconnected(
        self, bot_id: int, actor: User, message: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        bot = await self.repository.get_by_id(bot_id)
        if bot is None:
            return
        await self.repository.update(
            bot,
            status=BotStatus.DISCONNECTED,
            status_message=(message or '').strip()[:2000] or None,
            last_checked_at=now,
        )
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_BOT_DISCONNECTED,
            {'bot_id': bot_id, 'category': bot.category},
        )

    # ---- tenant-facing read (no secret) ----------------------------------

    async def list_authorized_for_tenant(self, tenant_id: int) -> List[RacetimeBot]:
        """Active bots a tenant may select on a tournament (no secret exposed).

        The tenant id is passed explicitly (the caller supplies
        ``require_tenant_id()``); a category the tenant was not granted, or an
        inactive bot/grant, never appears.
        """
        return await self.repository.list_active_for_tenant(tenant_id)

    async def is_authorized_for_tenant(self, bot_id: int, tenant_id: int) -> bool:
        return any(b.id == bot_id for b in await self.repository.list_active_for_tenant(tenant_id))

    # ---- internals -------------------------------------------------------

    async def _require(self, bot_id: int) -> RacetimeBot:
        bot = await self.repository.get_by_id(bot_id)
        if bot is None:
            raise ValueError('Racetime bot not found')
        return bot

    @staticmethod
    async def _ensure_super_admin(actor: Optional[User]) -> None:
        await AuthService.ensure(
            await AuthService.is_super_admin(actor),
            'Only super-admins can manage racetime bots',
        )
