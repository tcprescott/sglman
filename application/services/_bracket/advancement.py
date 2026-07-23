"""Bracket advancement mixin: result reporting, pointer-following, walkovers.

Split out of ``bracket_service.py`` as pure code motion (see that module's
docstring). ``AdvancementMixin`` is composed into :class:`BracketService`; its
methods reach siblings (including ``_propagate_winner`` and
``_maybe_complete_stage`` defined on other mixins), ``self.repository`` and
``self.audit_service`` through that composed class.
"""

from typing import List, Optional

from application.errors import require_found
from application.events import Event, EventType, event_bus
from application.services.audit_service import AuditActions
from application.services.auth_service import AuthService
from models import (
    Bracket,
    BracketEntry,
    BracketEntryStatus,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    BracketState,
    User,
)


class AdvancementMixin:
    # -- B7: results, advancement, stage completion -----------------------

    _ELIM_FORMATS = (BracketFormat.SINGLE_ELIM, BracketFormat.DOUBLE_ELIM)

    async def report_result(
        self, actor: Optional[User], match_id: int, winner_entry_id: int
    ) -> BracketMatch:
        """Record ``winner_entry_id`` as the winner of an OPEN match, then advance.

        Staff-gated. The match must be OPEN and belong to an ACTIVE bracket, and
        the winner must be one of the match's two entries. After completing the
        match the winner and loser are pushed through the ``winner_to`` /
        ``loser_to`` pointers, downstream slots are settled (auto-advancing
        walkovers), and the stage is auto-completed when an elimination final
        resolves.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        match = require_found(await self.repository.get_match(match_id), "Match")
        bracket = await self._require_bracket(match.bracket_id)
        if bracket.state != BracketState.ACTIVE:
            raise ValueError("Can only report results for an ACTIVE bracket")
        if match.state != BracketMatchState.OPEN:
            raise ValueError("Only an OPEN match can be reported")
        if winner_entry_id not in (match.entry1_id, match.entry2_id):
            raise ValueError("Winner must be one of the match's two entries")

        winner_entry = require_found(
            await self.repository.get_entry(winner_entry_id), "Entry"
        )
        loser_id = (
            match.entry1_id if winner_entry_id == match.entry2_id else match.entry2_id
        )
        loser_entry = require_found(
            await self.repository.get_entry(loser_id), "Entry"
        )

        match.winner = winner_entry
        match.state = BracketMatchState.COMPLETE
        await match.save()

        details = {
            'bracket_id': bracket.id,
            'match_id': match.id,
            'winner_entry_id': winner_entry_id,
            'loser_entry_id': loser_id,
        }
        await self.audit_service.write_log(
            actor, AuditActions.BRACKET_MATCH_COMPLETED, details
        )
        event_bus.publish(Event.create(EventType.BRACKET_MATCH_COMPLETED, details, actor))

        await self._advance_after_result(bracket, match, winner_entry, loser_entry)
        await self._maybe_complete_stage(bracket, actor)
        return require_found(await self.repository.get_match(match_id), "Match")

    async def _advance_after_result(
        self,
        bracket: Bracket,
        match: BracketMatch,
        winner_entry: BracketEntry,
        loser_entry: BracketEntry,
    ) -> None:
        """Push a completed match's winner/loser through its progression pointers."""
        is_elim = bracket.format in self._ELIM_FORMATS

        reset = await self._gf1_reset(match)
        if reset is not None:
            # Grand Final 1 (double elim): winner_to and loser_to both target the
            # terminal reset match. If the winners-bracket side (slot 1) wins, the
            # title is decided — the reset is never played and the loser is the
            # runner-up. If the losers-bracket side (slot 2) wins, populate and
            # open the reset for the deciding game.
            winner_from_wb = winner_entry.id == match.entry1_id
            if winner_from_wb:
                await self._clear_match_slots(reset)
                await self._set_entry_status(
                    loser_entry, BracketEntryStatus.ELIMINATED
                )
            else:
                await self._set_entry_status(winner_entry, BracketEntryStatus.ACTIVE)
                await self._set_entry_status(loser_entry, BracketEntryStatus.ACTIVE)
                self._place(reset, match.winner_to_slot, winner_entry)
                self._place(reset, match.loser_to_slot, loser_entry)
                reset.state = BracketMatchState.OPEN
                await reset.save()
            return

        if is_elim:
            await self._set_entry_status(winner_entry, BracketEntryStatus.ACTIVE)

        winner_target = await self._propagate_winner(match, winner_entry)

        loser_target: Optional[BracketMatch] = None
        if match.loser_to_id is not None:
            loser_target = await self.repository.get_match(match.loser_to_id)
            if loser_target is not None:
                self._place(loser_target, match.loser_to_slot, loser_entry)
                await loser_target.save()
                if is_elim:
                    await self._set_entry_status(
                        loser_entry, BracketEntryStatus.ACTIVE
                    )
        elif is_elim:
            await self._set_entry_status(loser_entry, BracketEntryStatus.ELIMINATED)

        settled: set = set()
        for target in (winner_target, loser_target):
            if target is None or target.id in settled:
                continue
            settled.add(target.id)
            fresh = await self.repository.get_match(target.id)
            if fresh is not None:
                await self._settle_match(fresh)

    async def _gf1_reset(self, match: BracketMatch) -> Optional[BracketMatch]:
        """Return the reset match iff ``match`` is a double-elim Grand Final 1.

        Structural, since there is no ``is_reset`` column: GF1 is the match whose
        ``winner_to`` and ``loser_to`` point at the *same* target, and that shared
        target is terminal (no onward pointers) — i.e. the reset. The degenerate
        P=2 winners final also points both pointers at the grand final, but that
        target still has onward pointers (into the reset), so it is not mistaken
        for GF1.
        """
        if match.winner_to_id is None or match.winner_to_id != match.loser_to_id:
            return None
        target = await self.repository.get_match(match.winner_to_id)
        if target is None:
            return None
        if target.winner_to_id is None and target.loser_to_id is None:
            return target
        return None

    @staticmethod
    def _place(match: BracketMatch, slot: Optional[int], entry: BracketEntry) -> None:
        if slot == 1:
            match.entry1 = entry
        else:
            match.entry2 = entry

    async def _clear_match_slots(self, match: BracketMatch) -> None:
        """Empty a match's entry slots and reset it to PENDING (idempotent)."""
        match.entry1 = None
        match.entry2 = None
        match.winner = None
        match.state = BracketMatchState.PENDING
        await match.save()

    @staticmethod
    async def _set_entry_status(
        entry: BracketEntry, status: BracketEntryStatus
    ) -> None:
        if entry.status != status:
            entry.status = status
            await entry.save()

    async def _settle_match(self, match: BracketMatch, _depth: int = 0) -> None:
        """Set a match's state after one of its slots changed.

        Both slots filled and not already COMPLETE → OPEN. Exactly one slot
        filled whose empty counterpart has no still-pending feeder → walkover:
        complete it with the present entry and recurse into the target. Otherwise
        → PENDING.
        """
        if _depth > 1000 or match.state == BracketMatchState.COMPLETE:
            return

        has1 = match.entry1_id is not None
        has2 = match.entry2_id is not None

        if has1 and has2:
            match.state = BracketMatchState.OPEN
            await match.save()
            return

        if has1 != has2:
            empty_slot = 2 if has1 else 1
            if await self._slot_can_fill(match.id, empty_slot):
                match.state = BracketMatchState.PENDING
                await match.save()
                return
            present_id = match.entry1_id if has1 else match.entry2_id
            present = await self.repository.get_entry(present_id)
            if present is None:
                match.state = BracketMatchState.PENDING
                await match.save()
                return
            target = await self._propagate_winner(match, present)
            if target is not None:
                fresh = await self.repository.get_match(target.id)
                if fresh is not None:
                    await self._settle_match(fresh, _depth + 1)
            return

        match.state = BracketMatchState.PENDING
        await match.save()

    async def _slot_can_fill(
        self, match_id: int, slot: int, _seen: Optional[set] = None
    ) -> bool:
        """Whether an entry can still arrive in ``slot`` of ``match_id``.

        A slot is fed by not-yet-COMPLETE upstream matches (via their ``winner_to``
        or ``loser_to`` pointers). A winner-feeder can deliver an entry only if it
        will ever have at least one entrant; a loser-feeder only if it will ever be
        a real two-entrant contest. This recurses so that a dead phantom (an
        elimination match both of whose own feeders were byes) is correctly seen
        as unable to fill the slot — turning the downstream lone entrant into a
        walkover instead of an eternally-pending match.
        """
        if _seen is None:
            _seen = set()
        key = (match_id, slot)
        if key in _seen:
            return False
        _seen.add(key)

        for feeder in await self.repository.winner_feeders(match_id, slot):
            if await self._can_produce_winner(feeder, _seen):
                return True
        for feeder in await self.repository.loser_feeders(match_id, slot):
            if await self._can_produce_loser(feeder, _seen):
                return True
        return False

    async def _can_produce_winner(
        self, match: BracketMatch, _seen: set
    ) -> bool:
        if match.state == BracketMatchState.COMPLETE:
            return match.winner_id is not None
        if match.entry1_id is not None or match.entry2_id is not None:
            return True
        return await self._slot_can_fill(
            match.id, 1, _seen
        ) or await self._slot_can_fill(match.id, 2, _seen)

    async def _can_produce_loser(
        self, match: BracketMatch, _seen: set
    ) -> bool:
        if match.state == BracketMatchState.COMPLETE:
            # A completed match yields a loser only if it was a real contest.
            return match.entry1_id is not None and match.entry2_id is not None
        slot1_live = match.entry1_id is not None or await self._slot_can_fill(
            match.id, 1, _seen
        )
        slot2_live = match.entry2_id is not None or await self._slot_can_fill(
            match.id, 2, _seen
        )
        return slot1_live and slot2_live

    async def override_result(
        self, actor: Optional[User], match_id: int, winner_entry_id: int
    ) -> BracketMatch:
        """Staff correction of an already-COMPLETE match's winner.

        Allowed only while no match downstream of this one is already COMPLETE
        (raise otherwise — staff must undo the downstream results first). The new
        winner/loser are re-pushed into the still-uncompleted downstream slots.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        match = require_found(await self.repository.get_match(match_id), "Match")
        bracket = await self._require_bracket(match.bracket_id)
        if match.state != BracketMatchState.COMPLETE:
            raise ValueError("Can only override a COMPLETE match")
        if winner_entry_id not in (match.entry1_id, match.entry2_id):
            raise ValueError("Winner must be one of the match's two entries")

        downstream_ids = {
            tid for tid in (match.winner_to_id, match.loser_to_id) if tid is not None
        }
        for tid in downstream_ids:
            target = await self.repository.get_match(tid)
            if target is not None and target.state == BracketMatchState.COMPLETE:
                raise ValueError(
                    "A downstream match is already complete; undo it before "
                    "overriding this result"
                )

        winner_entry = require_found(
            await self.repository.get_entry(winner_entry_id), "Entry"
        )
        loser_id = (
            match.entry1_id if winner_entry_id == match.entry2_id else match.entry2_id
        )
        loser_entry = require_found(
            await self.repository.get_entry(loser_id), "Entry"
        )

        match.winner = winner_entry
        await match.save()

        await self._advance_after_result(bracket, match, winner_entry, loser_entry)
        await self._maybe_complete_stage(bracket, actor)

        details = {
            'bracket_id': bracket.id,
            'match_id': match.id,
            'winner_entry_id': winner_entry_id,
            'loser_entry_id': loser_id,
            'override': True,
        }
        await self.audit_service.write_log(
            actor, AuditActions.BRACKET_MATCH_COMPLETED, details
        )
        event_bus.publish(Event.create(EventType.BRACKET_MATCH_COMPLETED, details, actor))
        return require_found(await self.repository.get_match(match_id), "Match")

    async def get_open_matches(self, bracket_id: int) -> List[BracketMatch]:
        """All OPEN (playable) matches of a bracket."""
        return await self.repository.list_open_matches(bracket_id)
