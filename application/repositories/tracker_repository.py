"""
Tracker Repository - Data Access Layer

Handles all database operations for Tracker model.
"""

from models import Tracker

from application.repositories._crew_repository import CrewRepository


class TrackerRepository(CrewRepository[Tracker]):
    """Repository for tracker-related data access."""

    model = Tracker
