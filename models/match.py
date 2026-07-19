from tortoise import fields
from tortoise.models import Model


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
    # (``scheduled_at``, players, ``tournament``) read-only in Wizzrobe — the guard
    # lives in ``MatchService.update_match``. SET_NULL so purging a synced episode
    # soft-detaches the Match (everything Wizzrobe added on top survives) rather
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
