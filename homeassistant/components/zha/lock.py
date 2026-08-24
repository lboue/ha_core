"""Locks on Zigbee Home Automation networks."""

import functools
from typing import Any, override

import voluptuous as vol

from homeassistant.components.lock import LockEntity, LockEntityFeature, LockUser
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    async_get_current_platform,
)

from .entity import ZHAEntity
from .helpers import (
    SIGNAL_ADD_ENTITIES,
    async_add_entities as zha_async_add_entities,
    convert_zha_error_to_ha_error,
    get_zha_data,
)

SERVICE_SET_LOCK_USER_CODE = "set_lock_user_code"
SERVICE_ENABLE_LOCK_USER_CODE = "enable_lock_user_code"
SERVICE_DISABLE_LOCK_USER_CODE = "disable_lock_user_code"
SERVICE_CLEAR_LOCK_USER_CODE = "clear_lock_user_code"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Zigbee Home Automation Door Lock from config entry."""
    zha_data = get_zha_data(hass)
    entities_to_create = zha_data.platforms[Platform.LOCK]

    unsub = async_dispatcher_connect(
        hass,
        SIGNAL_ADD_ENTITIES,
        functools.partial(
            zha_async_add_entities, async_add_entities, ZhaDoorLock, entities_to_create
        ),
    )
    config_entry.async_on_unload(unsub)

    platform = async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_LOCK_USER_CODE,
        {
            vol.Required("code_slot"): vol.Coerce(int),
            vol.Required("user_code"): cv.string,
        },
        "async_set_lock_user_code",
    )

    platform.async_register_entity_service(
        SERVICE_ENABLE_LOCK_USER_CODE,
        {
            vol.Required("code_slot"): vol.Coerce(int),
        },
        "async_enable_lock_user_code",
    )

    platform.async_register_entity_service(
        SERVICE_DISABLE_LOCK_USER_CODE,
        {
            vol.Required("code_slot"): vol.Coerce(int),
        },
        "async_disable_lock_user_code",
    )

    platform.async_register_entity_service(
        SERVICE_CLEAR_LOCK_USER_CODE,
        {
            vol.Required("code_slot"): vol.Coerce(int),
        },
        "async_clear_lock_user_code",
    )


class ZhaDoorLock(ZHAEntity, LockEntity):
    """Representation of a ZHA lock."""

    _attr_translation_key: str = "door_lock"
    # The zha library only supports writing/clearing a PIN at a code slot,
    # not listing configured slots back, so USERS covers set/clear only.
    _attr_supported_features = LockEntityFeature.USERS

    @property
    @override
    def is_locked(self) -> bool:
        """Return true if entity is locked."""
        return self.entity_data.entity.is_locked

    @convert_zha_error_to_ha_error()
    @override
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self.entity_data.entity.async_lock()
        self.async_write_ha_state()

    @convert_zha_error_to_ha_error()
    @override
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self.entity_data.entity.async_unlock()
        self.async_write_ha_state()

    @convert_zha_error_to_ha_error()
    async def async_set_lock_user_code(self, code_slot: int, user_code: str) -> None:
        """Set the user_code to index X on the lock."""
        await self.entity_data.entity.async_set_lock_user_code(
            code_slot=code_slot, user_code=user_code
        )
        self.async_write_ha_state()

    @convert_zha_error_to_ha_error()
    async def async_enable_lock_user_code(self, code_slot: int) -> None:
        """Enable user_code at index X on the lock."""
        await self.entity_data.entity.async_enable_lock_user_code(code_slot=code_slot)
        self.async_write_ha_state()

    @convert_zha_error_to_ha_error()
    async def async_disable_lock_user_code(self, code_slot: int) -> None:
        """Disable user_code at index X on the lock."""
        await self.entity_data.entity.async_disable_lock_user_code(code_slot=code_slot)
        self.async_write_ha_state()

    @convert_zha_error_to_ha_error()
    async def async_clear_lock_user_code(self, code_slot: int) -> None:
        """Clear the user_code at index X on the lock."""
        await self.entity_data.entity.async_clear_lock_user_code(code_slot=code_slot)
        self.async_write_ha_state()

    @override
    async def async_get_users(self) -> list[LockUser]:
        """Return the users configured on this lock.

        Not supported: the zha library can write PIN codes to a slot but has
        no ZCL GetPINCode/GetUserStatus wrapper to read them back.
        """
        raise HomeAssistantError(
            translation_domain="zha",
            translation_key="get_users_not_supported",
        )

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
        """Set the PIN code and/or enabled state of a code slot."""
        if name is not None or user_type is not None:
            raise ServiceValidationError(
                translation_domain="zha",
                translation_key="user_name_type_not_supported",
            )
        if code is not None:
            await self.async_set_lock_user_code(code_slot=user_index, user_code=code)
        if enabled is True:
            await self.async_enable_lock_user_code(code_slot=user_index)
        elif enabled is False:
            await self.async_disable_lock_user_code(code_slot=user_index)
        return None

    @override
    async def async_clear_user(self, user_index: int) -> None:
        """Clear the PIN code at a code slot."""
        await self.async_clear_lock_user_code(code_slot=user_index)

    @callback
    @override
    def restore_external_state_attributes(self, state: State) -> None:
        """Restore entity state."""
        self.entity_data.entity.restore_external_state_attributes(
            state=state.state,
        )
