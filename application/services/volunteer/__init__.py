"""Volunteer services — profiles, positions, shifts, and scheduling.

``VolunteerScheduleService`` builds and publishes the shift roster,
``VolunteerAutoscheduleService`` proposes a draft fill from availability +
qualifications, and ``volunteer_reminder`` is the background sweep that DMs
upcoming shifts (stamping ``reminder_sent_at`` before the send so a restart
resumes rather than double-notifies).
"""

from application.services.volunteer import volunteer_reminder
from application.services.volunteer.volunteer_autoschedule_service import (
    VolunteerAutoscheduleService,
)
from application.services.volunteer.volunteer_availability_service import (
    VolunteerAvailabilityService,
)
from application.services.volunteer.volunteer_position_service import VolunteerPositionService
from application.services.volunteer.volunteer_profile_service import VolunteerProfileService
from application.services.volunteer.volunteer_qualification_service import (
    VolunteerQualificationService,
)
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService

__all__ = [
    'VolunteerAutoscheduleService',
    'VolunteerAvailabilityService',
    'VolunteerPositionService',
    'VolunteerProfileService',
    'VolunteerQualificationService',
    'VolunteerScheduleService',
    'volunteer_reminder',
]
