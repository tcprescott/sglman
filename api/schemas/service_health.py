"""Schemas for the service-health endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProbeResultResponse(BaseModel):
    """One dependency's latest probe outcome.

    Mirrors :meth:`ProbeResult.as_dict` — ``status`` is the plain enum value
    string and ``checked_at`` is a UTC ISO-8601 timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    category: str
    status: str
    message: str
    checked_at: datetime
