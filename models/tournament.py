from tortoise import fields
from tortoise.models import Model

from .enums import MatchNotificationLevel


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
    # Per-tournament "tournament days" override (see docs/timezone-handling and
    # SystemConfigService). Each is nullable and falls back to the tenant-wide
    # setting when unset: ``event_start_date`` / ``event_end_date`` override the
    # event date window, and ``tournament_hours`` overrides the per-date open/close
    # windows — same JSON shape as the tenant's ``tournament_hours_by_date`` blob,
    # ``{"YYYY-MM-DD": {"open": "HH:MM", "close": "HH:MM"}}``. Resolved at the
    # scheduling/suggestion use-sites via ``SystemConfigService`` (tenant default
    # takes over whenever the tournament leaves a field unset).
    event_start_date = fields.DateField(null=True)
    event_end_date = fields.DateField(null=True)
    tournament_hours = fields.JSONField(null=True)
    admins = fields.ManyToManyField('models.User', related_name='admin_tournaments', through='TournamentAdmins')
    crew_coordinators = fields.ManyToManyField(
        'models.User',
        related_name='crew_coordinated_tournaments',
        through='TournamentCrewCoordinators',
    )
    # How much approved crew a *stream candidate* needs before the coverage
    # reports call it covered. Not every tournament runs the same crew shape —
    # plenty stream with commentary and no tracker — and without this the
    # reports assumed one of each and showed those tournaments a permanent
    # false gap and a depressed health score. ``0`` means the role is not used
    # here; the defaults reproduce the old assumption for existing rows.
    #
    # Read by ``ReportsService.crew_coverage`` and
    # ``AnalyticsService.tournament_health`` (through
    # ``reporting_shared.is_crew_covered``), and by the schedule board, which
    # hides Sign up for a role requiring ``0`` — ``CrewService.signup_crew``
    # refuses it too, since hiding a control is not enforcing a rule. Withdrawing
    # stays open at any requirement, so a signup made before the setting changed
    # can still be removed.
    required_commentators = fields.IntField(default=1)
    required_trackers = fields.IntField(default=1)
    staff_administered = fields.BooleanField(default=False)
    # Whether players may schedule matches themselves outside a bracket
    # (``MatchService.submit_match_request``). Turned off automatically when a
    # native bracket is created or a Challonge bracket is linked: a bracket-run
    # tournament schedules only the matchups the bracket produced. Staff can turn
    # it back on per tournament.
    allow_player_match_requests = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    players = fields.ReverseRelation["TournamentPlayers"]
    matches = fields.ReverseRelation["Match"]
    notification_preferences = fields.ReverseRelation["TournamentNotificationPreference"]
    triforce_texts = fields.ReverseRelation["TriforceText"]
    challonge_participants = fields.ReverseRelation["ChallongeParticipant"]
    challonge_matches = fields.ReverseRelation["ChallongeMatch"]

    @property
    def is_racetime_enabled(self) -> bool:
        """True when this tournament is wired to a racetime.gg category.

        A racetime tournament runs online — the race room drives the match
        lifecycle — so on-site-only actions (check-in/seating, station
        assignment) are disabled for it. ``racetime_bot`` is the FK that names
        the category; its ``racetime_bot_id`` is always loaded with the row, so
        this never triggers a query.
        """
        return self.racetime_bot_id is not None


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


class GeneratedSeeds(Model):
    """One rolled seed, with the provenance a disputed result asks for.

    ``seed_url`` alone cannot answer "what settings produced this?" — a
    :class:`Preset` is an editable row, so editing one silently rewrites the
    apparent history of every seed rolled from it. ``settings_snapshot`` is
    therefore the resolved payload **as sent upstream**, captured at roll time and
    never updated; ``preset`` records which preset was selected, and the two
    together survive any later edit. ``provider_meta`` carries what the roll cost
    (attempts, latency, surface) from the seed-provider envelope.

    No credential is ever part of the snapshot: randomizer keys are resolved
    separately and never merged into a settings payload.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='generated_seeds', on_delete=fields.CASCADE)
    seed_url = fields.CharField(max_length=255)
    seed_info = fields.TextField(null=True)
    # Which backend actually rolled it — ``Tournament.seed_generator`` and the
    # preset FK can both change afterwards, so the name is stamped here.
    randomizer = fields.CharField(max_length=32, null=True)
    preset = fields.ForeignKeyField(
        'models.Preset', related_name='generated_seeds', null=True, on_delete=fields.SET_NULL
    )
    settings_snapshot = fields.JSONField(null=True)
    # SET_NULL: deleting the roller must not delete the seed record.
    rolled_by = fields.ForeignKeyField(
        'models.User', related_name='rolled_seeds', null=True, on_delete=fields.SET_NULL
    )
    provider_meta = fields.JSONField(null=True)
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


class RandomizerCredential(Model):
    """A community's own credential for one randomizer's key-gated upstream API.

    Randomizer credentials are per tenant, not per deployment: each community
    supplies the key it was issued and is bound by its terms, rather than every
    community rolling on the operator's. Which credentials exist is declared in
    ``application/randomizer_credentials.py``; ``(randomizer, key)`` points at a
    ``CredentialSpec`` there.

    ``value`` is stored in plaintext (like ``RacetimeBot.client_secret`` and
    ``Webhook.secret``) and is **privileged**: ``RandomizerCredentialService``
    never returns it to a caller other than seed generation, and never writes it
    into an audit entry.
    """
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField(
        'models.Tenant', related_name='randomizer_credentials', on_delete=fields.CASCADE
    )
    randomizer = fields.CharField(max_length=32)
    key = fields.CharField(max_length=64)
    value = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'randomizercredential'
        unique_together = (('tenant', 'randomizer', 'key'),)
        indexes = (('tenant',),)


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
