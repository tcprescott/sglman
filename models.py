from enum import Enum

from tortoise import fields
from tortoise.models import Model


class Role(str, Enum):
    STAFF = 'staff'
    PROCTOR = 'proctor'
    STREAM_MANAGER = 'stream_manager'

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

    @property
    def preferred_name(self) -> str:
        return self.display_name if self.display_name else self.username

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
