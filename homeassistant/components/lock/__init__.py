"""Component to interface with locks that can be controlled remotely."""

from datetime import timedelta
import functools as ft
import logging
import re
from typing import TYPE_CHECKING, Any, final, override

from propcache.api import cached_property
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (  # noqa: F401
    ATTR_CODE,
    ATTR_CODE_FORMAT,
    SERVICE_LOCK,
    SERVICE_OPEN,
    SERVICE_UNLOCK,
)
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType, StateType

from . import websocket_api
from .const import (
    CLEAR_HOLIDAY_SCHEDULE_SERVICE_SCHEMA,
    CLEAR_SCHEDULE_FOR_USER_SERVICE_SCHEMA,
    CLEAR_USER_SERVICE_SCHEMA,
    DATA_COMPONENT,
    DOMAIN,
    GET_SCHEDULES_FOR_USER_SERVICE_SCHEMA,
    SET_HOLIDAY_SCHEDULE_SERVICE_SCHEMA,
    SET_USER_SERVICE_SCHEMA,
    SET_WEEK_DAY_SCHEDULE_SERVICE_SCHEMA,
    SET_YEAR_DAY_SCHEDULE_SERVICE_SCHEMA,
    LockEntityFeature,
    LockEntityStateAttribute,
    LockState,
)
from .models import (
    LockHolidaySchedule,
    LockUser,
    LockWeekDaySchedule,
    LockYearDaySchedule,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"
PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA
PLATFORM_SCHEMA_BASE = cv.PLATFORM_SCHEMA_BASE
SCAN_INTERVAL = timedelta(seconds=30)

ATTR_CHANGED_BY = "changed_by"
CONF_DEFAULT_CODE = "default_code"

MIN_TIME_BETWEEN_SCANS = timedelta(seconds=10)

LOCK_SERVICE_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional(ATTR_CODE): cv.string}
)

PROP_TO_ATTR = {
    "changed_by": LockEntityStateAttribute.CHANGED_BY,
    "code_format": LockEntityStateAttribute.CODE_FORMAT,
}

