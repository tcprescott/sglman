from enum import Enum

from tortoise import fields
from tortoise.models import Model


class Role(str, Enum):
    STAFF = 'staff'
    PROCTOR = 'proctor'
    STREAM_MANAGER = 'stream_manager'
    TRIFORCE_SUBMITTER = 'triforce_submitter'
    VOLUNTEER_COORDINATOR = 'volunteer_coordinator'
    EQUIPMENT_MANAGER = 'equipment_manager'
    VOLUNTEER = 'volunteer'
    # Online-tournament admin surfaces (see docs/online-tournaments). Each gates a
    # new subsystem's management UI/worker actions the way STAFF does the rest.
    PRESET_MANAGER = 'preset_manager'
    SYNC_ADMIN = 'sync_admin'
    QUALIFIER_ADMIN = 'qualifier_admin'
    # Global platform role: manages tenants on the /platform surface. Its
    # UserRole rows carry tenant=NULL (the only role that may) and stay visible
    # inside any tenant request. Not grantable per-tenant.
    SUPER_ADMIN = 'super_admin'


# Sentinel ``discord_id`` for the reserved system :class:`User` that automation
# (workers, racetime/Discord bot handlers, ETL, qualifier scoring) acts as. A
# real snowflake is always a large positive integer, so ``0`` can never collide
# with a genuine Discord account. The row is marked ``is_system`` and resolved
# via ``UserService.get_system_user()``.
SYSTEM_USER_DISCORD_ID = 0


class RoleSource(str, Enum):
    MANUAL = 'manual'
    DISCORD = 'discord'


class VolunteerAvailabilityStatus(str, Enum):
    AVAILABLE = 'available'
    UNAVAILABLE = 'unavailable'
    PREFERRED = 'preferred'


class FeedbackCategory(str, Enum):
    BUG = 'bug'
    SUGGESTION = 'suggestion'
    PRAISE = 'praise'
    OTHER = 'other'


class FeedbackStatus(str, Enum):
    NEW = 'new'
    REVIEWED = 'reviewed'


class EquipmentStatus(str, Enum):
    AVAILABLE = 'available'
    CHECKED_OUT = 'checked_out'
    RETIRED = 'retired'


class StationFormat(str, Enum):
    FREE = 'free'
    NUMERIC = 'numeric'
    STRUCTURED = 'structured'
    ALPHANUMERIC = 'alphanumeric'


class Tenant(Model):
    """One independent tournament community hosted on the shared deployment.

    Logical multitenancy: a single database, shared tables, and this row as the
    discriminator every scoped model points at. Addressable path-based at
    ``/t/<slug>`` on the platform host; ``domain`` is reserved for optional
    host-based addressing (not yet resolved). ``discord_guild_id`` is the routing
    key the shared one-bot-many-guilds process uses to map a guild back to its
    tenant(s) — it is **not** unique, so several communities may share one Discord
    server and the bot fans out over every linked tenant. ``config`` holds
    per-tenant knobs that don't warrant columns.
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    # URL-safe path routing key: ``https://<platform>/t/<slug>/…``. Mutable
    # unique column — every join is by ``tenant.id``, so re-slugging is a
    # one-row UPDATE.
    slug = fields.CharField(max_length=64, unique=True, index=True)
    # Optional custom domain for host-based addressing. Nullable + unique (many
    # NULLs allowed in Postgres); host-mode resolution is deferred, the column
    # exists so attaching a domain later needs no schema change.
    domain = fields.CharField(max_length=255, null=True, unique=True, index=True)
    # Discord guild this tenant owns; the shared bot routes gateway events and
    # role sync by matching this. Nullable until a guild is linked.
    discord_guild_id = fields.BigIntField(null=True, index=True)
    is_active = fields.BooleanField(default=True)
    config = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'tenant'


class TenantMembership(Model):
    """Ties a global :class:`User` to a :class:`Tenant` they belong to.

    Queried across tenants (never auto-scoped): membership is what the auth layer
    checks to decide whether an authenticated user may see a tenant at all.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='memberships', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='tenant_memberships', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'tenantmembership'
        unique_together = (('user', 'tenant'),)
        indexes = (('tenant',),)  # composite is user-first; per-tenant member enumeration uncovered


