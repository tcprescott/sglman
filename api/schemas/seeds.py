"""Schemas for the seed-generation endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class RandomizerResponse(BaseModel):
    """A supported randomizer and whether it can embed community triforce texts."""

    model_config = ConfigDict(from_attributes=True)

    randomizer: str
    supports_triforce_texts: bool


class SeedGenerateRequest(BaseModel):
    """Request to roll a seed for a randomizer, optionally from a stored preset.

    Two response shapes, decided by the randomizer: a synchronous backend answers
    **200** with :class:`SeedResponse`, a task-queue backend **202** with
    :class:`SeedTaskResponse`.
    """

    randomizer: str
    preset_id: Optional[int] = None


class SeedResponse(BaseModel):
    """The permalink URL of a freshly generated seed."""

    url: str


class SeedTaskResponse(BaseModel):
    """A roll that was accepted but has not finished.

    A task-queue randomizer takes minutes, so ``POST /seeds`` answers **202**
    with this instead of a permalink. Poll ``GET /seeds/tasks/{id}`` until
    ``status`` is terminal; ``url`` is filled in only once it is ``succeeded``.
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: int
    randomizer: str
    status: str
    url: Optional[str] = None
    error: Optional[str] = None
