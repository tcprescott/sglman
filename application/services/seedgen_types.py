"""Value objects shared by seed generation and everything that persists a roll.

Their own module so the per-backend modules (``seedgen_dk64r``) can name them
without importing the service that composes them.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RolledSeed:
    """What a generator produced: the permalink, and the settings that made it.

    ``settings`` is the **resolved payload as sent upstream**, which is the whole
    reason it is carried back here rather than re-derived by the caller. A
    ``Preset`` is an editable row: without a snapshot taken at roll time, editing
    a preset silently rewrites the apparent history of every seed rolled from it,
    and the question a disputed result actually asks — "what settings did this
    seed use?" — has no answer. ``None`` where the generator has no settings to
    speak of (the test stub).
    """

    url: str
    settings: Optional[dict] = None


@dataclass
class RemotePreset:
    """One preset a randomizer's own API publishes.

    ``settings`` is already in the shape a ``Preset`` row stores — whatever the
    upstream's catalogue format is, the translation happens in the generator that
    fetched it, so nothing downstream has to know that DK64R hands out portable
    settings strings while another backend might hand out full JSON.
    """

    name: str
    settings: dict
    description: Optional[str] = None


@dataclass
class AsyncRollSubmission:
    """A roll handed to a task queue, described well enough to resume later.

    Everything here is persisted on a :class:`ProviderTask` the moment it comes
    back, because the process that polls this task may not be the one that
    submitted it.
    """

    provider_task_id: str
    provider_params: dict
    settings: dict


@dataclass
class AsyncRollPoll:
    """One check of a submitted task.

    ``seed`` is ``None`` while the task is still queued or running; a failed
    task raises instead of returning, so "not yet" never reads as "never".
    """

    seed: Optional[RolledSeed] = None
    verification_hash: Optional[list] = None
