"""Schemas for the seed-generation endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RandomizerResponse(BaseModel):
    """A supported randomizer and whether it can embed community triforce texts."""

    model_config = ConfigDict(from_attributes=True)

    randomizer: str = Field(..., description="Randomizer slug, such as `alttpr` or `ff1r`. Pass it to `POST /seeds`.")
    supports_triforce_texts: bool = Field(
        ..., description="Whether seeds from this randomizer can carry the community's triforce texts."
    )


class SeedGenerateRequest(BaseModel):
    """Request to roll a seed for a randomizer, optionally from a stored preset.

    Two response shapes, decided by the randomizer: a synchronous backend answers
    **200** with :class:`SeedResponse`, a task-queue backend **202** with
    :class:`SeedTaskResponse`.
    """

    randomizer: str = Field(..., description="Randomizer slug from `GET /seeds/randomizers`.")
    preset_id: Optional[int] = Field(
        None,
        description="One of this community's presets to roll with. Some randomizers refuse to roll without one.",
    )


class SeedResponse(BaseModel):
    """The permalink URL of a freshly generated seed."""

    url: str = Field(
        ...,
        description="Link to the seed. Wind Waker and Zelda 1 seeds are a code to paste into the randomizer instead of a link.",
    )


class SeedTaskResponse(BaseModel):
    """A roll that was accepted but has not finished.

    A task-queue randomizer takes minutes, so ``POST /seeds`` answers **202**
    with this instead of a permalink. Poll ``GET /seeds/tasks/{id}`` until
    ``status`` is terminal; ``url`` is filled in only once it is ``succeeded``.
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: int = Field(..., description="Id to poll with `GET /seeds/tasks/{task_id}`.")
    randomizer: str = Field(..., description="Randomizer slug the roll is for.")
    status: str = Field(
        ...,
        description="Where the roll is: `queued`, `running`, `succeeded`, `failed` or `abandoned` (gave up waiting). The last three are final.",
    )
    url: Optional[str] = Field(
        None,
        description="Seed link once the roll succeeds. A roll made through this API with no match stays null even after it succeeds.",
    )
    error: Optional[str] = Field(None, description="Why the roll failed, when it did.")
