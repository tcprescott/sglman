from tortoise import fields
from tortoise.models import Model

from .enums import Role, RoleSource


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
