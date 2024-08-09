"""Test Matter valve."""

from math import floor
from unittest.mock import MagicMock, call

from chip.clusters import Objects as clusters
import pytest

from homeassistant.components.valve import (
    STATE_CLOSED,
    STATE_OPEN,
    STATE_OPENING,
    ValveEntityFeature,
)
from homeassistant.core import HomeAssistant

from .common import (
    set_node_attribute,
    setup_integration_with_node_fixture,
    trigger_subscription_callback,
)


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
@pytest.mark.parametrize(
    ("fixture", "entity_id"),
    [
        ("valve_full", "cover.mock_valve"),
    ],
)
async def test_valve(
    hass: HomeAssistant,
    matter_client: MagicMock,
    fixture: str,
    entity_id: str,
) -> None:
    """Test valve commands that always are implemented."""

    valve = await setup_integration_with_node_fixture(
        hass,
        fixture,
        matter_client,
    )

    await hass.services.async_call(
        "valve",
        "close_valve",
        {
            "entity_id": entity_id,
        },
        blocking=True,
    )

    assert matter_client.send_device_command.call_count == 1
    assert matter_client.send_device_command.call_args == call(
        node_id=valve.node_id,
        endpoint_id=1,
        command=clusters.ValveConfigurationAndControl.Commands.Close(),
    )
    matter_client.send_device_command.reset_mock()


    await hass.services.async_call(
        "cover",
        "open_valve",
        {
            "entity_id": entity_id,
        },
        blocking=True,
    )

    assert matter_client.send_device_command.call_count == 1
    assert matter_client.send_device_command.call_args == call(
        node_id=valve.node_id,
        endpoint_id=1,
        command=clusters.ValveConfigurationAndControl.Commands.UOpen(),
    )
    matter_client.send_device_command.reset_mock()
