"""Bracket multi-stage chaining mixin: advance a completed stage into the next.

Split out of ``bracket_service.py`` as pure code motion (see that module's
docstring). ``MultiStageMixin`` is composed into :class:`BracketService`; its
methods reach siblings (including ``_require_tournament`` defined on the
composer), ``self.repository`` and ``self.audit_service`` through that composed
class.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from application.errors import require_found
from application.events import Event, EventType, event_bus
from application.services.audit_service import AuditActions
from application.services.auth_service import AuthService
from application.services.bracket_config import AdvancementConfig
from models import (
    Bracket,
    BracketEntry,
    BracketEntryStatus,
    BracketFormat,
    BracketState,
    User,
)


class MultiStageMixin:
    # -- B8: multi-stage chaining -----------------------------------------

    async def advance_stage(
        self, actor: Optional[User], tournament_id: int, from_stage_order: int
    ) -> Bracket:
        """Seed the stage after ``from_stage_order`` from that stage's final ranks.

        Staff-triggered — nothing chains silently. The source stage must be
        COMPLETE (its ``final_rank`` written); the next stage must exist, be
        DRAFT, and carry an ``advancement`` rule. The rule's ``count`` entrants
        (per source ``group_number`` when ``per_group``, else overall) are drawn
        by best ``final_rank``, skipping DROPPED entries, and enrolled into the
        next stage as fresh :class:`BracketEntry` rows pointing at the SAME
        :class:`BracketEntrant` — identity carries across stages. Seeds are laid
        out by the rule's seeding policy. The next stage is left DRAFT and seeded
        for staff to review and then :meth:`start_bracket`.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        await self._require_tournament(tournament_id)

        source, next_stage, advancement = await self._advancement_context(
            tournament_id, from_stage_order
        )

        existing = await self.repository.list_entries(next_stage.id)
        if existing:
            raise ValueError("The next stage has already been seeded")

        advancers = await self._compute_advancers(source, advancement)
        next_is_grouped = next_stage.format == BracketFormat.ROUND_ROBIN

        for entry, seed, source_group in self._seed_advancers(advancers, advancement):
            await self.repository.create_entry(
                bracket_id=next_stage.id,
                entrant_id=entry.entrant_id,
                seed=seed,
                group_number=source_group if next_is_grouped else None,
                status=BracketEntryStatus.ACTIVE,
            )

        details = {
            'tournament_id': tournament_id,
            'from_stage_order': from_stage_order,
            'from_bracket_id': source.id,
            'to_bracket_id': next_stage.id,
            'advanced': len(advancers),
        }
        await self.audit_service.write_log(
            actor, AuditActions.BRACKET_STAGE_ADVANCED, details
        )
        event_bus.publish(
            Event.create(EventType.BRACKET_STAGE_ADVANCED, details, actor)
        )
        return next_stage

    async def get_advancing_preview(
        self, tournament_id: int, from_stage_order: int
    ) -> List[BracketEntry]:
        """Source-stage entries that would advance, in advancement order.

        Read helper for the UI/tests — same selection :meth:`advance_stage`
        performs, without writing anything. Raises the same guards.
        """
        source, _next_stage, advancement = await self._advancement_context(
            tournament_id, from_stage_order
        )
        return await self._compute_advancers(source, advancement)

    async def _advancement_context(
        self, tournament_id: int, from_stage_order: int
    ) -> Tuple[Bracket, Bracket, AdvancementConfig]:
        """Resolve and validate (source, next stage, advancement rule)."""
        source = await self.repository.get_stage(tournament_id, from_stage_order)
        source = require_found(source, "Stage")
        if source.state != BracketState.COMPLETE:
            raise ValueError("The predecessor stage must complete first")

        next_stage = await self.repository.get_stage(
            tournament_id, from_stage_order + 1
        )
        if next_stage is None:
            raise ValueError("There is no next stage to advance into")
        if next_stage.state != BracketState.DRAFT:
            raise ValueError("The next stage must be DRAFT to seed it")

        raw = (next_stage.config or {}).get('advancement')
        if not raw:
            raise ValueError("The next stage has no advancement rule configured")
        advancement = AdvancementConfig.model_validate(raw)
        return source, next_stage, advancement

    async def _compute_advancers(
        self, source: Bracket, advancement: AdvancementConfig
    ) -> List[BracketEntry]:
        """Ranked, DROPPED-filtered advancers from ``source`` in seeding order.

        ``per_group`` returns the top ``count`` of each source group ordered
        tier-major (every group's winner, then every group's runner-up, …) so the
        seeding policy can spread them; otherwise the ``count`` best overall.
        """
        entries = [
            e
            for e in await self.repository.list_entries(source.id)
            if e.status != BracketEntryStatus.DROPPED and e.final_rank is not None
        ]

        if not advancement.per_group:
            ordered = sorted(entries, key=lambda e: e.final_rank)
            if len(ordered) < advancement.count:
                raise ValueError(
                    "Not enough ranked entrants to advance the requested count"
                )
            return ordered[: advancement.count]

        by_group: Dict[Optional[int], List[BracketEntry]] = defaultdict(list)
        for e in entries:
            by_group[e.group_number].append(e)

        groups = sorted(by_group, key=lambda g: (g is None, g))
        tiers: List[List[BracketEntry]] = []
        for group in groups:
            ranked = sorted(by_group[group], key=lambda e: e.final_rank)
            if len(ranked) < advancement.count:
                raise ValueError(
                    "Not enough ranked entrants in a group to advance the "
                    "requested count"
                )
            for tier, entry in enumerate(ranked[: advancement.count]):
                if tier >= len(tiers):
                    tiers.append([])
                tiers[tier].append(entry)

        return [entry for tier in tiers for entry in tier]

    def _seed_advancers(
        self, advancers: List[BracketEntry], advancement: AdvancementConfig
    ) -> List[Tuple[BracketEntry, int, Optional[int]]]:
        """Assign 1..K seeds to ``advancers`` per the seeding policy.

        ``advancers`` arrive tier-major (see :meth:`_compute_advancers`): for a
        per-group rule, the first ``G`` are the group winners, the next ``G`` the
        runners-up, and so on. ``preserve`` keeps that order as seeds 1..K.
        ``snake`` reverses alternate tiers *symmetrically* (direction ``t`` ==
        direction of its mirror tier), which — against the engine's standard
        seeding, where the round-1 opponent of seed ``s`` is seed ``K+1-s`` —
        keeps two entrants from the same source group out of the same opening
        match while still spreading the group winners across the bracket.
        """
        if not advancement.per_group or advancement.seeding == 'preserve':
            order = advancers
        else:
            group_count = self._infer_group_count(advancers, advancement)
            order = self._snake_order(advancers, group_count, advancement.count)

        seeded: List[Tuple[BracketEntry, int, Optional[int]]] = []
        for index, entry in enumerate(order, start=1):
            seeded.append((entry, index, entry.group_number))
        return seeded

    @staticmethod
    def _infer_group_count(
        advancers: List[BracketEntry], advancement: AdvancementConfig
    ) -> int:
        tiers = max(1, advancement.count)
        return max(1, len(advancers) // tiers)

    @staticmethod
    def _snake_order(
        advancers: List[BracketEntry], group_count: int, tiers: int
    ) -> List[BracketEntry]:
        order: List[BracketEntry] = []
        for tier in range(tiers):
            block = advancers[tier * group_count : (tier + 1) * group_count]
            # Symmetric direction: a tier and its mirror (tiers-1-tier) share
            # orientation, so a same-group pair never lands in one round-1 match.
            if min(tier, tiers - 1 - tier) % 2 == 1:
                block = list(reversed(block))
            order.extend(block)
        return order
