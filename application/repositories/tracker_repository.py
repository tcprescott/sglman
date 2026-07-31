"""
Tracker Repository - Data Access Layer

Handles all database operations for Tracker model.
"""

from application.repositories._crew_repository import CrewRepository
from models import Tracker


class TrackerRepository(CrewRepository[Tracker]):
    """Repository for tracker-related data access."""

    model = Tracker
