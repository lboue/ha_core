"""Matter lock."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, override

from chip.clusters import Objects as clusters
from matter_server.common.errors import MatterError
from matter_server.common.models import EventType, MatterNodeEvent

from homeassistant.components.lock import (
    LockEntity,
    LockEntityDescription,
    LockEntityFeature,
    LockHolidaySchedule,
    LockUser,
    LockWeekDaySchedule,
    LockYearDaySchedule,
)
from homeassistant.const import ATTR_CODE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_CREDENTIAL_DATA,
    ATTR_CREDENTIAL_INDEX,
    ATTR_CREDENTIAL_RULE,
    ATTR_CREDENTIAL_TYPE,
    ATTR_DAYS,
    ATTR_END_DATE_TIME,
    ATTR_END_TIME,
    ATTR_HOLIDAY_INDEX,
    ATTR_OPERATING_MODE,
    ATTR_START_DATE_TIME,
    ATTR_START_TIME,
    ATTR_USER_INDEX,
    ATTR_USER_NAME,
    ATTR_USER_STATUS,
    ATTR_USER_TYPE,
    ATTR_WEEK_DAY_INDEX,
    ATTR_YEAR_DAY_INDEX,
    LOCK_TIMED_REQUEST_TIMEOUT_MS,
    LOGGER,
)
from .entity import MatterEntity, MatterEntityDescription
from .helpers import MatterConfigEntry
from .lock_helpers import (
    DoorLockFeature,
    GetLockCredentialStatusResult,
    GetLockInfoResult,
    GetLockUsersResult,
    HolidayScheduleData,
    SetLockCredentialResult,
    WeekDayScheduleData,
    YearDayScheduleData,
    clear_holiday_schedule,
    clear_lock_credential,
    clear_lock_user,
    clear_week_day_schedule,
    clear_year_day_schedule,
    get_holiday_schedule,
    get_lock_credential_status,
    get_lock_info,
    get_lock_users,
    get_week_day_schedule,
    get_year_day_schedule,
    set_holiday_schedule,
    set_lock_credential,
    set_lock_user,
    set_week_day_schedule,
    set_year_day_schedule,
)
from .models import MatterDiscoverySchema

# Door lock operation source mapping (Matter DoorLock OperationSourceEnum)
_OperationSource = clusters.DoorLock.Enums.OperationSourceEnum
DOOR_LOCK_OPERATION_SOURCE: dict[int, str] = {
    _OperationSource.kUnspecified: "Unspecified",
    _OperationSource.kManual: "Manual",
    _OperationSource.kProprietaryRemote: "Proprietary Remote",
    _OperationSource.kKeypad: "Keypad",
    _OperationSource.kAuto: "Auto",
    _OperationSource.kButton: "Button",
    _OperationSource.kSchedule: "Schedule",
    _OperationSource.kRemote: "Remote",
    _OperationSource.kRfid: "RFID",
    _OperationSource.kBiometric: "Biometric",
    _OperationSource.kAliro: "Aliro",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MatterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Matter lock from Config Entry."""
    matter = config_entry.runtime_data.adapter
    matter.register_platform_handler(Platform.LOCK, async_add_entities)


@dataclass(frozen=True, kw_only=True)
class MatterLockEntityDescription(LockEntityDescription, MatterEntityDescription):
    """Describe Matter Lock entities."""


