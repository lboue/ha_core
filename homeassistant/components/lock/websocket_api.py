"""Websocket API for lock user and schedule management.

Read-only commands that let the frontend query the generic user/schedule
data exposed by lock entities (see .models) without going through the
service-call layer. Writes go through the regular `lock.*` services so they
stay usable from automations and scripts too.
"""

from typing import Any

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DATA_COMPONENT, LockEntityFeature


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lock/get_users",
        vol.Required("entity_id"): cv.entity_id,
    }
)
@websocket_api.async_response
async def handle_get_users(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the users configured on a lock."""
    await _handle_get(
        hass, connection, msg, LockEntityFeature.USERS, "async_get_users", "users"
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lock/get_week_day_schedules",
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("user_index"): cv.positive_int,
    }
)
@websocket_api.async_response
async def handle_get_week_day_schedules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the week day schedules configured for a lock user."""
    await _handle_get(
        hass,
        connection,
        msg,
        LockEntityFeature.WEEK_DAY_SCHEDULES,
        "async_get_week_day_schedules",
        "schedules",
        msg["user_index"],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lock/get_year_day_schedules",
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("user_index"): cv.positive_int,
    }
)
@websocket_api.async_response
async def handle_get_year_day_schedules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the year day schedules configured for a lock user."""
    await _handle_get(
        hass,
        connection,
        msg,
        LockEntityFeature.YEAR_DAY_SCHEDULES,
        "async_get_year_day_schedules",
        "schedules",
        msg["user_index"],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lock/get_holiday_schedules",
        vol.Required("entity_id"): cv.entity_id,
    }
)
@websocket_api.async_response
async def handle_get_holiday_schedules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the holiday schedules configured on a lock."""
    await _handle_get(
        hass,
        connection,
        msg,
        LockEntityFeature.HOLIDAY_SCHEDULES,
        "async_get_holiday_schedules",
        "schedules",
    )


async def _handle_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    feature: LockEntityFeature,
    method_name: str,
    result_key: str,
    *args: Any,
) -> None:
    """Look up the entity, check permissions/features and call it."""
    entity_id = msg["entity_id"]
    if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
        connection.send_error(msg["id"], websocket_api.ERR_UNAUTHORIZED, "Unauthorized")
        return

    if not (entity := hass.data[DATA_COMPONENT].get_entity(entity_id)):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "Entity not found"
        )
        return

    if not entity.supported_features or not entity.supported_features & feature:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_SUPPORTED,
            f"{entity_id} does not support this",
        )
        return

    try:
        result = await getattr(entity, method_name)(*args)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "failed", str(err))
        return

    connection.send_result(msg["id"], {result_key: result})


def async_setup(hass: HomeAssistant) -> None:
    """Register the lock websocket commands."""
    websocket_api.async_register_command(hass, handle_get_users)
    websocket_api.async_register_command(hass, handle_get_week_day_schedules)
    websocket_api.async_register_command(hass, handle_get_year_day_schedules)
    websocket_api.async_register_command(hass, handle_get_holiday_schedules)
