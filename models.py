from enum import Enum

from tortoise import fields
from tortoise.models import Model


class Role(str, Enum):
    STAFF = 'staff'
    PROCTOR = 'proctor'
    STREAM_MANAGER = 'stream_manager'
    TRIFORCE_SUBMITTER = 'triforce_submitter'
    VOLUNTEER_COORDINATOR = 'volunteer_coordinator'


class VolunteerAvailabilityStatus(str, Enum):
    AVAILABLE = 'available'
    UNAVAILABLE = 'unavailable'
    PREFERRED = 'preferred'

class User(Model):
    id = fields.IntField(pk=True)
    discord_id = fields.BigIntField(unique=True)
    access_token = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    username = fields.CharField(max_length=150)
    display_name = fields.CharField(max_length=150, null=True)
    pronouns = fields.CharField(max_length=50, null=True)
    is_active = fields.BooleanField(default=True)
    dm_notifications = fields.BooleanField(default=True)

    # related fields
    admin_tournaments = fields.ManyToManyRelation["Tournament"]
    crew_coordinated_tournaments = fields.ManyToManyRelation["Tournament"]
    match_players = fields.ReverseRelation["MatchPlayers"]
    match_acknowledgments = fields.ReverseRelation["MatchAcknowledgment"]
    tournament_players = fields.ReverseRelation["TournamentPlayers"]
    tournament_notifications = fields.ReverseRelation["TournamentNotificationPreference"]
    teams = fields.ReverseRelation["UserTeams"]
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
    volunteer_profile = fields.ReverseRelation["VolunteerProfile"]
    volunteer_assignments = fields.ReverseRelation["VolunteerAssignment"]
    volunteer_assignments_made = fields.ReverseRelation["VolunteerAssignment"]
    volunteer_qualifications = fields.ReverseRelation["VolunteerQualification"]
    volunteer_availability = fields.ReverseRelation["VolunteerAvailability"]

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

class UserTeams(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='teams')
    team = fields.ForeignKeyField('models.Team', related_name='members')
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class TestModel(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    value = fields.IntField()
    somethingelse = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

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
    teams = fields.ReverseRelation["Team"]
    announcements = fields.ReverseRelation["Announcement"]
    notification_preferences = fields.ReverseRelation["TournamentNotificationPreference"]
    triforce_texts = fields.ReverseRelation["TriforceText"]

class Match(Model):
    id = fields.IntField(pk=True)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='matches')
    stream_room = fields.ForeignKeyField('models.StreamRoom', related_name='matches', null=True)
    scheduled_at = fields.DatetimeField(null=True)
    seated_at = fields.DatetimeField(null=True) # now known as "Checked In"
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    confirmed_at = fields.DatetimeField(null=True)
    comment = fields.TextField(null=True)
    is_stream_candidate = fields.BooleanField(default=False)
    title = fields.CharField(max_length=255, null=True)
    generated_seed = fields.ForeignKeyField('models.GeneratedSeeds', related_name='matches', null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    acknowledgments = fields.ReverseRelation["MatchAcknowledgment"]

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
    approved_by = fields.ForeignKeyField('models.User', related_name='approved_commentaries', null=True)
    acknowledged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class Tracker(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='trackers')
    match = fields.ForeignKeyField('models.Match', related_name='trackers')
    approved = fields.BooleanField(default=False)
    approved_by = fields.ForeignKeyField('models.User', related_name='approved_trackers', null=True)
    acknowledged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class MatchWatcher(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='watched_matches', on_delete=fields.CASCADE)
    match = fields.ForeignKeyField('models.Match', related_name='watchers', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'match')
        table = 'matchwatcher'

class Team(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='teams')
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class AuditLog(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='audit_logs')
    action = fields.CharField(max_length=255)
    details = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

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

class Announcement(Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    content = fields.TextField()
    is_active = fields.BooleanField(default=True)
    important = fields.BooleanField(default=False)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='announcements', null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class UserRole(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='roles')
    role = fields.CharEnumField(Role, max_length=32)
    granted_by = fields.ForeignKeyField('models.User', related_name='granted_roles', null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'role')
        table = 'userrole'

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
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    shifts = fields.ReverseRelation["VolunteerShift"]
    qualifications = fields.ReverseRelation["VolunteerQualification"]

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
