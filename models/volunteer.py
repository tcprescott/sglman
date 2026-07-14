from tortoise import fields
from tortoise.models import Model

from .enums import VolunteerAvailabilityStatus


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
