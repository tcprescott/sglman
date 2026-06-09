# Refactoring Guide: Separating UI from Business Logic

> Code-layer reference docs now live in [`docs/reference/`](reference/) — see [data-model.md](reference/data-model.md), [services.md](reference/services.md), and the [documentation index](README.md). This guide remains the canonical explanation of the three-layer pattern itself.

## Architecture Overview

The application is being refactored into three distinct layers:

```
┌─────────────────────────────────────────┐
│     Presentation Layer (UI)             │
│  - NiceGUI pages and components         │
│  - Tables, dialogs, forms               │
│  - User interaction handlers            │
└──────────────┬──────────────────────────┘
               │ calls
               ↓
┌─────────────────────────────────────────┐
│     Service Layer (Business Logic)      │
│  - Validation and business rules        │
│  - Orchestration between repositories   │
│  - Transaction coordination             │
│  - Audit logging                        │
└──────────────┬──────────────────────────┘
               │ calls
               ↓
┌─────────────────────────────────────────┐
│     Repository Layer (Data Access)      │
│  - Database queries (CRUD)              │
│  - ORM operations                       │
│  - Data fetching and persistence        │
└──────────────┬──────────────────────────┘
               │ uses
               ↓
┌─────────────────────────────────────────┐
│         Models (Domain)                  │
│  - Tortoise ORM models                  │
│  - Database schema definitions          │
└─────────────────────────────────────────┘
```

## Layer Responsibilities

### 1. Presentation Layer (UI)
**Location:** `pages/`, `theme/`

**Responsibilities:**
- Render UI components (tables, dialogs, forms)
- Handle user interactions (button clicks, form submissions)
- Format data for display
- Call service methods in response to user actions
- Show notifications and feedback to users

**Should NOT:**
- Perform database queries directly
- Contain business logic or validation
- Know about ORM implementation details

**Example:**
```python
# BEFORE: Direct database access
async def on_edit(match_id: int):
    match = await Match.get(id=match_id).prefetch_related('tournament', 'players')
    # ... dialog code ...

# AFTER: Use service layer
from application.services import MatchService

async def on_edit(match_id: int):
    service = MatchService()
    match_data = await service.get_match_for_display(match_id)
    # ... dialog code using match_data ...
```

### 2. Service Layer (Business Logic)
**Location:** `application/services/`

**Responsibilities:**
- Enforce business rules and validation
- Coordinate multiple repository operations
- Handle transactions and error handling
- Write audit logs
- Send notifications (emails, Discord messages)
- Format data for UI consumption

**Should NOT:**
- Know about UI components (NiceGUI, Quasar)
- Perform direct database queries (use repositories instead)
- Handle HTTP requests/responses

**Example:**
```python
class MatchService:
    async def create_match(
        self,
        tournament_id: int,
        scheduled_date: str,
        scheduled_time: str,
        player_ids: List[int],
        admin_user: Optional[User] = None
    ) -> Match:
        # Business validation
        if not player_ids:
            raise ValueError("Match must have at least one player")
        
        # Parse and validate datetime
        scheduled_at = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")
        
        # Create match via repository
        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at
        )
        
        # Add players and ensure tournament enrollment
        for player_id in player_ids:
            user = await User.get(id=player_id)
            await self._ensure_tournament_enrollment(user, tournament_id)
            await self.repository.add_player(match, user)
        
        # Audit log
        if admin_user:
            await write_audit_log(admin_user, f'Created match {match.id}', f'Players: {player_ids}')
        
        return match
```

### 3. Repository Layer (Data Access)
**Location:** `application/repositories/`

**Responsibilities:**
- Execute database queries (CRUD operations)
- Manage ORM operations (create, filter, update, delete)
- Control data fetching strategies (prefetch_related, select_related)
- Return domain objects (models)

**Should NOT:**
- Contain business logic or validation
- Know about UI or user interactions
- Handle audit logging or notifications

**Example:**
```python
class MatchRepository:
    @staticmethod
    async def get_by_id(match_id: int, prefetch_relations: bool = False) -> Optional[Match]:
        """Fetch a single match by ID."""
        query = Match.filter(id=match_id)
        if prefetch_relations:
            query = query.prefetch_related(
                'tournament', 'players', 'players__user',
                'commentators', 'commentators__user',
                'trackers', 'trackers__user',
                'stream_room', 'generated_seed'
            )
        return await query.first()
    
    @staticmethod
    async def create(
        tournament_id: int,
        scheduled_at: datetime,
        comment: Optional[str] = None,
        stream_room_id: Optional[int] = None
    ) -> Match:
        """Create a new match."""
        return await Match.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
            stream_room_id=stream_room_id
        )
```

