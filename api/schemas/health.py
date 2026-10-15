"""Schema for the liveness/readiness probe."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Always `ok` when the app is up and can reach its database.")
