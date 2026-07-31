"""
Commentator Repository - Data Access Layer

Handles all database operations for Commentator model.
"""

from application.repositories._crew_repository import CrewRepository
from models import Commentator


class CommentatorRepository(CrewRepository[Commentator]):
    """Repository for commentator-related data access."""

    model = Commentator
