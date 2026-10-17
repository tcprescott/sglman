"""What the viewer of a match board may actually do — one field per service gate.

The board used to carry a single ``can_crud`` boolean and render its controls off
callback presence. The services it calls have never been that coarse:
``can_run_match`` admits a proctor, ``can_confirm_match`` does not,
``can_assign_match_stream`` admits a Broadcast Tech (``STREAM_MANAGER``), and ``can_approve_crew``
admits a crew coordinator. Collapsing four audiences into one boolean is what
handed a crew coordinator 37 lifecycle controls that every service refused and
left the Broadcast Tech — the role ``assign_stage`` names in its own docstring —
with no surface that assigns a stage.

Each field below maps to exactly one gate in ``AuthService``:

============  ==========================  =========================================
field         gate                        controls
============  ==========================  =========================================
``edit``      ``can_crud_match``          the id link, the match dialog, Create Match
``run``       ``can_run_match``           Check In, Start, Finish, Generate, Stations
``confirm``   ``can_confirm_match``       Confirm, Record/Change Winner
``assign``    ``can_assign_match_stream`` Assign (stage)
``crew``      ``can_approve_crew``        the crew approval toggle and name link
============  ==========================  =========================================

These are **page-level** approximations of per-match gates: a tournament admin's
board answers "may you do this to *some* match here", and the service re-checks
the actual match on every call. That is deliberate — the board is the cheap
filter, the service is the enforcement — but it is why a scoped board matters
too: see ``admin_schedule_page``'s ``tournament_ids``.

``run_on_stage_only`` is the one per-row refinement: a Broadcast Tech may run
only a match that is on a stage, so the board offers ``run`` controls on those
rows alone (``can_run_row`` in Python, ``run_js`` in a slot template) rather
than on every row with a service refusal behind most of them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchBoardAccess:
    """One field per capability the match board offers. Default is a spectator."""

    edit: bool = False
    run: bool = False
    confirm: bool = False
    assign_stream: bool = False
    approve_crew: bool = False
    run_on_stage_only: bool = False

    def any(self) -> bool:
        return any(getattr(self, f) for f in self.__dataclass_fields__ if f != 'run_on_stage_only')

    def can_run_row(self, row: dict) -> bool:
        return self.run and (not self.run_on_stage_only or bool(row.get('stage_id')))

    def run_js(self, row: str = 'props.row') -> str:
        """``run`` as a Vue expression over ``row``, for slot templates."""
        if not self.run:
            return 'false'
        return f'(!!{row}.stage_id)' if self.run_on_stage_only else 'true'

    @classmethod
    def for_roles(
        cls,
        *,
        is_staff: bool = False,
        is_proctor: bool = False,
        is_tournament_admin: bool = False,
        is_stream_manager: bool = False,
        is_crew_coordinator: bool = False,
    ) -> 'MatchBoardAccess':
        """Resolve the capability set from the viewer's roles in this tenant.

        Mirrors the ``AuthService`` gates named in the module docstring, term for
        term. ``edit`` and ``confirm`` admit the same roles today and are still
        separate fields: they are separate gates, and a board that conflates them
        is the defect this class exists to fix.
        """
        staff_or_ta = is_staff or is_tournament_admin
        full_run = staff_or_ta or is_proctor
        return cls(
            edit=staff_or_ta,
            run=full_run or is_stream_manager,
            run_on_stage_only=is_stream_manager and not full_run,
            confirm=staff_or_ta,
            assign_stream=staff_or_ta or is_stream_manager,
            approve_crew=staff_or_ta or is_crew_coordinator,
        )
