"""Generic data models for lock user and schedule management.

These TypedDicts define an integration-agnostic shape for lock users and
their access schedules, so integrations that expose this kind of management
(currently Matter; potentially Zigbee/ZHA and Z-Wave JS) can be queried and
controlled the same way by automations, scripts and the frontend, instead of
each integration inventing its own service and payload shapes.

Integrations that model this data differently (e.g. Matter's separate
credential objects) are free to keep their own richer services in addition
to implementing this generic surface.
"""

from typing import TypedDict


class LockUser(TypedDict):
    """A user (code slot) on a lock."""

    user_index: int
    name: str | None
    code: str | None
    user_type: str | None
    enabled: bool | None


class LockWeekDaySchedule(TypedDict):
    """A recurring weekly access schedule for a lock user."""

    schedule_index: int
    user_index: int
    days: list[str]
    start_time: str
    end_time: str


class LockYearDaySchedule(TypedDict):
    """A one-off date range access schedule for a lock user."""

    schedule_index: int
    user_index: int
    start_date_time: str
    end_date_time: str


class LockHolidaySchedule(TypedDict):
    """A date range schedule that overrides normal lock operation."""

    schedule_index: int
    start_date_time: str
    end_date_time: str
    operating_mode: str
