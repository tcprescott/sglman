"""Schemas for the engagement telemetry endpoints."""

from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class TelemetrySummaryResponse(BaseModel):
    total_events: int = Field(..., description="All telemetry rows recorded in the window.")
    unique_users: int = Field(..., description="Distinct signed-in people seen in the window.")
    unique_sessions: int = Field(..., description="Distinct browser sessions seen in the window.")
    page_views: int = Field(..., description="Page loads recorded in the window.")


class _Row(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TopPathRow(_Row):
    path: str = Field(..., description="Page path that was loaded.")
    views: int = Field(..., description="Page loads of that path.")
    users: int = Field(..., description="Distinct people who loaded it.")


class TopEventTypeRow(_Row):
    category: str = Field(
        ...,
        description=(
            "Row category: `page` (page loads), `interaction` (clicks, tab switches and other UI use) "
            "or `domain` (a copy of an event published by the app, such as a match being created)."
        ),
    )
    event_type: str = Field(..., description="Event name, such as `page.view` or `match.created`.")
    count: int = Field(..., description="Rows with this category and event name.")


class TopUserRow(_Row):
    user_id: int = Field(..., description="ID of the person.")
    user: str = Field(..., description="Display name of the person.")
    events: int = Field(..., description="Telemetry rows attributed to them.")
    sessions: int = Field(..., description="Distinct browser sessions they used.")


class TopControlRow(_Row):
    path: Optional[str] = Field(None, description="Page the control is on.")
    event_type: str = Field(
        ...,
        description=(
            "Kind of use: `tab.view`, `ui.click`, `ui.dialog_opened`, `ui.dialog_closed` or `ui.field_used`."
        ),
    )
    target: str = Field(..., description="The tab, button, menu item, dialog or field that was used.")
    uses: int = Field(..., description="How many times it was used.")
    users: int = Field(..., description="Distinct people who used it.")
    phone: int = Field(..., description="Uses that came from a phone.")


TelemetryTopRow = Union[TopPathRow, TopEventTypeRow, TopUserRow, TopControlRow]
