"""Schemas for the reporting endpoints.

The report services build their payloads for the chart that is about to draw
them, so the shapes are wide and per-report. Rather than freeze each one into a
model that would have to move with every chart tweak, the responses are typed
as ``Dict[str, Any]`` / ``List[Dict[str, Any]]`` and the two that are genuinely
too heavy to hand back whole are reshaped in the router — the same call the MCP
tools make, for the same reason.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CapacityPeak(BaseModel):
    at: datetime
    players: int


class CapacityForecastResponse(BaseModel):
    start: datetime
    end: datetime
    interval_minutes: int
    max_capacity: Optional[int] = None
    peak_players: int
    peak_on_stream_players: int
    over_capacity_intervals: int
    busiest: List[CapacityPeak] = Field(default_factory=list)


class StageUtilizationRow(BaseModel):
    stage_id: Optional[int] = None
    stage_name: Optional[str] = None
    scheduled_hours: float
    match_count: int
    gap_hours: float
    back_to_back_count: int


class StageUtilizationResponse(BaseModel):
    stages: List[StageUtilizationRow] = Field(default_factory=list)
    unplaced_candidate_count: int = 0


class ActiveMatchRow(BaseModel):
    match_id: int
    tournament: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    players: List[str] = Field(default_factory=list)
    stage: Optional[str] = None


ReportPayload = Dict[str, Any]
ReportRows = List[Dict[str, Any]]