# mypy: disallow-any-generics


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Track states and offer events for locks."""
    component = hass.data[DATA_COMPONENT] = EntityComponent[LockEntity](
        _LOGGER, DOMAIN, hass, SCAN_INTERVAL
    )

    await component.async_setup(config)

    component.async_register_entity_service(
        SERVICE_UNLOCK, LOCK_SERVICE_SCHEMA, "async_handle_unlock_service"
    )
    component.async_register_entity_service(
        SERVICE_LOCK, LOCK_SERVICE_SCHEMA, "async_handle_lock_service"
    )
    component.async_register_entity_service(
        SERVICE_OPEN,
        LOCK_SERVICE_SCHEMA,
        "async_handle_open_service",
        [LockEntityFeature.OPEN],
    )

    component.async_register_entity_service(
        "get_users",
        None,
        "async_get_users",
        [LockEntityFeature.USERS],
        supports_response=SupportsResponse.ONLY,
    )
    component.async_register_entity_service(
        "set_user",
        SET_USER_SERVICE_SCHEMA,
        "async_set_user",
        [LockEntityFeature.USERS],
        supports_response=SupportsResponse.OPTIONAL,
    )
    component.async_register_entity_service(
        "clear_user",
        CLEAR_USER_SERVICE_SCHEMA,
        "async_clear_user",
        [LockEntityFeature.USERS],
    )

    component.async_register_entity_service(
        "get_week_day_schedules",
        GET_SCHEDULES_FOR_USER_SERVICE_SCHEMA,
        "async_get_week_day_schedules",
        [LockEntityFeature.WEEK_DAY_SCHEDULES],
        supports_response=SupportsResponse.ONLY,
    )
    component.async_register_entity_service(
        "set_week_day_schedule",
        SET_WEEK_DAY_SCHEDULE_SERVICE_SCHEMA,
        "async_set_week_day_schedule",
        [LockEntityFeature.WEEK_DAY_SCHEDULES],
    )
    component.async_register_entity_service(
        "clear_week_day_schedule",
        CLEAR_SCHEDULE_FOR_USER_SERVICE_SCHEMA,
        "async_clear_week_day_schedule",
        [LockEntityFeature.WEEK_DAY_SCHEDULES],
    )

    component.async_register_entity_service(
        "get_year_day_schedules",
        GET_SCHEDULES_FOR_USER_SERVICE_SCHEMA,
        "async_get_year_day_schedules",
        [LockEntityFeature.YEAR_DAY_SCHEDULES],
        supports_response=SupportsResponse.ONLY,
    )
    component.async_register_entity_service(
        "set_year_day_schedule",
        SET_YEAR_DAY_SCHEDULE_SERVICE_SCHEMA,
        "async_set_year_day_schedule",
        [LockEntityFeature.YEAR_DAY_SCHEDULES],
    )
    component.async_register_entity_service(
        "clear_year_day_schedule",
        CLEAR_SCHEDULE_FOR_USER_SERVICE_SCHEMA,
        "async_clear_year_day_schedule",
        [LockEntityFeature.YEAR_DAY_SCHEDULES],
    )

    component.async_register_entity_service(
        "get_holiday_schedules",
        None,
        "async_get_holiday_schedules",
        [LockEntityFeature.HOLIDAY_SCHEDULES],
        supports_response=SupportsResponse.ONLY,
    )
    component.async_register_entity_service(
        "set_holiday_schedule",
        SET_HOLIDAY_SCHEDULE_SERVICE_SCHEMA,
        "async_set_holiday_schedule",
        [LockEntityFeature.HOLIDAY_SCHEDULES],
    )
    component.async_register_entity_service(
        "clear_holiday_schedule",
        CLEAR_HOLIDAY_SCHEDULE_SERVICE_SCHEMA,
        "async_clear_holiday_schedule",
        [LockEntityFeature.HOLIDAY_SCHEDULES],
    )

    websocket_api.async_setup(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    return await hass.data[DATA_COMPONENT].async_setup_entry(entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.data[DATA_COMPONENT].async_unload_entry(entry)


class LockEntityDescription(EntityDescription, frozen_or_thawed=True):
    """A class that describes lock entities."""


CACHED_PROPERTIES_WITH_ATTR_ = {
    "changed_by",
    "code_format",
    "is_locked",
    "is_locking",
    "is_unlocking",
    "is_open",
    "is_opening",
    "is_jammed",
    "supported_features",
}


class LockEntity(Entity, cached_properties=CACHED_PROPERTIES_WITH_ATTR_):
    """Base class for lock entities."""

    entity_description: LockEntityDescription
    _attr_changed_by: str | None = None
    _attr_code_format: str | None = None
    _attr_is_locked: bool | None = None
    _attr_is_locking: bool | None = None
    _attr_is_open: bool | None = None
    _attr_is_opening: bool | None = None
    _attr_is_unlocking: bool | None = None
    _attr_is_jammed: bool | None = None
    _attr_state: None = None
    _attr_supported_features: LockEntityFeature = LockEntityFeature(0)
    _lock_option_default_code: str = ""
    __code_format_cmp: re.Pattern[str] | None = None

    @final
    @callback
    def add_default_code(self, data: dict[Any, Any]) -> dict[Any, Any]:
        """Add default lock code."""
        code: str = data.pop(ATTR_CODE, "")
        if not code:
            code = self._lock_option_default_code
        if self.code_format_cmp and not self.code_format_cmp.match(code):
            if TYPE_CHECKING:
                assert self.code_format
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="add_default_code",
                translation_placeholders={
                    "entity_id": self.entity_id,
                    "code_format": self.code_format,
                },
            )
        if code:
            data[ATTR_CODE] = code
        return data

    @cached_property
    def changed_by(self) -> str | None:
        """Last change triggered by."""
        return self._attr_changed_by

    @cached_property
    def code_format(self) -> str | None:
        """Regex for code format or None if no code is required."""
        return self._attr_code_format

    @property
    @final
    def code_format_cmp(self) -> re.Pattern[str] | None:
        """Return a compiled code_format."""
        if self.code_format is None:
            self.__code_format_cmp = None
            return None
        if (
            not self.__code_format_cmp
            or self.code_format != self.__code_format_cmp.pattern
        ):
            self.__code_format_cmp = re.compile(self.code_format)
        return self.__code_format_cmp

    @cached_property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        return self._attr_is_locked

    @cached_property
    def is_locking(self) -> bool | None:
        """Return true if the lock is locking."""
        return self._attr_is_locking

    @cached_property
    def is_unlocking(self) -> bool | None:
        """Return true if the lock is unlocking."""
        return self._attr_is_unlocking

    @cached_property
    def is_open(self) -> bool | None:
        """Return true if the lock is open."""
        return self._attr_is_open

    @cached_property
    def is_opening(self) -> bool | None:
        """Return true if the lock is opening."""
        return self._attr_is_opening

    @cached_property
    def is_jammed(self) -> bool | None:
        """Return true if the lock is jammed (incomplete locking)."""
        return self._attr_is_jammed

    @final
    async def async_handle_lock_service(self, **kwargs: Any) -> None:
        """Add default code and lock."""
        await self.async_lock(**self.add_default_code(kwargs))

    def lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        raise NotImplementedError

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self.hass.async_add_executor_job(ft.partial(self.lock, **kwargs))

    @final
    async def async_handle_unlock_service(self, **kwargs: Any) -> None:
        """Add default code and unlock."""
        await self.async_unlock(**self.add_default_code(kwargs))

    def unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        raise NotImplementedError

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self.hass.async_add_executor_job(ft.partial(self.unlock, **kwargs))

    @final
    async def async_handle_open_service(self, **kwargs: Any) -> None:
        """Add default code and open."""
        await self.async_open(**self.add_default_code(kwargs))

    def open(self, **kwargs: Any) -> None:
        """Open the door latch."""
        raise NotImplementedError

    async def async_open(self, **kwargs: Any) -> None:
        """Open the door latch."""
        await self.hass.async_add_executor_job(ft.partial(self.open, **kwargs))

    async def async_get_users(self) -> list[LockUser]:
        """Return the users configured on this lock.

        Only called for entities that report LockEntityFeature.USERS.
        """
        raise NotImplementedError

    async def async_set_user(
        self,
        user_index: int,
        *,
        name: str | None = None,
        code: str | None = None,
        user_type: str | None = None,
        enabled: bool | None = None,
    ) -> LockUser | None:
        """Create or update a user (code slot) on this lock."""
        raise NotImplementedError

    async def async_clear_user(self, user_index: int) -> None:
        """Remove a user (code slot) from this lock."""
        raise NotImplementedError

    async def async_get_week_day_schedules(
        self, user_index: int
    ) -> list[LockWeekDaySchedule]:
        """Return the week day schedules configured for a lock user."""
        raise NotImplementedError

    async def async_set_week_day_schedule(
        self,
        schedule_index: int,
        user_index: int,
        *,
        days: list[str],
        start_time: str,
        end_time: str,
    ) -> None:
        """Create or update a week day schedule for a lock user."""
        raise NotImplementedError

    async def async_clear_week_day_schedule(
        self, schedule_index: int, user_index: int
    ) -> None:
        """Remove a week day schedule from a lock user."""
        raise NotImplementedError

    async def async_get_year_day_schedules(
        self, user_index: int
    ) -> list[LockYearDaySchedule]:
        """Return the year day schedules configured for a lock user."""
        raise NotImplementedError

    async def async_set_year_day_schedule(
        self,
        schedule_index: int,
        user_index: int,
        *,
        start_date_time: str,
        end_date_time: str,
    ) -> None:
        """Create or update a year day schedule for a lock user."""
        raise NotImplementedError

    async def async_clear_year_day_schedule(
        self, schedule_index: int, user_index: int
    ) -> None:
        """Remove a year day schedule from a lock user."""
        raise NotImplementedError

    async def async_get_holiday_schedules(self) -> list[LockHolidaySchedule]:
        """Return the holiday schedules configured on this lock."""
        raise NotImplementedError

    async def async_set_holiday_schedule(
        self,
        schedule_index: int,
        *,
        start_date_time: str,
        end_date_time: str,
        operating_mode: str,
    ) -> None:
        """Create or update a holiday schedule on this lock."""
        raise NotImplementedError

    async def async_clear_holiday_schedule(self, schedule_index: int) -> None:
        """Remove a holiday schedule from this lock."""
        raise NotImplementedError

    @final
    @property
    @override
    def state_attributes(self) -> dict[str, StateType]:
        """Return the state attributes."""
        state_attr: dict[str, StateType] = {}
        for prop, attr in PROP_TO_ATTR.items():
            if (value := getattr(self, prop)) is not None:
                state_attr[attr] = value
        return state_attr

    @final
    @property
    @override
    def state(self) -> str | None:
        """Return the state."""
        if self.is_jammed:
            return LockState.JAMMED
        if self.is_opening:
            return LockState.OPENING
        if self.is_locking:
            return LockState.LOCKING
        if self.is_open:
            return LockState.OPEN
        if self.is_unlocking:
            return LockState.UNLOCKING
        if (locked := self.is_locked) is None:
            return None
        return LockState.LOCKED if locked else LockState.UNLOCKED

    @cached_property
    @override
    def supported_features(self) -> LockEntityFeature:
        """Return the list of supported features."""
        return self._attr_supported_features

    @override
    async def async_internal_added_to_hass(self) -> None:
        """Call when the sensor entity is added to hass."""
        await super().async_internal_added_to_hass()
        if not self.registry_entry:
            return
        self._async_read_entity_options()

    @callback
    @override
    def async_registry_entry_updated(self) -> None:
        """Run when the entity registry entry has been updated."""
        self._async_read_entity_options()

    @callback
    def _async_read_entity_options(self) -> None:
        """Read entity options from entity registry.

        Called when the entity registry entry has been updated and before the lock is
        added to the state machine.
        """
        assert self.registry_entry
        if (lock_options := self.registry_entry.options.get(DOMAIN)) and (
            custom_default_lock_code := lock_options.get(CONF_DEFAULT_CODE)
        ):
            if self.code_format_cmp and self.code_format_cmp.match(
                custom_default_lock_code
            ):
                self._lock_option_default_code = custom_default_lock_code
            return

        self._lock_option_default_code = ""