class User(Model):
    id = fields.IntField(pk=True)
    # Nullable+unique (Postgres allows many NULLs) so an unresolved SpeedGaming
    # player can exist as a *placeholder* User (``is_placeholder=True``,
    # ``discord_id=NULL``) — keeping ``MatchPlayers.user`` NOT NULL. A DB CHECK
    # (``discord_id IS NOT NULL OR is_placeholder``) enforces that only
    # placeholders may lack a discord id; see migration 26. A placeholder is
    # *upgraded in place* to a real User when its ``discord_id`` later appears.
    discord_id = fields.BigIntField(unique=True, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    username = fields.CharField(max_length=150)
    display_name = fields.CharField(max_length=150, null=True)
    pronouns = fields.CharField(max_length=50, null=True)
    is_active = fields.BooleanField(default=True)
    # Marks the single reserved automation actor (sentinel ``discord_id`` =
    # ``SYSTEM_USER_DISCORD_ID``). Workers/bots pass this row as ``actor`` so
    # audit rows snapshot a real username instead of a bare sentinel. Resolve it
    # via ``UserService.get_system_user()``, never construct it ad hoc.
    is_system = fields.BooleanField(default=False)
    dm_notifications = fields.BooleanField(default=True)
    # Verified Challonge identity (captured via one-time OAuth, scope ``me``).
    # Identity only — we do not retain a player's Challonge access token.
    # Unique so bracket sync can resolve a Challonge id to exactly one user
    # (Postgres allows multiple NULLs, so unlinked users are unconstrained).
    challonge_user_id = fields.CharField(max_length=64, null=True, unique=True)
    challonge_username = fields.CharField(max_length=255, null=True)
    challonge_linked_at = fields.DatetimeField(null=True)
    # Verified Twitch identity (captured via one-time OAuth). Identity only — we
    # do not retain a user's Twitch access token. Unique so a Twitch id resolves
    # to exactly one user (Postgres allows multiple NULLs, so unlinked users are
    # unconstrained).
    twitch_user_id = fields.CharField(max_length=64, null=True, unique=True)
    twitch_username = fields.CharField(max_length=255, null=True)
    twitch_linked_at = fields.DatetimeField(null=True)
    # Verified racetime.gg identity (captured via one-time OAuth, read scope).
    # Identity only — we do not retain a user's racetime access token. Unique so a
    # racetime id resolves to exactly one user (Postgres allows multiple NULLs, so
    # unlinked users are unconstrained).
    racetime_user_id = fields.CharField(max_length=64, null=True, unique=True)
    racetime_username = fields.CharField(max_length=255, null=True)
    racetime_linked_at = fields.DatetimeField(null=True)
    # Placeholder identity (SpeedGaming ETL, PR 7). A player the SG sync could not
    # resolve to a real account becomes a placeholder User so its ``MatchPlayers``
    # row is still first-class. ``speedgaming_id`` is the SG-side numeric id used
    # to re-find the same placeholder across syncs; unique so an SG id maps to one
    # User (Postgres allows many NULLs, so non-SG users are unconstrained).
    is_placeholder = fields.BooleanField(default=False)
    speedgaming_id = fields.CharField(max_length=64, null=True, unique=True)

    # related fields
    admin_tournaments = fields.ManyToManyRelation["Tournament"]
    crew_coordinated_tournaments = fields.ManyToManyRelation["Tournament"]
    match_players = fields.ReverseRelation["MatchPlayers"]
    match_acknowledgments = fields.ReverseRelation["MatchAcknowledgment"]
    tournament_players = fields.ReverseRelation["TournamentPlayers"]
    tournament_notifications = fields.ReverseRelation["TournamentNotificationPreference"]
    commentaries = fields.ReverseRelation["Commentator"]
    approved_commentaries = fields.ReverseRelation["Commentator"]
    trackers = fields.ReverseRelation["Tracker"]
    approved_trackers = fields.ReverseRelation["Tracker"]
    watched_matches = fields.ReverseRelation["MatchWatcher"]
    roles = fields.ReverseRelation["UserRole"]
    granted_roles = fields.ReverseRelation["UserRole"]
    audit_logs = fields.ReverseRelation["AuditLog"]
    triforce_texts = fields.ReverseRelation["TriforceText"]
    triforce_texts_moderated = fields.ReverseRelation["TriforceText"]
    api_tokens = fields.ReverseRelation["ApiToken"]
    feedback_submissions = fields.ReverseRelation["Feedback"]
    owned_equipment = fields.ReverseRelation["Equipment"]
    equipment_loans = fields.ReverseRelation["EquipmentLoan"]
    equipment_checkouts_performed = fields.ReverseRelation["EquipmentLoan"]
    equipment_checkins_performed = fields.ReverseRelation["EquipmentLoan"]
    volunteer_profiles = fields.ReverseRelation["VolunteerProfile"]
    volunteer_assignments = fields.ReverseRelation["VolunteerAssignment"]
    volunteer_assignments_made = fields.ReverseRelation["VolunteerAssignment"]
    volunteer_qualifications = fields.ReverseRelation["VolunteerQualification"]
    volunteer_availability = fields.ReverseRelation["VolunteerAvailability"]
    challonge_participations = fields.ReverseRelation["ChallongeParticipant"]
    web_push_subscriptions = fields.ReverseRelation["WebPushSubscription"]
    tenant_memberships = fields.ReverseRelation["TenantMembership"]

    @property
    def preferred_name(self) -> str:
        return self.display_name if self.display_name else self.username


class ApiToken(Model):
    """A personal access token granting REST API access as its owning user.

    Only the SHA-256 hash of the token is stored; the plaintext is shown once
    at creation. A token acts with the full permissions of ``user`` unless
    ``read_only`` is set, in which case it may only call read endpoints.
    """

    id = fields.IntField(pk=True)
    # A token acts within one tenant; token_hash stays globally unique (the
    # lookup happens before any tenant context exists — see api/dependencies.py).
    tenant = fields.ForeignKeyField('models.Tenant', related_name='api_tokens', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='api_tokens')
    name = fields.CharField(max_length=100)
    token_hash = fields.CharField(max_length=64, unique=True, index=True)
    token_prefix = fields.CharField(max_length=24)
    read_only = fields.BooleanField(default=False)
    last_used_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'apitoken'


class Feedback(Model):
    """An in-app feedback submission from a logged-in attendee.

    Captures the submitting ``user``, a free-text ``message`` and ``category``,
    and the ``page_url`` (path + query, including any ``?tab=``) the user was on
    when they submitted, so staff have the context to act on it.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='feedback', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='feedback_submissions', on_delete=fields.CASCADE)
    category = fields.CharEnumField(FeedbackCategory, default=FeedbackCategory.OTHER, max_length=20)
    message = fields.TextField()
    page_url = fields.CharField(max_length=512)
    status = fields.CharEnumField(FeedbackStatus, default=FeedbackStatus.NEW, max_length=20)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'feedback'


class Equipment(Model):
    """A physical asset available for lending at live events.

    Each asset gets an auto-assigned, unique ``asset_number`` (a scannable QR
    code on its page encodes the asset's URL). ``owner_user`` records who owns
    the asset; a ``null`` owner means it belongs to SpeedGaming Live. ``status``
    is kept in sync with open loans by the service layer (the single writer).
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='equipment', on_delete=fields.CASCADE)
    # Unique per tenant, not globally — each tenant runs its own asset numbering.
    asset_number = fields.IntField()
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    private_notes = fields.TextField(null=True)
    owner_user = fields.ForeignKeyField(
        'models.User', related_name='owned_equipment', null=True, on_delete=fields.SET_NULL
    )
    status = fields.CharEnumField(EquipmentStatus, default=EquipmentStatus.AVAILABLE, max_length=20)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    loans = fields.ReverseRelation["EquipmentLoan"]

    @property
    def owner_label(self) -> str:
        return self.owner_user.preferred_name if self.owner_user else 'SpeedGaming Live'

    class Meta:
        table = 'equipment'
        unique_together = (('tenant', 'asset_number'),)


class EquipmentLoan(Model):
    """A single checkout of an :class:`Equipment` asset.

    The open loan (``checked_in_at`` is null) identifies the current holder;
    closed loans form the asset's full lending history.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='equipment_loans', on_delete=fields.CASCADE)
    equipment = fields.ForeignKeyField('models.Equipment', related_name='loans', on_delete=fields.CASCADE)
    # RESTRICT: a user with lending history cannot be hard-deleted (retire via
    # User.is_active instead), so the asset's ownership trail is never destroyed.
    borrower = fields.ForeignKeyField(
        'models.User', related_name='equipment_loans', on_delete=fields.RESTRICT
    )
    checked_out_by = fields.ForeignKeyField(
        'models.User', related_name='equipment_checkouts_performed', on_delete=fields.RESTRICT
    )
    checked_out_at = fields.DatetimeField(auto_now_add=True)
    checked_in_at = fields.DatetimeField(null=True)
    checked_in_by = fields.ForeignKeyField(
        'models.User', related_name='equipment_checkins_performed', null=True, on_delete=fields.SET_NULL
    )

    class Meta:
        table = 'equipmentloan'
        indexes = (('equipment',), ('borrower',))


class Tournament(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='tournaments', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    seed_generator = fields.CharField(max_length=255, null=True)
    is_active = fields.BooleanField(default=True)
    players_per_match = fields.IntField(default=2)
    team_size = fields.IntField(default=1)
    bracket_url = fields.CharField(max_length=255, null=True)
    rules_url = fields.CharField(max_length=255, null=True)
    tournament_format = fields.CharField(max_length=255, null=True)
    triforce_access_message = fields.TextField(null=True)
    average_match_duration = fields.IntField(null=True)  # in minutes
    max_match_duration = fields.IntField(null=True)  # in minutes
    challonge_tournament_id = fields.CharField(max_length=64, null=True)
    challonge_tournament_url = fields.CharField(max_length=255, null=True)
    challonge_last_synced_at = fields.DatetimeField(null=True)
    # Hybrid config substrate (see docs/online-tournaments): worker-queried knobs
    # stay typed columns; templates, scoring params, and strategy choices live in
    # this schema-validated JSON blob. Written only through the service layer,
    # which validates it with ``validate_tournament_config`` (unknown keys raise
    # ``ValueError``). ``null`` until a tournament opts into online behavior.
    config = fields.JSONField(null=True)
    # Seed-rolling preset (PR 1+). Coexists with the legacy ``seed_generator``
    # string: when this FK is set it wins (seed generation resolves the preset's
    # randomizer + settings); otherwise ``seed_generator`` still drives the
    # hard-coded path. SET_NULL so deleting a preset detaches its tournaments
    # rather than cascade-deleting them.
    preset = fields.ForeignKeyField(
        'models.Preset', related_name='tournaments', null=True, on_delete=fields.SET_NULL
    )
    # Racetime room automation (PR 3+). ``racetime_bot`` must be a category the
    # tenant is authorized for (enforced in the service); SET_NULL so revoking a
    # bot detaches its tournaments rather than deleting them. ``race_room_profile``
    # supplies reusable room settings. The remaining knobs are worker-queried, so
    # they are typed columns rather than living in ``config``.
    racetime_bot = fields.ForeignKeyField(
        'models.RacetimeBot', related_name='tournaments', null=True, on_delete=fields.SET_NULL
    )
    race_room_profile = fields.ForeignKeyField(
        'models.RaceRoomProfile', related_name='tournaments', null=True, on_delete=fields.SET_NULL
    )
    racetime_auto_create_rooms = fields.BooleanField(default=False)
    room_open_minutes_before = fields.IntField(default=30)
    require_racetime_link = fields.BooleanField(default=False)
    racetime_default_goal = fields.CharField(max_length=255, null=True)
    # Discord Scheduled Events mirror (PR 8). Per-tournament opt-in: when enabled,
    # the reconciler worker mirrors this tournament's scheduled matches into the
    # tenant guild's Discord Scheduled Events. ``discord_event_duration_minutes``
    # sets each external event's end time; the templates (nullable — a built-in
    # default is used when unset) render the event title/description from match
    # data (``{tournament}`` / ``{match}`` / ``{players}`` placeholders).
    discord_events_enabled = fields.BooleanField(default=False)
    discord_event_duration_minutes = fields.IntField(default=60)
    discord_event_title_template = fields.CharField(max_length=255, null=True)
    discord_event_description_template = fields.TextField(null=True)
    admins = fields.ManyToManyField('models.User', related_name='admin_tournaments', through='TournamentAdmins')
    crew_coordinators = fields.ManyToManyField(
        'models.User',
        related_name='crew_coordinated_tournaments',
        through='TournamentCrewCoordinators',
    )
    staff_administered = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    players = fields.ReverseRelation["TournamentPlayers"]
    matches = fields.ReverseRelation["Match"]
    notification_preferences = fields.ReverseRelation["TournamentNotificationPreference"]
    triforce_texts = fields.ReverseRelation["TriforceText"]
    challonge_participants = fields.ReverseRelation["ChallongeParticipant"]
    challonge_matches = fields.ReverseRelation["ChallongeMatch"]

class Match(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='matches', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='matches')
    # SET_NULL: deleting a stream room (or seed) detaches its matches instead of
    # cascade-deleting the entire match and its players/crew/acknowledgments.
    stream_room = fields.ForeignKeyField(
        'models.StreamRoom', related_name='matches', null=True, on_delete=fields.SET_NULL
    )
    scheduled_at = fields.DatetimeField(null=True, index=True)
    seated_at = fields.DatetimeField(null=True) # now known as "Checked In"
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True, index=True)
    confirmed_at = fields.DatetimeField(null=True)
    comment = fields.TextField(null=True)
    is_stream_candidate = fields.BooleanField(default=False)
    title = fields.CharField(max_length=255, null=True)
    generated_seed = fields.ForeignKeyField(
        'models.GeneratedSeeds', related_name='matches', null=True, on_delete=fields.SET_NULL
    )
    # Source marker for the SpeedGaming ETL (PR 7). Non-null = this Match was
    # materialized from an SG episode, which makes the ETL-owned fields
    # (``scheduled_at``, players, ``tournament``) read-only in SGLMan — the guard
    # lives in ``MatchService.update_match``. SET_NULL so purging a synced episode
    # soft-detaches the Match (everything SGLMan added on top survives) rather
    # than cascade-deleting it. OneToOne: an episode maps to exactly one Match.
    speedgaming_episode = fields.OneToOneField(
        'models.SpeedGamingEpisode', related_name='match', null=True, on_delete=fields.SET_NULL
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    acknowledgments = fields.ReverseRelation["MatchAcknowledgment"]
    challonge_match = fields.ReverseRelation["ChallongeMatch"]

    @property
    def is_seated(self) -> bool:
        return self.seated_at is not None

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None

    @property
    def is_started(self) -> bool:
        return self.started_at is not None

    @property
    def current_state(self) -> str:
        if self.is_finished:
            return 'Finished'
        elif self.is_started:
            return 'In Progress'
        elif self.is_seated:
            return 'Checked In'
        else:
            return 'Scheduled'

    class Meta:
        # scheduled_at / finished_at are indexed at the field level; these FK
        # columns drive the tournament- and room-scoped schedule/report filters.
        indexes = (('tournament',), ('stream_room',))

class MatchPlayers(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='match_players', on_delete=fields.CASCADE)
    match = fields.ForeignKeyField('models.Match', related_name='players')
    user = fields.ForeignKeyField('models.User', related_name='match_players')
    finish_rank = fields.IntField(null=True)
    # Elapsed finish time in whole seconds, captured from a racetime room result
    # (PR 6). Null for non-finishers (forfeit / no-show / DQ) and for matches not
    # run through a race room. ``finish_rank`` remains the place (1 = winner).
    finish_time = fields.IntField(null=True)
    assigned_station = fields.CharField(max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('match', 'user'),)
        table = 'matchplayers'
        indexes = (('user',),)  # composite is match-first; user-only reverse lookup uncovered

class MatchAcknowledgment(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='match_acknowledgments', on_delete=fields.CASCADE)
    match = fields.ForeignKeyField('models.Match', related_name='acknowledgments', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='match_acknowledgments', on_delete=fields.CASCADE)
    acknowledged_at = fields.DatetimeField(null=True)
    auto_acknowledged = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('match', 'user'),)
        table = 'matchacknowledgment'

class TournamentPlayers(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='tournament_players', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='players')
    user = fields.ForeignKeyField('models.User', related_name='tournament_players')
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('tournament', 'user'),)
        table = 'tournamentplayers'
        indexes = (('user',),)  # composite is tournament-first; user-only reverse lookup uncovered

class MatchNotificationLevel(str, Enum):
    NONE = 'none'
    STREAMED = 'streamed'
    STREAMED_AND_CANDIDATES = 'streamed_and_candidates'
    ALL = 'all'

class TournamentNotificationPreference(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='tournament_notification_preferences', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='tournament_notifications')
    tournament = fields.ForeignKeyField('models.Tournament', related_name='notification_preferences')
    match_notifications = fields.CharEnumField(MatchNotificationLevel, default=MatchNotificationLevel.NONE, max_length=30)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'tournament')
        table = 'tournamentnotificationpreference'
        indexes = (('tournament',),)  # composite is user-first; tournament-only fan-out uncovered

class StreamRoom(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='stream_rooms', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    stream_url = fields.CharField(max_length=255, null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'streamroom'
        unique_together = (('tenant', 'name'),)

class Commentator(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='commentators', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='commentaries')
    match = fields.ForeignKeyField('models.Match', related_name='commentators')
    approved = fields.BooleanField(default=False)
    # SET_NULL: deleting the approver must not delete another user's crew signup.
    approved_by = fields.ForeignKeyField(
        'models.User', related_name='approved_commentaries', null=True, on_delete=fields.SET_NULL
    )
    acknowledged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('match', 'user'),)
        table = 'commentator'

class Tracker(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='trackers', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='trackers')
    match = fields.ForeignKeyField('models.Match', related_name='trackers')
    approved = fields.BooleanField(default=False)
    # SET_NULL: deleting the approver must not delete another user's crew signup.
    approved_by = fields.ForeignKeyField(
        'models.User', related_name='approved_trackers', null=True, on_delete=fields.SET_NULL
    )
    acknowledged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('match', 'user'),)
        table = 'tracker'

class MatchWatcher(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='match_watchers', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='watched_matches', on_delete=fields.CASCADE)
    match = fields.ForeignKeyField('models.Match', related_name='watchers', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'match')
        table = 'matchwatcher'
        indexes = (('match',),)  # composite is user-first; match-only fan-out lookup uncovered

class AuditLog(Model):
    id = fields.IntField(pk=True)
    # Nullable: stamped from context for tenant activity; NULL marks a
    # platform-level row (super-admin tenant CRUD). SET_NULL so a deleted tenant
    # doesn't destroy the append-only trail.
    tenant = fields.ForeignKeyField(
        'models.Tenant', related_name='audit_logs', null=True, on_delete=fields.SET_NULL
    )
    # SET_NULL keeps the append-only trail intact when a user is deleted; the
    # actor's identity is also snapshotted into ``details`` by AuditService.
    user = fields.ForeignKeyField(
        'models.User', related_name='audit_logs', null=True, on_delete=fields.SET_NULL
    )
    action = fields.CharField(max_length=255)
    details = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = 'auditlog'
        indexes = (('user',),)

class TelemetryEvent(Model):
    """Append-only engagement telemetry: how people actually use the tool.

    Distinct from ``AuditLog`` (which records deliberate admin *actions*): this
    is high-volume behavioral signal — page views, feature interactions, and a
    mirror of every domain event on the bus — captured to answer "how did people
    engage post-event?". ``user`` is ``SET_NULL`` + identity-snapshotted into
    ``details`` so the trail survives a user deletion, exactly like ``AuditLog``.
    """
    id = fields.IntField(pk=True)
    # Nullable: stamped from the event/request tenant; NULL marks a platform-level
    # row (platform page views). SET_NULL preserves the trail past a tenant delete.
    tenant = fields.ForeignKeyField(
        'models.Tenant', related_name='telemetry_events', null=True, on_delete=fields.SET_NULL
    )
    user = fields.ForeignKeyField(
        'models.User', related_name='telemetry_events', null=True, on_delete=fields.SET_NULL
    )
    # Coarse bucket for aggregation without parsing event_type: 'page',
    # 'interaction', or 'domain' (see TelemetryCategory in the service).
    category = fields.CharField(max_length=32, index=True)
    # Namespaced ``object.verb`` name. For domain rows this is the EventType
    # string; for engagement rows it is e.g. 'page.view' / 'report.exported'.
    event_type = fields.CharField(max_length=100, index=True)
    # Route/page the event happened on (page views + interactions); null for
    # domain events, which are not page-scoped.
    path = fields.CharField(max_length=512, null=True)
    # Per-browser correlation id (NiceGUI app.storage.browser id) so a user's
    # journey can be reconstructed as an ordered session; null for bus events.
    session_id = fields.CharField(max_length=64, null=True, index=True)
    details = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = 'telemetryevent'
        indexes = (('user',),)

class GeneratedSeeds(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='generated_seeds', on_delete=fields.CASCADE)
    seed_url = fields.CharField(max_length=255)
    seed_info = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class Preset(Model):
    """A tenant-authored seed-rolling preset: a named randomizer settings blob.

    Replaces the hard-coded ``presets/*`` files as the source of seed settings —
    seed generation resolves a ``Preset`` (its ``randomizer`` + ``settings``)
    rather than opening a path. The built-in files can be imported as starting
    rows (see ``PresetService.import_builtins``). ``settings`` is the raw payload
    handed to the randomizer backend (for ALTTPR, the customizer settings dict).
    """
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='presets', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    randomizer = fields.CharField(max_length=32)
    settings = fields.JSONField()
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    tournaments = fields.ReverseRelation["Tournament"]

    class Meta:
        table = 'preset'
        # Formerly-global preset names are namespaced per tenant; a preset is
        # uniquely a (randomizer, name) within its tenant.
        unique_together = (('tenant', 'randomizer', 'name'),)

class SystemConfiguration(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='system_configurations', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    value = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'systemconfiguration'
        unique_together = (('tenant', 'name'),)

class Webhook(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='webhooks', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    url = fields.CharField(max_length=1024)
    # Plaintext because it must be reproducible to sign each delivery (unlike a
    # hashed API token). Never returned by list/GET or written to logs.
    secret = fields.CharField(max_length=128)
    # List of EventType values this webhook fires on; ['*'] means every event.
    event_types = fields.JSONField(default=list)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'webhook'

class WebhookDelivery(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='webhook_deliveries', on_delete=fields.CASCADE)
    webhook = fields.ForeignKeyField(
        'models.Webhook', related_name='deliveries', on_delete=fields.CASCADE
    )
    event_type = fields.CharField(max_length=100)
    payload = fields.TextField()
    response_status = fields.IntField(null=True)
    attempt_count = fields.IntField(default=0)
    success = fields.BooleanField(default=False)
    error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    delivered_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'webhookdelivery'
        indexes = (('webhook',),)

class WebPushSubscription(Model):
    """One browser/device push subscription for a user (Web Push, RFC 8030).

    ``endpoint`` is the push-service URL the browser handed out and is unique
    per subscription; ``p256dh``/``auth`` are the client keys every message is
    encrypted against (RFC 8291). A user may hold one row per device/browser.
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        'models.User', related_name='web_push_subscriptions', on_delete=fields.CASCADE
    )
    endpoint = fields.CharField(max_length=1024, unique=True)
    p256dh = fields.CharField(max_length=128)
    auth = fields.CharField(max_length=64)
    # Captured at subscribe time so the settings UI can label the device.
    user_agent = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_used_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'webpushsubscription'
        indexes = (('user',),)


class UserRole(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='roles')
    # Nullable: every grant is per-tenant EXCEPT SUPER_ADMIN, which carries
    # tenant=NULL and stays visible inside any tenant request (the only global
    # role). CASCADE so a deleted tenant drops its per-tenant grants; NULL
    # super-admin rows are untouched.
    tenant = fields.ForeignKeyField(
        'models.Tenant', related_name='user_roles', null=True, on_delete=fields.CASCADE
    )
    role = fields.CharEnumField(Role, max_length=32)
    # SET_NULL: deleting the granter must not revoke roles they granted to others.
    granted_by = fields.ForeignKeyField(
        'models.User', related_name='granted_roles', null=True, on_delete=fields.SET_NULL
    )
    source = fields.CharEnumField(RoleSource, max_length=16, default=RoleSource.MANUAL)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'role', 'tenant')
        table = 'userrole'
        indexes = (('role',),)  # composite is user-first; role-only enumeration uncovered


class DiscordRoleMapping(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='discord_role_mappings', on_delete=fields.CASCADE)
    # The Discord guild these mappings apply to. A guild may be shared by several
    # tenants, so ``guild_id`` alone does not isolate a tenant — reads combine it
    # with the tenant scope, and the unique key is (tenant, discord_role_id, app_role).
    guild_id = fields.BigIntField()
    discord_role_id = fields.BigIntField()
    discord_role_name = fields.CharField(max_length=100)
    app_role = fields.CharEnumField(Role, max_length=32)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'discord_role_id', 'app_role')
        table = 'discordrolemapping'

class TriforceText(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='triforce_texts', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField(
        'models.Tournament', related_name='triforce_texts', on_delete=fields.CASCADE
    )
    user = fields.ForeignKeyField(
        'models.User', related_name='triforce_texts',
        null=True, on_delete=fields.SET_NULL,
    )
    text = fields.CharField(max_length=200)
    author = fields.CharField(max_length=200, null=True)
    approved = fields.BooleanField(null=True)
    approved_by = fields.ForeignKeyField(
        'models.User', related_name='triforce_texts_moderated',
        null=True, on_delete=fields.SET_NULL,
    )
    approved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'triforcetext'
        # tournament_id prefix serves list_by_tournament(+approved); full key
        # serves list_by_tournament_and_user / list_approved_by_user.
        indexes = (('tournament', 'user'),)


class VolunteerProfile(Model):
    """Per-user opt-in record for onsite volunteering.

    Any logged-in user can opt in; only users with ``opted_in_at`` set are
    assignable / appear in the coordinator's pool.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='volunteer_profiles', on_delete=fields.CASCADE)
    # Per-tenant opt-in: a user opts in independently for each tenant, so this is
    # a tenant-scoped FK (not a global OneToOne) unique per (tenant, user).
    user = fields.ForeignKeyField('models.User', related_name='volunteer_profiles', on_delete=fields.CASCADE)
    opted_in_at = fields.DatetimeField(null=True)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteerprofile'
        unique_together = (('tenant', 'user'),)


class VolunteerPosition(Model):
    """A coordinator-defined volunteer job (e.g. Check-in Desk, Race Proctor)."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='volunteer_positions', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    color = fields.CharField(max_length=32, null=True)
    display_order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)
    # When both are set, the shift generator produces staggered rolling shifts
    # for this position instead of fixed shared blocks (overlapping windows
    # offset by ``stagger_minutes`` so handoffs happen one at a time).
    shift_length_minutes = fields.IntField(null=True)
    stagger_minutes = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    shifts = fields.ReverseRelation["VolunteerShift"]
    qualifications = fields.ReverseRelation["VolunteerQualification"]

    @property
    def is_staggered(self) -> bool:
        return bool(self.shift_length_minutes and self.stagger_minutes)

    class Meta:
        table = 'volunteerposition'
        unique_together = (('tenant', 'name'),)


class VolunteerShift(Model):
    """A fillable slot-set for a position over a time window (UTC)."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='volunteer_shifts', on_delete=fields.CASCADE)
    position = fields.ForeignKeyField('models.VolunteerPosition', related_name='shifts', on_delete=fields.CASCADE)
    starts_at = fields.DatetimeField(index=True)
    ends_at = fields.DatetimeField()
    label = fields.CharField(max_length=100, null=True)
    slots_needed = fields.IntField(default=1)
    notes = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    assignments = fields.ReverseRelation["VolunteerAssignment"]

    class Meta:
        table = 'volunteershift'
        indexes = (('position',),)  # starts_at is field-indexed; per-position lookups need position_id


class VolunteerAssignment(Model):
    """A volunteer placed into a shift."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='volunteer_assignments', on_delete=fields.CASCADE)
    shift = fields.ForeignKeyField('models.VolunteerShift', related_name='assignments', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='volunteer_assignments', on_delete=fields.CASCADE)
    assigned_by = fields.ForeignKeyField('models.User', related_name='volunteer_assignments_made', null=True, on_delete=fields.SET_NULL)
    auto_generated = fields.BooleanField(default=False)
    acknowledged_at = fields.DatetimeField(null=True)
    reminder_sent_at = fields.DatetimeField(null=True)
    checked_in_at = fields.DatetimeField(null=True)
    checked_in_by = fields.ForeignKeyField('models.User', related_name='volunteer_check_ins', null=True, on_delete=fields.SET_NULL)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteerassignment'
        unique_together = (('shift', 'user'),)
        indexes = (('user',),)  # composite is shift-first; user-only "my shifts" lookup uncovered


class VolunteerQualification(Model):
    """Capability matrix: which positions a user can fill."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='volunteer_qualifications', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='volunteer_qualifications', on_delete=fields.CASCADE)
    position = fields.ForeignKeyField('models.VolunteerPosition', related_name='qualifications', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteerqualification'
        unique_together = (('user', 'position'),)
        indexes = (('position',),)  # composite is user-first; position-only lookup uncovered


class VolunteerAvailability(Model):
    """A window a volunteer self-declares (UTC)."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='volunteer_availability', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='volunteer_availability', on_delete=fields.CASCADE)
    starts_at = fields.DatetimeField(index=True)
    ends_at = fields.DatetimeField()
    status = fields.CharEnumField(VolunteerAvailabilityStatus, default=VolunteerAvailabilityStatus.AVAILABLE, max_length=20)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteeravailability'
        indexes = (('user',),)  # starts_at is field-indexed; per-user reads need user_id


class PlayerAvailability(Model):
    """A window a player self-declares they can play (UTC)."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='player_availability', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='player_availability', on_delete=fields.CASCADE)
    starts_at = fields.DatetimeField(index=True)
    ends_at = fields.DatetimeField()
    status = fields.CharEnumField(VolunteerAvailabilityStatus, default=VolunteerAvailabilityStatus.AVAILABLE, max_length=20)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'playeravailability'
        indexes = (('user',),)  # starts_at is field-indexed; per-user reads need user_id


class ChallongeMatchState(str, Enum):
    """Mirrors Challonge's match states relevant to scheduling."""

    PENDING = 'pending'   # participants not yet fully determined
    OPEN = 'open'         # both participants known and ready to play
    COMPLETE = 'complete' # result recorded on Challonge


class ChallongeConnection(Model):
    """Single shared SGL service-account OAuth connection to Challonge.

    Only one connection is meaningful at a time; the most recently saved row is
    authoritative. Tokens are privileged secrets — surfaced only to STAFF and
    never logged.
    """

    id = fields.IntField(pk=True)
    # One connection per tenant: the most recent row for a tenant is
    # authoritative (each tenant links its own Challonge service account).
    tenant = fields.ForeignKeyField('models.Tenant', related_name='challonge_connections', on_delete=fields.CASCADE)
    access_token = fields.CharField(max_length=512)
    refresh_token = fields.CharField(max_length=512, null=True)
    token_expires_at = fields.DatetimeField(null=True)
    scopes = fields.CharField(max_length=255, null=True)
    challonge_username = fields.CharField(max_length=255, null=True)
    connected_by = fields.ForeignKeyField('models.User', related_name='challonge_connections', null=True, on_delete=fields.SET_NULL)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'challongeconnection'


class ChallongeParticipant(Model):
    """A Challonge participant in a linked tournament, mirrored into sglman.

    ``user`` is resolved by matching ``challonge_user_id`` to a player who has
    linked their Challonge identity; it stays null for participants we can't map
    to an sglman user.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='challonge_participants', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='challonge_participants', on_delete=fields.CASCADE)
    challonge_participant_id = fields.CharField(max_length=64)
    name = fields.CharField(max_length=255, null=True)
    challonge_user_id = fields.CharField(max_length=64, null=True)
    user = fields.ForeignKeyField('models.User', related_name='challonge_participations', null=True, on_delete=fields.SET_NULL)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'challongeparticipant'
        unique_together = (('tournament', 'challonge_participant_id'),)
        indexes = (('user',),)  # resolve participants for a linked sglman user


class ChallongeMatch(Model):
    """A Challonge bracket match mirrored into sglman.

    ``match`` links to the scheduled sglman :class:`Match` once a player has
    scheduled it; it is null while the matchup is still unscheduled.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='challonge_matches', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='challonge_matches', on_delete=fields.CASCADE)
    challonge_match_id = fields.CharField(max_length=64)
    round = fields.IntField(null=True)
    state = fields.CharEnumField(ChallongeMatchState, default=ChallongeMatchState.PENDING, max_length=20)
    participant1 = fields.ForeignKeyField('models.ChallongeParticipant', related_name='matches_as_p1', null=True, on_delete=fields.SET_NULL)
    participant2 = fields.ForeignKeyField('models.ChallongeParticipant', related_name='matches_as_p2', null=True, on_delete=fields.SET_NULL)
    winner_participant = fields.ForeignKeyField('models.ChallongeParticipant', related_name='matches_as_winner', null=True, on_delete=fields.SET_NULL)
    match = fields.ForeignKeyField('models.Match', related_name='challonge_match', null=True, on_delete=fields.SET_NULL)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'challongematch'
        unique_together = (('tournament', 'challonge_match_id'),)
        indexes = (('match',), ('participant1',), ('participant2',))


class ChallongeApiUsage(Model):
    """Per-calendar-month tally of real outbound Challonge API requests.

    One row per ``YYYY-MM`` period; incremented at the client's single HTTP
    choke point so we can show consumption against the monthly quota and decide
    whether more capacity is needed.
    """

    id = fields.IntField(pk=True)
    # Per-tenant connections mean per-tenant Challonge quotas: usage is tallied
    # per (tenant, period), not globally.
    tenant = fields.ForeignKeyField('models.Tenant', related_name='challonge_api_usage', on_delete=fields.CASCADE)
    period = fields.CharField(max_length=7)  # 'YYYY-MM' (UTC)
    request_count = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'challongeapiusage'
        unique_together = (('tenant', 'period'),)


class BotStatus(str, Enum):
    """Health of a racetime bot's websocket connection.

    The values are *written* by the PR 4 runtime (heartbeat/connect/error) and
    read by the platform health surface; in this PR the column exists but stays
    at its ``UNKNOWN`` default.
    """

    UNKNOWN = 'unknown'
    CONNECTED = 'connected'
    DISCONNECTED = 'disconnected'
    ERROR = 'error'


class RaceRoomStatus(str, Enum):
    """Cached racetime room lifecycle state (written by PR 4/6)."""

    OPEN = 'open'
    IN_PROGRESS = 'in_progress'
    FINISHED = 'finished'
    CANCELLED = 'cancelled'


class RacetimeBot(Model):
    """A shared, platform-managed racetime.gg bot for one game category.

    **Global** (no ``tenant`` FK) like the Discord token and VAPID keys: one bot
    per racetime category, holding that category's OAuth client credentials.
    SUPER_ADMIN authorizes tenants to use it through :class:`RacetimeBotTenant`.
    ``client_secret`` is a privileged secret — never surfaced to a tenant-facing
    response or logged. The websocket connection and the health-field *writes*
    land in PR 4; here the record and its admin surface exist.
    """

    id = fields.IntField(pk=True)
    category = fields.CharField(max_length=64, unique=True)
    client_id = fields.CharField(max_length=255)
    client_secret = fields.CharField(max_length=255)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)
    handler_class = fields.CharField(max_length=255, null=True)
    # Health fields — written by the PR 4 runtime, read by the platform health
    # page. Default to UNKNOWN until a live connection reports otherwise.
    status = fields.CharEnumField(BotStatus, default=BotStatus.UNKNOWN, max_length=20)
    status_message = fields.TextField(null=True)
    last_connected_at = fields.DatetimeField(null=True)
    last_checked_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    tenant_grants = fields.ReverseRelation["RacetimeBotTenant"]
    rooms = fields.ReverseRelation["RacetimeRoom"]
    tournaments = fields.ReverseRelation["Tournament"]

    class Meta:
        table = 'racetimebot'


class RacetimeBotTenant(Model):
    """SUPER_ADMIN authorization grant: a :class:`RacetimeBot` usable by a tenant.

    **Many-to-many** — a tenant may hold several categories; a category serves
    many tenants. Created on ``/platform`` with explicit ids (no ambient tenant
    scope); ``is_active`` lets a grant be suspended without deleting it.
    """

    id = fields.IntField(pk=True)
    bot = fields.ForeignKeyField('models.RacetimeBot', related_name='tenant_grants', on_delete=fields.CASCADE)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='racetime_bot_grants', on_delete=fields.CASCADE)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'racetimebottenant'
        unique_together = (('bot', 'tenant'),)


class RaceRoomProfile(Model):
    """Reusable racetime room settings a tournament can point at.

    Tenant-scoped; managed by ``SYNC_ADMIN``. These values become the racetime
    ``startrace`` parameters when the PR 4/6 room-creation flow opens a room, so
    a community defines its house rules once and reuses them across tournaments.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='race_room_profiles', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    goal = fields.CharField(max_length=255, null=True)
    invitational = fields.BooleanField(default=False)
    unlisted = fields.BooleanField(default=False)
    auto_start = fields.BooleanField(default=True)
    allow_comments = fields.BooleanField(default=True)
    allow_midrace_chat = fields.BooleanField(default=True)
    allow_non_entrant_chat = fields.BooleanField(default=True)
    chat_message_delay = fields.IntField(default=0)  # seconds
    start_delay = fields.IntField(default=15)  # seconds before an auto-started race begins
    time_limit = fields.IntField(default=24)  # hours before the room auto-closes
    streaming_required = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    tournaments = fields.ReverseRelation["Tournament"]

    class Meta:
        table = 'raceroomprofile'
        unique_together = (('tenant', 'name'),)


class RacetimeRoom(Model):
    """A racetime.gg race room record — its own model, not a slug on ``Match``.

    ``slug`` is **globally unique + indexed**: inbound racetime events carry only
    the slug (no tenant), so the reverse lookup is deliberately *unscoped* for
    tenant routing (see :class:`RacetimeRoomRepository.get_by_slug`, mirroring the
    ``ApiToken``→tenant pattern). Room creation and status *writes* land in
    PR 4/6; this PR defines the record.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='racetime_rooms', on_delete=fields.CASCADE)
    # SET_NULL: removing a bot must not erase the history of rooms it opened.
    bot = fields.ForeignKeyField(
        'models.RacetimeBot', related_name='rooms', null=True, on_delete=fields.SET_NULL
    )
    slug = fields.CharField(max_length=255, unique=True, index=True)
    category = fields.CharField(max_length=64)
    room_name = fields.CharField(max_length=255, null=True)
    status = fields.CharEnumField(RaceRoomStatus, default=RaceRoomStatus.OPEN, max_length=20)
    # SET_NULL: deleting a match detaches its room record rather than dropping it.
    match = fields.OneToOneField(
        'models.Match', related_name='racetime_room', null=True, on_delete=fields.SET_NULL
    )
    opened_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'racetimeroom'
        indexes = (('match',),)


class SyncStatus(str, Enum):
    """Reconciliation state of a synced SpeedGaming episode (PR 7).

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings, never the
    bare member (which repr's as ``SyncStatus.SYNCED``).
    """

    PENDING = 'pending'      # discovered upstream, not yet materialized
    SYNCED = 'synced'        # materialized/refreshed into a Match this cycle
    SKIPPED = 'skipped'      # a lifecycle guard held the refresh back
    CANCELLED = 'cancelled'  # upstream episode gone; the Match soft-detached
    ERROR = 'error'          # transform/load failed (see ``sync_error``)


class SpeedGamingEventLink(Model):
    """Config row wiring an SG event slug to a tenant tournament (PR 7).

    Tenant-scoped. The sync worker iterates the *active* links, polls the SG
    schedule API for each ``event_slug`` over a forward window, and materializes
    the returned episodes into the linked tournament's ``Match`` rows. The
    observability fields (``last_synced_at`` / ``last_status`` / ``last_error``)
    make sync health visible in the admin UI without reading the audit log.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='sg_event_links', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='sg_event_links', on_delete=fields.CASCADE)
    event_slug = fields.CharField(max_length=128)
    # Optional SG ``content_type`` filter (a specific bracket within an event).
    content_type = fields.CharField(max_length=64, null=True)
    active = fields.BooleanField(default=True)
    # Poll cadence; the worker skips a link whose ``last_synced_at`` is newer.
    sync_interval_minutes = fields.IntField(default=15)
    # How far ahead (hours) to pull episodes on each poll.
    lookahead_hours = fields.IntField(default=72)
    last_synced_at = fields.DatetimeField(null=True)
    last_status = fields.CharField(max_length=32, null=True)
    last_error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    episodes = fields.ReverseRelation["SpeedGamingEpisode"]

    class Meta:
        table = 'speedgamingeventlink'
        unique_together = (('tenant', 'tournament', 'event_slug'),)
        indexes = (('tenant',), ('tournament',))


class SpeedGamingEpisode(Model):
    """A synced SpeedGaming schedule episode — the ETL staging record (PR 7).

    Tenant-scoped, unique ``(tenant, sg_episode_id)``. Holds the raw upstream
    payload snapshot plus a ``content_hash`` so an unchanged re-sync is a cheap
    no-op. The materialized SGLMan ``Match`` is reachable via the reverse of
    ``Match.speedgaming_episode`` (that FK is the canonical source marker; there
    is no second column here).
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='sg_episodes', on_delete=fields.CASCADE)
    event_link = fields.ForeignKeyField(
        'models.SpeedGamingEventLink', related_name='episodes', null=True, on_delete=fields.SET_NULL
    )
    sg_episode_id = fields.CharField(max_length=64)
    title = fields.CharField(max_length=255, null=True)
    scheduled_at = fields.DatetimeField(null=True)
    payload = fields.JSONField(null=True)
    content_hash = fields.CharField(max_length=64, null=True)
    sync_status = fields.CharEnumField(SyncStatus, default=SyncStatus.PENDING, max_length=20)
    synced_at = fields.DatetimeField(null=True)
    sync_error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields — the materialized Match (reverse of Match.speedgaming_episode)
    match: fields.ReverseRelation["Match"]

    class Meta:
        table = 'speedgamingepisode'
        unique_together = (('tenant', 'sg_episode_id'),)
        indexes = (('tenant',), ('event_link',))


class DiscordEventSource(str, Enum):
    """What SGLMan schedule row a mirrored Discord event came from (PR 8).

    The ``DiscordScheduledEvent`` link is polymorphic: ``(source_type, source_id)``
    identifies the SGLMan row a Discord Scheduled Event mirrors. Today only
    ``MATCH`` is materialized (native + SG-imported matches both live in ``Match``);
    qualifier windows / live races join later without a schema change.

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings.
    """

    MATCH = 'match'


class DiscordScheduledEvent(Model):
    """A Discord Scheduled Event mirrored from an SGLMan schedule row (PR 8).

    Tenant-scoped reconciliation link. The reconciler keeps the tenant guild's
    Scheduled Events in sync with its schedule: ``content_hash`` drives
    update-vs-noop, and the working set is **only this tenant's own rows** —
    never every event in the guild — so a shared guild never has a sibling
    tenant's events cancelled (``discord_guild_id`` is not unique).

    Uniqueness: ``discord_event_id`` is globally unique (one link per Discord
    event); ``(tenant, source_type, source_id)`` is unique for idempotency (one
    mirrored event per source row).
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='discord_scheduled_events', on_delete=fields.CASCADE)
    # The guild the event lives in, snapshotted from ``Tenant.discord_guild_id``
    # at creation so a later re-link doesn't silently orphan the row.
    guild_id = fields.BigIntField()
    discord_event_id = fields.BigIntField(unique=True)
    source_type = fields.CharEnumField(DiscordEventSource, max_length=20)
    source_id = fields.IntField()
    title = fields.CharField(max_length=255)
    scheduled_at = fields.DatetimeField(null=True)
    content_hash = fields.CharField(max_length=64, null=True)
    synced_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'discordscheduledevent'
        unique_together = (('tenant', 'source_type', 'source_id'),)
        indexes = (('tenant',), ('guild_id',))


class AsyncQualifierRunStatus(str, Enum):
    """Execution state of a single async-qualifier run (PR 9).

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings, never the
    bare member (which repr's as ``AsyncQualifierRunStatus.FINISHED``).

    Web-first collapses reveal and start, so a run is created ``IN_PROGRESS`` the
    moment a player draws (the permalink is revealed then). ``PENDING`` is
    reserved for a run pre-created before a synchronous start — the live-race path
    (PR 10) — and is unused by the self-paced core flow.
    """

    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    FINISHED = 'finished'
    FORFEIT = 'forfeit'
    DISQUALIFIED = 'disqualified'


class AsyncQualifierReviewStatus(str, Enum):
    """Review state of a finished async-qualifier run (PR 9)."""

    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class AsyncQualifier(Model):
    """A self-paced permalink-pool qualifier — a peer aggregate of ``Tournament``.

    Created/administered like a tournament (per-qualifier ``admins`` M2M, an admin
    tab, ``is_active``) but a **distinct state machine** entirely outside the
    Match/schedule system: window opens → players draw permalinks from pools →
    runs (in-progress → finished/forfeit) → review (pending → approved/rejected) →
    scored leaderboard → window closes.

    Tenant-scoped. Typed **window columns** (``opens_at``/``closes_at``) plus
    ``runs_per_pool`` / ``allowed_reattempts`` are worker-/query-facing knobs; the
    validated-JSON ``config`` blob carries scoring/reattempt/messaging strategy
    (the hybrid config decision). ``admins`` is the reviewer set (self-review is
    blocked in the service).
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='async_qualifiers', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    # Informational only: the event this qualifier feeds. No structural FK — the
    # two machines share no workflow (decisions log).
    event_name = fields.CharField(max_length=255, null=True)
    opens_at = fields.DatetimeField(null=True)
    closes_at = fields.DatetimeField(null=True)
    runs_per_pool = fields.IntField(default=1)
    allowed_reattempts = fields.IntField(default=0)
    config = fields.JSONField(null=True)
    is_active = fields.BooleanField(default=True)
    admins = fields.ManyToManyField(
        'models.User', related_name='admin_async_qualifiers', through='AsyncQualifierAdmins'
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    pools = fields.ReverseRelation["AsyncQualifierPool"]
    runs = fields.ReverseRelation["AsyncQualifierRun"]

    class Meta:
        table = 'asyncqualifier'
        indexes = (('tenant',),)


class AsyncQualifierPool(Model):
    """A named permalink pool inside a qualifier, optionally tied to a preset (PR 9).

    ``preset`` records which preset the pool's permalinks were rolled from
    (SET_NULL so deleting the preset detaches rather than cascade-deletes the
    pool). ``live_race`` permalinks in the pool run synchronously on racetime
    (PR 10); the flag lives on the permalink, not the pool.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='async_qualifier_pools', on_delete=fields.CASCADE)
    qualifier = fields.ForeignKeyField('models.AsyncQualifier', related_name='pools', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    preset = fields.ForeignKeyField(
        'models.Preset', related_name='async_qualifier_pools', null=True, on_delete=fields.SET_NULL
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    permalinks = fields.ReverseRelation["AsyncQualifierPermalink"]

    class Meta:
        table = 'asyncqualifierpool'
        unique_together = (('qualifier', 'name'),)
        indexes = (('tenant',), ('qualifier',))


class AsyncQualifierPermalink(Model):
    """One seed permalink in a pool; ``par_time`` is maintained from approved runs (PR 9).

    ``par_time`` (whole seconds) is the mean of the N fastest finished+approved
    runs on this permalink, recomputed by the scoring path; ``par_updated_at``
    timestamps that recompute. ``live_race`` marks a permalink reserved for a
    synchronous racetime run (PR 10).
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='async_qualifier_permalinks', on_delete=fields.CASCADE)
    pool = fields.ForeignKeyField('models.AsyncQualifierPool', related_name='permalinks', on_delete=fields.CASCADE)
    url = fields.CharField(max_length=1024)
    notes = fields.TextField(null=True)
    live_race = fields.BooleanField(default=False)
    par_time = fields.IntField(null=True)
    par_updated_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    runs = fields.ReverseRelation["AsyncQualifierRun"]

    class Meta:
        table = 'asyncqualifierpermalink'
        indexes = (('tenant',), ('pool',))


class AsyncQualifierRun(Model):
    """A player's single attempt at a drawn permalink (PR 9).

    Created ``IN_PROGRESS`` at draw time (web-first collapses reveal + start):
    the ``permalink`` is assigned inside a locked transaction so concurrent draws
    can't double-assign, ``started_at`` is server-stamped, and the player later
    submits ``elapsed_seconds`` + ``runner_vod_url`` (→ ``FINISHED``) or forfeits.
    Finished runs enter review (``review_status``); an approved run is par-scored.

    ``reattempted`` + ``reattempt_reason`` are the one-attempt integrity backstop:
    a reattempt voids the prior run (excluded from par/scoring/played-count),
    frees the pool slot, requires a reason, and is limited by
    ``AsyncQualifier.allowed_reattempts``. ``permalink`` is SET_NULL so purging a
    permalink keeps run history. ``live_race`` (PR 10) is set on runs captured
    from a synchronous racetime race and is ``None`` for self-paced runs.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='async_qualifier_runs', on_delete=fields.CASCADE)
    qualifier = fields.ForeignKeyField('models.AsyncQualifier', related_name='runs', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='async_qualifier_runs')
    permalink = fields.ForeignKeyField(
        'models.AsyncQualifierPermalink', related_name='runs', null=True, on_delete=fields.SET_NULL
    )
    # Set for runs captured from a synchronous racetime race (PR 10); SET_NULL so
    # deleting a live race keeps the captured run history.
    live_race = fields.ForeignKeyField(
        'models.AsyncQualifierLiveRace', related_name='runs', null=True, on_delete=fields.SET_NULL
    )
    status = fields.CharEnumField(AsyncQualifierRunStatus, default=AsyncQualifierRunStatus.IN_PROGRESS, max_length=20)
    review_status = fields.CharEnumField(
        AsyncQualifierReviewStatus, default=AsyncQualifierReviewStatus.PENDING, max_length=20
    )
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    # Self-reported elapsed run time in whole seconds (submitted by the player).
    elapsed_seconds = fields.IntField(null=True)
    runner_vod_url = fields.CharField(max_length=1024, null=True)
    reattempted = fields.BooleanField(default=False)
    reattempt_reason = fields.TextField(null=True)
    # Par score in [0, 105]; null until an approved run is scored.
    score = fields.FloatField(null=True)
    reviewed_by = fields.ForeignKeyField(
        'models.User', related_name='reviewed_async_qualifier_runs', null=True, on_delete=fields.SET_NULL
    )
    reviewed_at = fields.DatetimeField(null=True)
    # Claim-locking so two reviewers don't collide on the same run.
    review_claimed_by = fields.ForeignKeyField(
        'models.User', related_name='claimed_async_qualifier_runs', null=True, on_delete=fields.SET_NULL
    )
    review_claimed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    review_notes = fields.ReverseRelation["AsyncQualifierReviewNote"]

    class Meta:
        table = 'asyncqualifierrun'
        indexes = (
            ('tenant',),
            ('qualifier', 'review_status'),  # reviewer queue
            ('user',),                       # "my runs"
            ('permalink',),                  # par recompute
        )


class AsyncQualifierReviewNote(Model):
    """A reviewer's note attached to a run during review (PR 9)."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='async_qualifier_review_notes', on_delete=fields.CASCADE)
    run = fields.ForeignKeyField('models.AsyncQualifierRun', related_name='review_notes', on_delete=fields.CASCADE)
    author = fields.ForeignKeyField('models.User', related_name='authored_async_qualifier_review_notes')
    note = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'asyncqualifierreviewnote'
        indexes = (('tenant',), ('run',))


class AsyncQualifierLiveRaceStatus(str, Enum):
    """Lifecycle of a synchronous racetime qualifier race (PR 10).

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings, never the
    bare member (which repr's as ``AsyncQualifierLiveRaceStatus.FINISHED``).

    ``SCHEDULED`` before a room opens, ``PENDING`` once a room exists but the race
    has not started, ``IN_PROGRESS`` while racing, ``FINISHED`` once the entrants'
    results are captured into runs.
    """

    SCHEDULED = 'scheduled'
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    FINISHED = 'finished'


class AsyncQualifierLiveRace(Model):
    """A synchronous racetime race whose results flow into ``AsyncQualifierRun``s (PR 10).

    A pool permalink flagged ``live_race`` is raced live on racetime instead of
    self-paced: every entrant runs the same ``permalink`` in one room, and on
    finish each racetime entrant is mapped back to a ``User`` and captured as an
    ``AsyncQualifierRun`` (racetime status → run status; ``end_time`` → elapsed).
    Live-race runs **skip reviewer sign-off** — the racetime result is
    self-attributing — and are par-scored like any other approved run.

    Reuses the PR 4/6 racetime subsystem: opening a live race creates a
    :class:`RacetimeRoom` (with ``match=None``) whose lifecycle events the shared
    handler routes here by slug. ``racetime_slug`` mirrors that room's slug and is
    globally unique (nullable until a room opens). ``episode`` optionally links an
    SG-imported episode this race stands in for.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='async_qualifier_live_races', on_delete=fields.CASCADE)
    pool = fields.ForeignKeyField('models.AsyncQualifierPool', related_name='live_races', on_delete=fields.CASCADE)
    # SET_NULL so purging a permalink keeps the live-race record + captured runs.
    permalink = fields.ForeignKeyField(
        'models.AsyncQualifierPermalink', related_name='live_races', null=True, on_delete=fields.SET_NULL
    )
    match_title = fields.CharField(max_length=255)
    # Mirrors the RacetimeRoom slug; globally unique like the room's, nullable
    # until a room is opened (multiple NULLs are allowed).
    racetime_slug = fields.CharField(max_length=255, unique=True, null=True)
    episode = fields.ForeignKeyField(
        'models.SpeedGamingEpisode', related_name='async_qualifier_live_races', null=True,
        on_delete=fields.SET_NULL,
    )
    status = fields.CharEnumField(
        AsyncQualifierLiveRaceStatus, default=AsyncQualifierLiveRaceStatus.SCHEDULED, max_length=20
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    runs = fields.ReverseRelation["AsyncQualifierRun"]

    class Meta:
        table = 'asyncqualifierliverace'
        indexes = (('tenant',), ('pool',))