## Migration Strategy

### Step 1: Identify Components to Refactor

Start with components that:
- Have complex database queries
- Mix UI and business logic heavily
- Are used in multiple places
- Would benefit from testability

**Good candidates:**
- Match management (create, edit, seat, finish)
- Crew signup and approval
- Seed generation
- Tournament management

### Step 2: Create Repository

1. Create a new file in `application/repositories/`
2. Define static methods for CRUD operations
3. Keep methods simple - just data access
4. Return domain objects (models)

**Example:**
```python
# application/repositories/tournament_repository.py
class TournamentRepository:
    @staticmethod
    async def get_all(active_only: bool = False) -> List[Tournament]:
        query = Tournament.all()
        if active_only:
            query = query.filter(active=True)
        return await query
    
    @staticmethod
    async def get_by_id(tournament_id: int) -> Optional[Tournament]:
        return await Tournament.get_or_none(id=tournament_id)
    
    @staticmethod
    async def create(name: str, seed_generator: Optional[str] = None, **kwargs) -> Tournament:
        return await Tournament.create(name=name, seed_generator=seed_generator, **kwargs)
```

### Step 3: Create Service

1. Create a new file in `application/services/`
2. Import the repository
3. Add business logic methods
4. Include validation, orchestration, audit logging

**Example:**
```python
# application/services/tournament_service.py
from application.repositories.tournament_repository import TournamentRepository

class TournamentService:
    def __init__(self):
        self.repository = TournamentRepository()
    
    async def get_active_tournaments(self) -> List[Dict[str, Any]]:
        """Get all active tournaments formatted for display."""
        tournaments = await self.repository.get_all(active_only=True)
        return [self._format_for_display(t) for t in tournaments]
    
    async def create_tournament(
        self,
        name: str,
        seed_generator: Optional[str] = None,
        admin_user: Optional[User] = None
    ) -> Tournament:
        """Create a new tournament with validation."""
        # Business rule: Name must be unique
        existing = await self.repository.get_all()
        if any(t.name.lower() == name.lower() for t in existing):
            raise ValueError(f"Tournament '{name}' already exists")
        
        # Create tournament
        tournament = await self.repository.create(name=name, seed_generator=seed_generator)
        
        # Audit log
        if admin_user:
            await write_audit_log(admin_user, f'Created tournament {tournament.id}', f'Name: {name}')
        
        return tournament
```

### Step 4: Update UI Component

1. Import the service
2. Replace direct database queries with service calls
3. Use service methods for all data operations
4. Keep only UI-specific code in the component

**Example BEFORE:**
```python
# pages/admin_tabs/admin_schedule.py
async def on_generate_seed(match_id: int):
    match = await Match.get(id=match_id).prefetch_related('tournament', 'players', 'players__user')
    
    if match.generated_seed:
        ui.notify('Seed already generated', color='warning')
        return
    
    if match.tournament.seed_generator:
        seed_generator = RANDOMIZERS.get(match.tournament.seed_generator)
        if seed_generator:
            seed_url = await seed_generator()
            match.generated_seed = await GeneratedSeeds.create(
                tournament=match.tournament,
                seed_url=seed_url,
                seed_info=f"Generated seed for match {match.id}"
            )
            await match.save()
            
            # Send DMs to players
            for player in match.players:
                if player.user.discord_id:
                    await send_dm(player.user.discord_id, f"Seed: {seed_url}")
            
            ui.notify('Seed generated', color='positive')
```

