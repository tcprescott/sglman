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


class User(Model):
    id = fields.IntField(pk=True)
    discord_id = fields.BigIntField(unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    username = fields.CharField(max_length=150)
    display_name = fields.CharField(max_length=150, null=True)
    pronouns = fields.CharField(max_length=50, null=True)
    is_active = fields.BooleanField(default=True)
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
    volunteer_profile = fields.ReverseRelation["VolunteerProfile"]
    volunteer_assignments = fields.ReverseRelation["VolunteerAssignment"]
    volunteer_assignments_made = fields.ReverseRelation["VolunteerAssignment"]
    volunteer_qualifications = fields.ReverseRelation["VolunteerQualification"]
    volunteer_availability = fields.ReverseRelation["VolunteerAvailability"]
    challonge_participations = fields.ReverseRelation["ChallongeParticipant"]
    web_push_subscriptions = fields.ReverseRelation["WebPushSubscription"]

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
    user = fields.ForeignKeyField('models.User', related_name='feedback_submissions', on_delete=fields.CASCADE)
    category = fields.CharEnumField(FeedbackCategory, default=FeedbackCategory.OTHER, max_length=20)
    message = fields.TextField()
    page_url = fields.CharField(max_length=512)
    status = fields.CharEnumField(FeedbackStatus, default=FeedbackStatus.NEW, max_length=20)
    created_at = fields.DatetimeField(auto_now_add=True)
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
    asset_number = fields.IntField(unique=True)
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


class EquipmentLoan(Model):
    """A single checkout of an :class:`Equipment` asset.

    The open loan (``checked_in_at`` is null) identifies the current holder;
    closed loans form the asset's full lending history.
    """

    id = fields.IntField(pk=True)
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


class Tournament(Model):
    id = fields.IntField(pk=True)
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

class MatchPlayers(Model):
    id = fields.IntField(pk=True)
    match = fields.ForeignKeyField('models.Match', related_name='players')
    user = fields.ForeignKeyField('models.User', related_name='match_players')
    finish_rank = fields.IntField(null=True)
    assigned_station = fields.CharField(max_length=50, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('match', 'user'),)
        table = 'matchplayers'

class MatchAcknowledgment(Model):
    id = fields.IntField(pk=True)
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
    tournament = fields.ForeignKeyField('models.Tournament', related_name='players')
    user = fields.ForeignKeyField('models.User', related_name='tournament_players')
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('tournament', 'user'),)
        table = 'tournamentplayers'

class MatchNotificationLevel(str, Enum):
    NONE = 'none'
    STREAMED = 'streamed'
    STREAMED_AND_CANDIDATES = 'streamed_and_candidates'
    ALL = 'all'

class TournamentNotificationPreference(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='tournament_notifications')
    tournament = fields.ForeignKeyField('models.Tournament', related_name='notification_preferences')
    match_notifications = fields.CharEnumField(MatchNotificationLevel, default=MatchNotificationLevel.NONE, max_length=30)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'tournament')
        table = 'tournamentnotificationpreference'

class StreamRoom(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True)
    stream_url = fields.CharField(max_length=255, null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class Commentator(Model):
    id = fields.IntField(pk=True)
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
    user = fields.ForeignKeyField('models.User', related_name='watched_matches', on_delete=fields.CASCADE)
    match = fields.ForeignKeyField('models.Match', related_name='watchers', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'match')
        table = 'matchwatcher'

class AuditLog(Model):
    id = fields.IntField(pk=True)
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
    seed_url = fields.CharField(max_length=255)
    seed_info = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class SystemConfiguration(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True)
    value = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class Webhook(Model):
    id = fields.IntField(pk=True)
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
    role = fields.CharEnumField(Role, max_length=32)
    # SET_NULL: deleting the granter must not revoke roles they granted to others.
    granted_by = fields.ForeignKeyField(
        'models.User', related_name='granted_roles', null=True, on_delete=fields.SET_NULL
    )
    source = fields.CharEnumField(RoleSource, max_length=16, default=RoleSource.MANUAL)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'role')
        table = 'userrole'


class DiscordRoleMapping(Model):
    id = fields.IntField(pk=True)
    guild_id = fields.BigIntField()
    discord_role_id = fields.BigIntField()
    discord_role_name = fields.CharField(max_length=100)
    app_role = fields.CharEnumField(Role, max_length=32)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('guild_id', 'discord_role_id', 'app_role')
        table = 'discordrolemapping'

class TriforceText(Model):
    id = fields.IntField(pk=True)
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


class VolunteerProfile(Model):
    """Per-user opt-in record for onsite volunteering.

    Any logged-in user can opt in; only users with ``opted_in_at`` set are
    assignable / appear in the coordinator's pool.
    """

    id = fields.IntField(pk=True)
    user = fields.OneToOneField('models.User', related_name='volunteer_profile', on_delete=fields.CASCADE)
    opted_in_at = fields.DatetimeField(null=True)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteerprofile'


class VolunteerPosition(Model):
    """A coordinator-defined volunteer job (e.g. Check-in Desk, Race Proctor)."""

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, unique=True)
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


class VolunteerShift(Model):
    """A fillable slot-set for a position over a time window (UTC)."""

    id = fields.IntField(pk=True)
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


class VolunteerAssignment(Model):
    """A volunteer placed into a shift."""

    id = fields.IntField(pk=True)
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


class VolunteerQualification(Model):
    """Capability matrix: which positions a user can fill."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='volunteer_qualifications', on_delete=fields.CASCADE)
    position = fields.ForeignKeyField('models.VolunteerPosition', related_name='qualifications', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteerqualification'
        unique_together = (('user', 'position'),)


class VolunteerAvailability(Model):
    """A window a volunteer self-declares (UTC)."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='volunteer_availability', on_delete=fields.CASCADE)
    starts_at = fields.DatetimeField(index=True)
    ends_at = fields.DatetimeField()
    status = fields.CharEnumField(VolunteerAvailabilityStatus, default=VolunteerAvailabilityStatus.AVAILABLE, max_length=20)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'volunteeravailability'


class PlayerAvailability(Model):
    """A window a player self-declares they can play (UTC)."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='player_availability', on_delete=fields.CASCADE)
    starts_at = fields.DatetimeField(index=True)
    ends_at = fields.DatetimeField()
    status = fields.CharEnumField(VolunteerAvailabilityStatus, default=VolunteerAvailabilityStatus.AVAILABLE, max_length=20)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'playeravailability'


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


class ChallongeMatch(Model):
    """A Challonge bracket match mirrored into sglman.

    ``match`` links to the scheduled sglman :class:`Match` once a player has
    scheduled it; it is null while the matchup is still unscheduled.
    """

    id = fields.IntField(pk=True)
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


class ChallongeApiUsage(Model):
    """Per-calendar-month tally of real outbound Challonge API requests.

    One row per ``YYYY-MM`` period; incremented at the client's single HTTP
    choke point so we can show consumption against the monthly quota and decide
    whether more capacity is needed.
    """

    id = fields.IntField(pk=True)
    period = fields.CharField(max_length=7, unique=True)  # 'YYYY-MM' (UTC)
    request_count = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'challongeapiusage'
