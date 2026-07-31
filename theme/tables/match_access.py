"""What the viewer of a match board may actually do — one field per service gate.

The board used to carry a single ``can_crud`` boolean and render its controls off
callback presence. The services it calls have never been that coarse:
``can_run_match`` admits a proctor, ``can_confirm_match`` does not,
``can_assign_match_stream`` admits a stream manager, and ``can_approve_crew``
admits a crew coordinator. Collapsing four audiences into one boolean is what
handed a crew coordinator 37 lifecycle controls that every service refused and
left the stream manager — the role ``assign_stage`` names in its own docstring —
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

    def any(self) -> bool:
        return any(getattr(self, f) for f in self.__dataclass_fields__)

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
        return cls(
            edit=staff_or_ta,
            run=staff_or_ta or is_proctor,
            confirm=staff_or_ta,
            assign_stream=staff_or_ta or is_stream_manager,
            approve_crew=staff_or_ta or is_crew_coordinator,
        )