**Example AFTER:**
```python
# pages/admin_tabs/admin_schedule.py
from application.services import MatchService

async def on_generate_seed(match_id: int):
    service = MatchService()
    
    try:
        await service.generate_seed(match_id)
        ui.notify('Seed generated successfully', color='positive')
        await table_view.update_row_by_id(match_id)
    except ValueError as e:
        ui.notify(str(e), color='warning')
    except Exception as e:
        ui.notify(f'Error generating seed: {e}', color='negative')

# And in MatchService:
async def generate_seed(self, match_id: int) -> str:
    """Generate a seed for a match and notify players."""
    match = await self.repository.get_by_id(match_id, prefetch_relations=True)
    
    # Business validation
    if match.generated_seed:
        raise ValueError('Seed already generated for this match')
    
    if not match.tournament.seed_generator:
        raise ValueError('No seed generator configured for this tournament')
    
    # Generate seed
    seed_generator = RANDOMIZERS.get(match.tournament.seed_generator)
    if not seed_generator:
        raise ValueError(f'Unknown seed generator: {match.tournament.seed_generator}')
    
    seed_url = await seed_generator()
    
    # Save to database
    generated_seed = await GeneratedSeeds.create(
        tournament=match.tournament,
        seed_url=seed_url,
        seed_info=f"Generated seed for match {match.id}"
    )
    await self.repository.update(match, generated_seed=generated_seed)
    
    # Notify players
    for player in match.players:
        if player.user.discord_id:
            message = f"Hello {player.user.preferred_name},\n\n"
            message += f"A seed has been generated for match {match.id}:\n{seed_url}\n\n"
            message += "Good luck!"
            await send_dm(player.user.discord_id, message)
    
    return seed_url
```

### Step 5: Export from `__init__.py`

Update the `__init__.py` files to export new classes:

```python
# application/repositories/__init__.py
from application.repositories.match_repository import MatchRepository
from application.repositories.tournament_repository import TournamentRepository

__all__ = ['MatchRepository', 'TournamentRepository']

# application/services/__init__.py
from application.services.match_service import MatchService
from application.services.tournament_service import TournamentService

__all__ = ['MatchService', 'TournamentService']
```

## Testing Benefits

With this architecture, you can:

1. **Test business logic in isolation:**
```python
async def test_create_match_validation():
    service = MatchService()
    with pytest.raises(ValueError, match="at least one player"):
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-01",
            scheduled_time="10:00",
            player_ids=[]  # Empty - should fail
        )
```

2. **Mock repositories in service tests:**
```python
async def test_generate_seed():
    mock_repo = Mock(spec=MatchRepository)
    service = MatchService()
    service.repository = mock_repo
    
    # Test without touching the database
    await service.generate_seed(match_id=123)
    mock_repo.update.assert_called_once()
```

3. **Test UI components with mock services:**
```python
async def test_admin_schedule_page():
    mock_service = Mock(spec=MatchService)
    # Test UI interactions without database
```

## Gradual Migration

**Don't refactor everything at once!** Migrate incrementally:

1. Start with one feature (e.g., match creation)
2. Create repository and service
3. Update one UI component to use the service
4. Test thoroughly
5. Move to the next feature

Both old and new code can coexist:
```python
# Old code still works
match = await Match.get(id=123)

# New code uses service
service = MatchService()
match_data = await service.get_match_for_display(123)
```

## Current Status

### Completed
- ✅ `MatchRepository` - Full CRUD for matches
- ✅ `MatchService` - Business logic for match operations

### In Progress
- 🔄 Refactor admin_schedule.py to use MatchService

### To Do
- ⏳ `TournamentRepository` and `TournamentService`
- ⏳ `UserRepository` and `UserService`
- ⏳ `CrewRepository` and `CrewService` (commentators/trackers)
- ⏳ Refactor remaining UI components

## Best Practices

1. **Keep services stateless** - Create new instance each time or use static methods
2. **Use type hints** - Makes code self-documenting and enables IDE support
3. **Return domain objects or dicts** - Services can return models or formatted dicts
4. **Handle exceptions in UI** - Let services raise exceptions, catch in UI layer
5. **Write docstrings** - Document parameters, returns, and exceptions
6. **Audit important actions** - Log creates, updates, deletes in services
7. **Validate early** - Check business rules before database operations

## Questions?

- **Q: Should I always use services for every database query?**
  - A: For complex operations, yes. Simple lookups can stay direct.

- **Q: Can I use repositories directly from UI?**
  - A: Only for read-only operations. Writes should go through services.

- **Q: What if I need to add a new field to a model?**
  - A: Update model, migration, then repository method, then service method, then UI.

- **Q: How do I handle transactions?**
  - A: Services should manage transactions for operations that touch multiple tables.
