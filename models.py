from enum import IntEnum

from tortoise import fields
from tortoise.models import Model


class Permissions(IntEnum):
    USER = 0
    TOURNAMENT_ADMIN = 1
    SUPERADMIN = 2

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
    permission = fields.IntEnumField(Permissions, default=Permissions.USER.value)

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
    staff_administered = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class Match(Model):
    id = fields.IntField(pk=True)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='matches')
    stream_room = fields.ForeignKeyField('models.StreamRoom', related_name='matches', null=True)
    scheduled_at = fields.DatetimeField(null=True)
    seated_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    comment = fields.TextField(null=True)
    generated_seed = fields.ForeignKeyField('models.GeneratedSeeds', related_name='matches', null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    @property
    def is_seated(self) -> bool:
        return self.seated_at is not None

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

class MatchPlayers(Model):
    id = fields.IntField(pk=True)
    match = fields.ForeignKeyField('models.Match', related_name='players')
    user = fields.ForeignKeyField('models.User', related_name='match_players')
    confirmed = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class TournamentPlayers(Model):
    id = fields.IntField(pk=True)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='players')
    user = fields.ForeignKeyField('models.User', related_name='tournament_players')
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

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
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class Tracker(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='trackers')
    match = fields.ForeignKeyField('models.Match', related_name='trackers')
    approved = fields.BooleanField(default=False)
    approved_by = fields.ForeignKeyField('models.User', related_name='approved_trackers', null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

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