"""Constants for the lock entity platform."""

from enum import IntFlag, StrEnum
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.util.hass_dict import HassKey

if TYPE_CHECKING:
    from homeassistant.helpers.entity_component import EntityComponent

    from . import LockEntity

DOMAIN = "lock"

DATA_COMPONENT: HassKey[EntityComponent[LockEntity]] = HassKey(DOMAIN)


class LockEntityStateAttribute(StrEnum):
    """State attributes for lock entities."""

    CHANGED_BY = "changed_by"
    CODE_FORMAT = "code_format"


class LockState(StrEnum):
    """State of lock entities."""

    JAMMED = "jammed"
    OPENING = "opening"
    LOCKING = "locking"
    OPEN = "open"
    UNLOCKING = "unlocking"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class LockEntityFeature(IntFlag):
    """Supported features of the lock entity."""

    OPEN = 1
    USERS = 2
    WEEK_DAY_SCHEDULES = 4
    YEAR_DAY_SCHEDULES = 8
    HOLIDAY_SCHEDULES = 16


ATTR_USER_INDEX = "user_index"
ATTR_USER_NAME = "name"
ATTR_USER_CODE = "code"
ATTR_USER_TYPE = "user_type"
ATTR_USER_ENABLED = "enabled"
ATTR_SCHEDULE_INDEX = "schedule_index"
ATTR_DAYS = "days"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_START_DATE_TIME = "start_date_time"
ATTR_END_DATE_TIME = "end_date_time"
ATTR_OPERATING_MODE = "operating_mode"

SET_USER_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_USER_INDEX): cv.positive_int,
        vol.Optional(ATTR_USER_NAME): cv.string,
        vol.Optional(ATTR_USER_CODE): cv.string,
        vol.Optional(ATTR_USER_TYPE): cv.string,
        vol.Optional(ATTR_USER_ENABLED): cv.boolean,
    }
)
CLEAR_USER_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {vol.Required(ATTR_USER_INDEX): cv.positive_int}
)
SET_WEEK_DAY_SCHEDULE_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE_INDEX): cv.positive_int,
        vol.Required(ATTR_USER_INDEX): cv.positive_int,
        vol.Required(ATTR_DAYS): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_START_TIME): cv.time,
        vol.Required(ATTR_END_TIME): cv.time,
    }
)
CLEAR_SCHEDULE_FOR_USER_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE_INDEX): cv.positive_int,
        vol.Required(ATTR_USER_INDEX): cv.positive_int,
    }
)
GET_SCHEDULES_FOR_USER_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {vol.Required(ATTR_USER_INDEX): cv.positive_int}
)
SET_YEAR_DAY_SCHEDULE_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE_INDEX): cv.positive_int,
        vol.Required(ATTR_USER_INDEX): cv.positive_int,
        vol.Required(ATTR_START_DATE_TIME): cv.datetime,
        vol.Required(ATTR_END_DATE_TIME): cv.datetime,
    }
)
SET_HOLIDAY_SCHEDULE_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE_INDEX): cv.positive_int,
        vol.Required(ATTR_START_DATE_TIME): cv.datetime,
        vol.Required(ATTR_END_DATE_TIME): cv.datetime,
        vol.Required(ATTR_OPERATING_MODE): cv.string,
    }
)
CLEAR_HOLIDAY_SCHEDULE_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {vol.Required(ATTR_SCHEDULE_INDEX): cv.positive_int}
)
