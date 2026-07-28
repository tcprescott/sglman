# The Three-Layer Pattern

The rules live in [CLAUDE.md](../CLAUDE.md); this doc is the worked example of each
layer against current code. The refactor itself is finished — every domain has a
repository and a service, and `.claude/scripts/enforce_architecture.py` blocks
violations at write time.

```
Presentation (pages/, theme/, api/, discordbot/, mcpserver/)
      ↓ calls
Service      (application/services/)
      ↓ calls
Repository   (application/repositories/)
      ↓ uses
Models       (models/)
```

## Repository — pure data access

Data access only: CRUD, queries, `prefetch_related`. No validation, no audit, no
notifications. Every scoped read goes through `scoped()` and every scoped write
stamps `tenant_id` — see [`_tenant.py`](../application/repositories/_tenant.py).

```python
from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import StreamRoom


class StreamRoomRepository(TenantScopedRepository[StreamRoom]):
    model = StreamRoom

    @staticmethod
    async def get_all() -> list[StreamRoom]:
        return await scoped(StreamRoom.all()).order_by('name')

    @staticmethod
    async def create(name: str, stream_url: str | None = None) -> StreamRoom:
        return await StreamRoom.create(
            tenant_id=current_tenant_id(), name=name, stream_url=stream_url,
        )
```

`current_tenant_id()` raises when no tenant is in scope. That loud failure is the
safety net — never swallow it. The handful of deliberately cross-tenant methods
(token lookup by hash, guild→tenant routing, the volunteer-reminder scan, global
identity by `discord_id`) skip these helpers and carry a comment saying why.

## Service — rules, authorization, audit, notifications

Validates, authorizes, coordinates repositories, writes the audit row, and sends
notifications. Raises `ValueError` for anything the user should see. Never imports
NiceGUI. Stateless — a fresh instance per request, or static methods.

```python
class StreamRoomService:
    async def create_stream_room(
        self, name: str, stream_url: str | None = None, actor: User | None = None,
    ) -> StreamRoom:
        await AuthService.ensure(
            await AuthService.can_manage_stream_rooms(actor),
            "User cannot manage stream rooms",
        )

        if not name or not name.strip():
            raise ValueError("Room name is required")

        room = await self.repository.create(name=name.strip(), stream_url=stream_url)

        await self.audit_service.write_log(
            actor,
            AuditActions.STREAM_ROOM_CREATED,
            {'stream_room_id': room.id, 'name': room.name},
        )
        return room
```

Note the shape of the audit call: an `AuditActions` constant (never a free-form
string), `actor` passed positionally and unconditionally (never `if actor:`), and
`details` as a plain dict. When the change should also reach webhooks and live UI,
use `write_and_publish` instead of pairing `write_log` with a bare
`event_bus.publish` — `check_dry_regressions.py` blocks the hand-rolled pair. Full
conventions: [audit-logging.md](features/audit-logging.md),
[event-system.md](features/event-system.md).

## Presentation — render and report

Renders, handles interaction, calls services, catches their errors and notifies.
No business logic, no ORM writes. Read-only ORM lookups for simple display are
tolerated, but a repository-backed service method is preferred.

```python
from application.services import MatchScheduleService

async def on_generate_seed(match_id: int):
    try:
        await service.generate_seed(match_id)
        ui.notify('Seed generated', color='positive')
    except ValueError as e:
        ui.notify(str(e), color='warning')
```

**`api/`, `discordbot/` and `mcpserver/` are presentation too.** They call services
and may do a read-only *load-or-404* model lookup (the sanctioned shape is
`Tournament.get_or_none(...)` in
[`api/routers/tournament_actions.py`](../api/routers/tournament_actions.py)), but
they must not import `application.repositories` or reach through
`service.repository.*`. Route reads through a service method instead.

## What the hooks enforce

`enforce_architecture.py` rejects, at write time: presentation importing
`application.repositories`; services importing NiceGUI; repositories importing
`pages/`/`theme/`. Sibling hooks check audit conventions, the `write_log` +
`publish` pair, mobile grids on tables, and test-fixture cost. Inventory:
[`.claude/README.md`](../.claude/README.md).

## Adding a feature

The sequenced checklist — model → migration → repository → service → exports → UI →
dev seed → tests — is the `add-feature` skill, and step 0 (does this warrant a
feature flag?) is in [CLAUDE.md](../CLAUDE.md#adding-a-new-feature).
