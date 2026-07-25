"""Which bracket stages a viewer may see.

A DRAFT stage is **unpublished**: it exists so staff can author and seed a field
before announcing it. The bracket views are world-readable, so a draft would
otherwise put pre-announcement seeding in front of anyone with the URL — it is
shown to staff only, on every surface that lists or renders stages.

Pure and ORM-free, so the two public pages and the home browse tab share one
rule rather than three copies of a filter, and it is unit-testable. Staff keep
the full list in Admin → Brackets, which never goes through here.
"""

from typing import Iterable, List

from models import Bracket, BracketState


def is_visible(bracket: Bracket, *, is_staff: bool) -> bool:
    return is_staff or bracket.state != BracketState.DRAFT


def visible_stages(brackets: Iterable[Bracket], *, is_staff: bool) -> List[Bracket]:
    return [b for b in brackets if is_visible(b, is_staff=is_staff)]