class MatterLock(MatterEntity, LockEntity):
    """Representation of a Matter lock."""

    _feature_map: int | None = None
    _optimistic_timer: asyncio.TimerHandle | None = None
    _platform_translation_key = "lock"
    _attr_changed_by = "Unknown"

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to events."""
        await super().async_added_to_hass()
        # subscribe to NodeEvent events
        self._unsubscribes.append(
            self.matter_client.subscribe_events(
                callback=self._on_matter_node_event,
                event_filter=EventType.NODE_EVENT,
                node_filter=self._endpoint.node.node_id,
            )
        )

    @callback
    def _on_matter_node_event(
        self,
        event: EventType,
        node_event: MatterNodeEvent,
    ) -> None:
        """Call on NodeEvent."""
        if (node_event.endpoint_id != self._endpoint.endpoint_id) or (
            node_event.cluster_id != clusters.DoorLock.id
        ):
            return

        LOGGER.debug(
            "Received node_event: event type %s, event id %s for %s with data %s",
            event,
            node_event.event_id,
            self.entity_id,
            node_event.data,
        )

        # Handle the DoorLock events
        node_event_data: dict[str, int] = node_event.data or {}
        match node_event.event_id:
            case clusters.DoorLock.Events.LockOperation.event_id:
                operation_source: int = node_event_data.get("operationSource", -1)
                source_name = DOOR_LOCK_OPERATION_SOURCE.get(
                    operation_source, "Unknown"
                )
                self._attr_changed_by = source_name
                self.async_write_ha_state()

    @property
    @override
    def code_format(self) -> str | None:
        """Regex for code format or None if no code is required."""
        if self.get_matter_attribute_value(
            clusters.DoorLock.Attributes.RequirePINforRemoteOperation
        ):
            min_pincode_length = int(
                self.get_matter_attribute_value(
                    clusters.DoorLock.Attributes.MinPINCodeLength
                )
            )
            max_pincode_length = int(
                self.get_matter_attribute_value(
                    clusters.DoorLock.Attributes.MaxPINCodeLength
                )
            )
            return f"^\\d{{{min_pincode_length},{max_pincode_length}}}$"

        return None

    @override
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock with pin if needed."""
        if not self._attr_is_locked:
            # optimistically signal locking to state machine
            self._attr_is_locking = True
            self.async_write_ha_state()
            # the lock should acknowledge the command with an attribute update
            # but bad things may happen, so guard against it with a timer.
            self._optimistic_timer = self.hass.loop.call_later(
                30, self._reset_optimistic_state
            )
        code: str | None = kwargs.get(ATTR_CODE)
        code_bytes = code.encode() if code else None
        await self.send_device_command(
            command=clusters.DoorLock.Commands.LockDoor(code_bytes),
            timed_request_timeout_ms=LOCK_TIMED_REQUEST_TIMEOUT_MS,
        )

    @override
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock with pin if needed."""
        if self._attr_is_locked:
            # optimistically signal unlocking to state machine
            self._attr_is_unlocking = True
            self.async_write_ha_state()
            # the lock should acknowledge the command with an attribute update
            # but bad things may happen, so guard against it with a timer.
            self._optimistic_timer = self.hass.loop.call_later(
                30, self._reset_optimistic_state
            )
        code: str | None = kwargs.get(ATTR_CODE)
        code_bytes = code.encode() if code else None
        if self._attr_supported_features & LockEntityFeature.OPEN:
            # if the lock reports it has separate unbolt support,
            # the unlock command should unbolt only on the unlock command
            # and unlatch on the HA 'open' command.
            await self.send_device_command(
                command=clusters.DoorLock.Commands.UnboltDoor(code_bytes),
                timed_request_timeout_ms=LOCK_TIMED_REQUEST_TIMEOUT_MS,
            )
        else:
            await self.send_device_command(
                command=clusters.DoorLock.Commands.UnlockDoor(code_bytes),
                timed_request_timeout_ms=LOCK_TIMED_REQUEST_TIMEOUT_MS,
            )

    @override
    async def async_open(self, **kwargs: Any) -> None:
        """Open the door latch."""
        # optimistically signal opening to state machine
        self._attr_is_opening = True
        self.async_write_ha_state()
        # the lock should acknowledge the command with an attribute update
        # but bad things may happen, so guard against it with a timer.
        self._optimistic_timer = self.hass.loop.call_later(
            30 if self._attr_is_locked else 5, self._reset_optimistic_state
        )
        code: str | None = kwargs.get(ATTR_CODE)
        code_bytes = code.encode() if code else None
        await self.send_device_command(
            command=clusters.DoorLock.Commands.UnlockDoor(code_bytes),
            timed_request_timeout_ms=LOCK_TIMED_REQUEST_TIMEOUT_MS,
        )

    @callback
    @override
    def _update_from_device(self) -> None:
        """Update the entity from the device."""
        # always calculate the features as they can dynamically change
        self._calculate_features()

        lock_state = self.get_matter_attribute_value(
            clusters.DoorLock.Attributes.LockState
        )

        # always reset the optimisically (un)locking state on state update
        self._reset_optimistic_state(write_state=False)

        LOGGER.debug("Lock state: %s for %s", lock_state, self.entity_id)

        if lock_state == clusters.DoorLock.Enums.DlLockState.kUnlatched:
            self._attr_is_locked = False
            self._attr_is_open = True
        elif lock_state == clusters.DoorLock.Enums.DlLockState.kLocked:
            self._attr_is_locked = True
            self._attr_is_open = False
        elif lock_state in (
            clusters.DoorLock.Enums.DlLockState.kUnlocked,
            clusters.DoorLock.Enums.DlLockState.kNotFullyLocked,
        ):
            self._attr_is_locked = False
            self._attr_is_open = False
        else:
            # Treat any other state as unknown.
            # NOTE: A null state can happen during device startup.
            self._attr_is_locked = None
            self._attr_is_open = None

    @callback
    def _reset_optimistic_state(self, write_state: bool = True) -> None:
        if self._optimistic_timer and not self._optimistic_timer.cancelled():
            self._optimistic_timer.cancel()
        self._optimistic_timer = None
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._attr_is_opening = False
        if write_state:
            self.async_write_ha_state()

    @callback
    def _calculate_features(
        self,
    ) -> None:
        """Calculate features for HA Lock platform from Matter FeatureMap."""
        feature_map = int(
            self.get_matter_attribute_value(clusters.DoorLock.Attributes.FeatureMap)
        )
        # NOTE: the featuremap can dynamically change, so we need to update the
        # supported features if the featuremap changes.
        if self._feature_map == feature_map:
            return
        self._feature_map = feature_map
        supported_features = LockEntityFeature(0)
        # determine if lock supports optional open/unbolt feature
        if bool(feature_map & DoorLockFeature.kUnbolt):
            supported_features |= LockEntityFeature.OPEN
        if bool(feature_map & DoorLockFeature.kUser):
            supported_features |= LockEntityFeature.USERS
        if bool(feature_map & DoorLockFeature.kWeekDayAccessSchedules):
            supported_features |= LockEntityFeature.WEEK_DAY_SCHEDULES
        if bool(feature_map & DoorLockFeature.kYearDayAccessSchedules):
            supported_features |= LockEntityFeature.YEAR_DAY_SCHEDULES
        if bool(feature_map & DoorLockFeature.kHolidaySchedules):
            supported_features |= LockEntityFeature.HOLIDAY_SCHEDULES
        self._attr_supported_features = supported_features

    # --- Generic lock.* platform methods (homeassistant.components.lock) ---
    # Implements the cross-integration user/schedule contract so a shared
    # frontend can manage this lock the same way as e.g. a future ZHA lock,
    # in addition to the richer matter.* services below for credential-level
    # control that the generic model doesn't cover.

    @override
    async def async_get_users(self) -> list[LockUser]:
        """Return the users configured on this lock."""
        try:
            result = await get_lock_users(self.matter_client, self._endpoint.node)
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get lock users for {self.entity_id}: {err}"
            ) from err
        return [
            LockUser(
                user_index=user["user_index"],
                name=user["user_name"],
                code=None,  # Matter never returns credential values
                user_type=user["user_type"],
                enabled=user["user_status"] == "occupied_enabled",
            )
            for user in result["users"]
            if user["user_index"] is not None
        ]

    @override
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
        user_status = (
            "occupied_enabled"
            if enabled
            else "occupied_disabled"
            if enabled is False
            else None
        )
        try:
            result = await set_lock_user(
                self.matter_client,
                self._endpoint.node,
                user_index=user_index,
                user_name=name,
                user_type=user_type,
                user_status=user_status,
            )
            if code is not None:
                await set_lock_credential(
                    self.matter_client,
                    self._endpoint.node,
                    credential_type="pin",
                    credential_data=code,
                    user_index=result["user_index"],
                )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set lock user on {self.entity_id}: {err}"
            ) from err
        return LockUser(
            user_index=result["user_index"],
            name=name,
            code=code,
            user_type=user_type,
            enabled=enabled,
        )

    @override
    async def async_clear_user(self, user_index: int) -> None:
        """Remove a user (code slot) from this lock."""
        try:
            await clear_lock_user(self.matter_client, self._endpoint.node, user_index)
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear lock user on {self.entity_id}: {err}"
            ) from err

    async def _async_max_schedules(self, attr: str) -> int:
        """Look up a schedule capacity attribute via get_lock_info."""
        try:
            info: GetLockInfoResult = await get_lock_info(
                self.matter_client, self._endpoint.node
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get lock info for {self.entity_id}: {err}"
            ) from err
        return info[attr] or 0  # type: ignore[literal-required]

    @override
    async def async_get_week_day_schedules(
        self, user_index: int
    ) -> list[LockWeekDaySchedule]:
        """Return the week day schedules configured for a lock user."""
        max_schedules = await self._async_max_schedules(
            "max_week_day_schedules_per_user"
        )
        schedules: list[LockWeekDaySchedule] = []
        try:
            for index in range(1, max_schedules + 1):
                schedule = await get_week_day_schedule(
                    self.matter_client,
                    self._endpoint.node,
                    week_day_index=index,
                    user_index=user_index,
                )
                if schedule["exists"]:
                    schedules.append(
                        LockWeekDaySchedule(
                            schedule_index=index,
                            user_index=user_index,
                            days=schedule["days"],
                            start_time=schedule["start_time"] or "",
                            end_time=schedule["end_time"] or "",
                        )
                    )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get week day schedules for {self.entity_id}: {err}"
            ) from err
        return schedules

    @override
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
        try:
            await set_week_day_schedule(
                self.matter_client,
                self._endpoint.node,
                week_day_index=schedule_index,
                user_index=user_index,
                days=days,
                start_time=time.fromisoformat(start_time),
                end_time=time.fromisoformat(end_time),
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set week day schedule on {self.entity_id}: {err}"
            ) from err

    @override
    async def async_clear_week_day_schedule(
        self, schedule_index: int, user_index: int
    ) -> None:
        """Remove a week day schedule from a lock user."""
        try:
            await clear_week_day_schedule(
                self.matter_client,
                self._endpoint.node,
                week_day_index=schedule_index,
                user_index=user_index,
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear week day schedule on {self.entity_id}: {err}"
            ) from err

    @override
    async def async_get_year_day_schedules(
        self, user_index: int
    ) -> list[LockYearDaySchedule]:
        """Return the year day schedules configured for a lock user."""
        max_schedules = await self._async_max_schedules(
            "max_year_day_schedules_per_user"
        )
        schedules: list[LockYearDaySchedule] = []
        try:
            for index in range(1, max_schedules + 1):
                schedule = await get_year_day_schedule(
                    self.matter_client,
                    self._endpoint.node,
                    year_day_index=index,
                    user_index=user_index,
                )
                if schedule["exists"]:
                    schedules.append(
                        LockYearDaySchedule(
                            schedule_index=index,
                            user_index=user_index,
                            start_date_time=schedule["start_date_time"] or "",
                            end_date_time=schedule["end_date_time"] or "",
                        )
                    )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get year day schedules for {self.entity_id}: {err}"
            ) from err
        return schedules

    @override
    async def async_set_year_day_schedule(
        self,
        schedule_index: int,
        user_index: int,
        *,
        start_date_time: str,
        end_date_time: str,
    ) -> None:
        """Create or update a year day schedule for a lock user."""
        try:
            await set_year_day_schedule(
                self.matter_client,
                self._endpoint.node,
                year_day_index=schedule_index,
                user_index=user_index,
                start_date_time=datetime.fromisoformat(start_date_time),
                end_date_time=datetime.fromisoformat(end_date_time),
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set year day schedule on {self.entity_id}: {err}"
            ) from err

    @override
    async def async_clear_year_day_schedule(
        self, schedule_index: int, user_index: int
    ) -> None:
        """Remove a year day schedule from a lock user."""
        try:
            await clear_year_day_schedule(
                self.matter_client,
                self._endpoint.node,
                year_day_index=schedule_index,
                user_index=user_index,
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear year day schedule on {self.entity_id}: {err}"
            ) from err

    @override
    async def async_get_holiday_schedules(self) -> list[LockHolidaySchedule]:
        """Return the holiday schedules configured on this lock."""
        max_schedules = await self._async_max_schedules("max_holiday_schedules")
        schedules: list[LockHolidaySchedule] = []
        try:
            for index in range(1, max_schedules + 1):
                schedule = await get_holiday_schedule(
                    self.matter_client,
                    self._endpoint.node,
                    holiday_index=index,
                )
                if schedule["exists"]:
                    schedules.append(
                        LockHolidaySchedule(
                            schedule_index=index,
                            start_date_time=schedule["start_date_time"] or "",
                            end_date_time=schedule["end_date_time"] or "",
                            operating_mode=schedule["operating_mode"] or "",
                        )
                    )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get holiday schedules for {self.entity_id}: {err}"
            ) from err
        return schedules

    @override
    async def async_set_holiday_schedule(
        self,
        schedule_index: int,
        *,
        start_date_time: str,
        end_date_time: str,
        operating_mode: str,
    ) -> None:
        """Create or update a holiday schedule on this lock."""
        try:
            await set_holiday_schedule(
                self.matter_client,
                self._endpoint.node,
                holiday_index=schedule_index,
                start_date_time=datetime.fromisoformat(start_date_time),
                end_date_time=datetime.fromisoformat(end_date_time),
                operating_mode=operating_mode,
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set holiday schedule on {self.entity_id}: {err}"
            ) from err

    @override
    async def async_clear_holiday_schedule(self, schedule_index: int) -> None:
        """Remove a holiday schedule from this lock."""
        try:
            await clear_holiday_schedule(
                self.matter_client,
                self._endpoint.node,
                holiday_index=schedule_index,
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear holiday schedule on {self.entity_id}: {err}"
            ) from err

    # --- Entity service methods ---

    async def async_set_lock_user(self, **kwargs: Any) -> None:
        """Set a lock user (full CRUD)."""
        try:
            await set_lock_user(
                self.matter_client,
                self._endpoint.node,
                user_index=kwargs.get(ATTR_USER_INDEX),
                user_name=kwargs.get(ATTR_USER_NAME),
                user_type=kwargs.get(ATTR_USER_TYPE),
                credential_rule=kwargs.get(ATTR_CREDENTIAL_RULE),
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set lock user on {self.entity_id}: {err}"
            ) from err

    async def async_clear_lock_user(self, **kwargs: Any) -> None:
        """Clear a lock user."""
        try:
            await clear_lock_user(
                self.matter_client,
                self._endpoint.node,
                kwargs[ATTR_USER_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear lock user on {self.entity_id}: {err}"
            ) from err

    async def async_get_lock_info(self) -> GetLockInfoResult:
        """Get lock capabilities and configuration info."""
        try:
            return await get_lock_info(
                self.matter_client,
                self._endpoint.node,
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get lock info for {self.entity_id}: {err}"
            ) from err

    async def async_get_lock_users(self) -> GetLockUsersResult:
        """Get all users from the lock."""
        try:
            return await get_lock_users(
                self.matter_client,
                self._endpoint.node,
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get lock users for {self.entity_id}: {err}"
            ) from err

    async def async_set_lock_credential(self, **kwargs: Any) -> SetLockCredentialResult:
        """Set a credential on the lock."""
        try:
            return await set_lock_credential(
                self.matter_client,
                self._endpoint.node,
                credential_type=kwargs[ATTR_CREDENTIAL_TYPE],
                credential_data=kwargs[ATTR_CREDENTIAL_DATA],
                credential_index=kwargs.get(ATTR_CREDENTIAL_INDEX),
                user_index=kwargs.get(ATTR_USER_INDEX),
                user_status=kwargs.get(ATTR_USER_STATUS),
                user_type=kwargs.get(ATTR_USER_TYPE),
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set lock credential on {self.entity_id}: {err}"
            ) from err

    async def async_clear_lock_credential(self, **kwargs: Any) -> None:
        """Clear a credential from the lock."""
        try:
            await clear_lock_credential(
                self.matter_client,
                self._endpoint.node,
                credential_type=kwargs[ATTR_CREDENTIAL_TYPE],
                credential_index=kwargs[ATTR_CREDENTIAL_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear lock credential on {self.entity_id}: {err}"
            ) from err

    async def async_get_lock_credential_status(
        self, **kwargs: Any
    ) -> GetLockCredentialStatusResult:
        """Get the status of a credential slot on the lock."""
        try:
            return await get_lock_credential_status(
                self.matter_client,
                self._endpoint.node,
                credential_type=kwargs[ATTR_CREDENTIAL_TYPE],
                credential_index=kwargs[ATTR_CREDENTIAL_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get credential status for {self.entity_id}: {err}"
            ) from err

    async def async_set_week_day_schedule_matter(self, **kwargs: Any) -> None:
        """Set a week day schedule for a lock user."""
        try:
            await set_week_day_schedule(
                self.matter_client,
                self._endpoint.node,
                week_day_index=kwargs[ATTR_WEEK_DAY_INDEX],
                user_index=kwargs[ATTR_USER_INDEX],
                days=kwargs[ATTR_DAYS],
                start_time=kwargs[ATTR_START_TIME],
                end_time=kwargs[ATTR_END_TIME],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set week day schedule on {self.entity_id}: {err}"
            ) from err

    async def async_get_week_day_schedule(self, **kwargs: Any) -> WeekDayScheduleData:
        """Get a week day schedule for a lock user."""
        try:
            return await get_week_day_schedule(
                self.matter_client,
                self._endpoint.node,
                week_day_index=kwargs[ATTR_WEEK_DAY_INDEX],
                user_index=kwargs[ATTR_USER_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get week day schedule for {self.entity_id}: {err}"
            ) from err

    async def async_clear_week_day_schedule_matter(self, **kwargs: Any) -> None:
        """Clear a week day schedule for a lock user."""
        try:
            await clear_week_day_schedule(
                self.matter_client,
                self._endpoint.node,
                week_day_index=kwargs[ATTR_WEEK_DAY_INDEX],
                user_index=kwargs[ATTR_USER_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear week day schedule on {self.entity_id}: {err}"
            ) from err

    async def async_set_year_day_schedule_matter(self, **kwargs: Any) -> None:
        """Set a year day schedule for a lock user."""
        try:
            await set_year_day_schedule(
                self.matter_client,
                self._endpoint.node,
                year_day_index=kwargs[ATTR_YEAR_DAY_INDEX],
                user_index=kwargs[ATTR_USER_INDEX],
                start_date_time=kwargs[ATTR_START_DATE_TIME],
                end_date_time=kwargs[ATTR_END_DATE_TIME],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set year day schedule on {self.entity_id}: {err}"
            ) from err

    async def async_get_year_day_schedule(self, **kwargs: Any) -> YearDayScheduleData:
        """Get a year day schedule for a lock user."""
        try:
            return await get_year_day_schedule(
                self.matter_client,
                self._endpoint.node,
                year_day_index=kwargs[ATTR_YEAR_DAY_INDEX],
                user_index=kwargs[ATTR_USER_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get year day schedule for {self.entity_id}: {err}"
            ) from err

    async def async_clear_year_day_schedule_matter(self, **kwargs: Any) -> None:
        """Clear a year day schedule for a lock user."""
        try:
            await clear_year_day_schedule(
                self.matter_client,
                self._endpoint.node,
                year_day_index=kwargs[ATTR_YEAR_DAY_INDEX],
                user_index=kwargs[ATTR_USER_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear year day schedule on {self.entity_id}: {err}"
            ) from err

    async def async_set_holiday_schedule_matter(self, **kwargs: Any) -> None:
        """Set a lock-wide holiday schedule."""
        try:
            await set_holiday_schedule(
                self.matter_client,
                self._endpoint.node,
                holiday_index=kwargs[ATTR_HOLIDAY_INDEX],
                start_date_time=kwargs[ATTR_START_DATE_TIME],
                end_date_time=kwargs[ATTR_END_DATE_TIME],
                operating_mode=kwargs[ATTR_OPERATING_MODE],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to set holiday schedule on {self.entity_id}: {err}"
            ) from err

    async def async_get_holiday_schedule(self, **kwargs: Any) -> HolidayScheduleData:
        """Get a lock-wide holiday schedule."""
        try:
            return await get_holiday_schedule(
                self.matter_client,
                self._endpoint.node,
                holiday_index=kwargs[ATTR_HOLIDAY_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to get holiday schedule for {self.entity_id}: {err}"
            ) from err

    async def async_clear_holiday_schedule_matter(self, **kwargs: Any) -> None:
        """Clear a lock-wide holiday schedule."""
        try:
            await clear_holiday_schedule(
                self.matter_client,
                self._endpoint.node,
                holiday_index=kwargs[ATTR_HOLIDAY_INDEX],
            )
        except MatterError as err:
            raise HomeAssistantError(
                f"Failed to clear holiday schedule on {self.entity_id}: {err}"
            ) from err


DISCOVERY_SCHEMAS = [
    MatterDiscoverySchema(
        platform=Platform.LOCK,
        entity_description=MatterLockEntityDescription(
            key="MatterLock",
            name=None,
        ),
        entity_class=MatterLock,
        required_attributes=(clusters.DoorLock.Attributes.LockState,),
    ),
]
