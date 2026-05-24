"""
Triforce Text Service - Business Logic Layer

Manages community-submitted texts that may be embedded in randomizer seeds.

Ported from sahasrahbot's ``alttprbot/util/triforce_text.py`` and
``alttprbot_api/blueprints/triforcetexts.py``. The submission/moderation
pool is scoped to a Tournament; moderators are the tournament's admins.
"""

import random
import re
from typing import List, Optional

from application.repositories.triforce_text_repository import TriforceTextRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import Tournament, TriforceText, User


# Same character set as sahasrahbot: A-Z, a-z, 0-9, space, common punctuation,
# arrow glyphs, hiragana, and katakana. 19 chars max per line is an ALTTP
# end-game text engine limit.
TEXT_LINE_REGEX = re.compile(
    r"^[A-Za-z0-9 \?!,\-….~～''↑↓→←ぁ-ゟァ-ヿ]{0,19}$"
)
MAX_LINES = 3


class TriforceTextService:
    """Service for triforce text operations."""

    def __init__(self):
        self.repository = TriforceTextRepository()
        self.audit_service = AuditService()

    @staticmethod
    def _validate_lines(lines: List[str]) -> List[str]:
        if not isinstance(lines, list) or len(lines) != MAX_LINES:
            raise ValueError(f"Must provide exactly {MAX_LINES} lines of text.")
        cleaned = [(line or '').rstrip('\r\n') for line in lines]
        for idx, line in enumerate(cleaned, start=1):
            if not TEXT_LINE_REGEX.match(line):
                raise ValueError(
                    f"Line {idx} contains invalid characters or exceeds 19 characters."
                )
        if not any(line.strip() for line in cleaned):
            raise ValueError("At least one line must contain text.")
        return cleaned

    async def submit(
        self,
        tournament_id: int,
        lines: List[str],
        user: User,
    ) -> TriforceText:
        if user is None:
            raise ValueError("You must be logged in to submit a triforce text.")
        tournament = await Tournament.get_or_none(id=tournament_id)
        if tournament is None:
            raise ValueError("Tournament not found.")
        if not tournament.is_active:
            raise ValueError("This tournament is not accepting submissions.")

        cleaned = self._validate_lines(lines)
        text = "\n".join(cleaned)

        created = await self.repository.create(
            tournament=tournament,
            user=user,
            text=text,
            author=user.preferred_name,
        )
        await self.audit_service.write_log(
            user,
            AuditActions.TRIFORCE_TEXT_SUBMITTED,
            {
                'triforce_text_id': created.id,
                'tournament_id': tournament.id,
            },
        )
        return created

    async def list_user_submissions(
        self, tournament_id: int, user: User
    ) -> List[TriforceText]:
        tournament = await Tournament.get_or_none(id=tournament_id)
        if tournament is None or user is None:
            return []
        return await self.repository.list_by_tournament_and_user(tournament, user)

    async def list_for_moderation(
        self,
        tournament_id: int,
        approved=TriforceTextRepository._UNSET,
    ) -> List[TriforceText]:
        tournament = await Tournament.get_or_none(id=tournament_id)
        if tournament is None:
            return []
        return await self.repository.list_by_tournament(tournament, approved=approved)

    async def moderate(
        self,
        text_id: int,
        approved: bool,
        actor: User,
    ) -> TriforceText:
        triforce_text = await self.repository.get_by_id(text_id)
        if triforce_text is None:
            raise ValueError("Triforce text not found.")

        is_staff = await AuthService.is_staff(actor)
        is_admin = await AuthService.is_tournament_admin(actor, triforce_text.tournament_id)
        if not (is_staff or is_admin):
            raise ValueError("You do not have permission to moderate this pool.")

        updated = await self.repository.set_moderation(triforce_text, approved, actor)
        await self.audit_service.write_log(
            actor,
            AuditActions.TRIFORCE_TEXT_APPROVED if approved else AuditActions.TRIFORCE_TEXT_REJECTED,
            {
                'triforce_text_id': updated.id,
                'tournament_id': updated.tournament_id,
            },
        )
        return updated

    async def delete(self, text_id: int, actor: User) -> None:
        triforce_text = await self.repository.get_by_id(text_id)
        if triforce_text is None:
            raise ValueError("Triforce text not found.")

        is_staff = await AuthService.is_staff(actor)
        is_admin = await AuthService.is_tournament_admin(actor, triforce_text.tournament_id)
        if not (is_staff or is_admin):
            raise ValueError("You do not have permission to delete this submission.")

        details = {
            'triforce_text_id': triforce_text.id,
            'tournament_id': triforce_text.tournament_id,
        }
        await self.repository.delete(triforce_text)
        await self.audit_service.write_log(
            actor, AuditActions.TRIFORCE_TEXT_DELETED, details
        )

    async def get_balanced_text(self, tournament: Tournament) -> Optional[str]:
        """Pick a random user with approved texts, then a random text from that user.

        Ensures every submitter has equal weight regardless of how many texts
        they have approved. Returns None if no approved texts exist.
        """
        if tournament is None:
            return None
        user_ids = await self.repository.list_approved_user_ids(tournament)
        if not user_ids:
            return None
        chosen_user_id = random.choice(user_ids)
        texts = await self.repository.list_approved_by_user(tournament, chosen_user_id)
        if not texts:
            return None
        return random.choice(texts).text

    async def get_random_text(self, tournament: Tournament) -> Optional[str]:
        """Pick a uniformly random approved text. Returns None when none exist."""
        if tournament is None:
            return None
        texts = await self.repository.list_approved(tournament)
        if not texts:
            return None
        return random.choice(texts).text
