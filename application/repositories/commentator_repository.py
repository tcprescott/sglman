"""
Commentator Repository - Data Access Layer

Handles all database operations for Commentator model.
"""

from models import Commentator

from application.repositories._crew_repository import CrewRepository


class CommentatorRepository(CrewRepository[Commentator]):
    """Repository for commentator-related data access."""

    model = Commentator
