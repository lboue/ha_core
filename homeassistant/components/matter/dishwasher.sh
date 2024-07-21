"""Matter dishwasher platform."""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any

from chip.clusters import Objects as clusters
from matter_server.client.models import device_types
from matter_server.common.helpers.util import create_attribute_path_from_attribute

from homeassistant.components.dishwasher import (
    DishwasherEntity,
    DishwasherEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import MatterEntity
from .helpers import get_matter
from .models import MatterDiscoverySchema

if TYPE_CHECKING:
    from matter_server.client import MatterClient
    from matter_server.client.models.node import MatterEndpoint

    from .discovery import MatterEntityInfo

'''
TEMPERATURE_SCALING_FACTOR = 100
HVAC_SYSTEM_MODE_MAP = {
    HVACMode.OFF: 0,
    HVACMode.HEAT_COOL: 1,
    HVACMode.COOL: 3,
    HVACMode.HEAT: 4,
    HVACMode.DRY: 8,
    HVACMode.FAN_ONLY: 7,
}

SINGLE_SETPOINT_DEVICES: set[tuple[int, int]] = {
    # Some devices only have a single setpoint while the matter spec
    # assumes that you need separate setpoints for heating and cooling.
    # We were told this is just some legacy inheritance from zigbee specs.
    # In the list below specify tuples of (vendorid, productid) of devices for
    # which we just need a single setpoint to control both heating and cooling.
    (0x1209, 0x8007),
}

SUPPORT_DRY_MODE_DEVICES: set[tuple[int, int]] = {
    # The Matter spec is missing a feature flag if the device supports a dry mode.
    # In the list below specify tuples of (vendorid, productid) of devices that
    # support dry mode.
    (0x0001, 0x0108),
    (0x0001, 0x010A),
    (0x1209, 0x8007),
}

SUPPORT_FAN_MODE_DEVICES: set[tuple[int, int]] = {
    # The Matter spec is missing a feature flag if the device supports a fan-only mode.
    # In the list below specify tuples of (vendorid, productid) of devices that
    # support fan-only mode.
    (0x0001, 0x0108),
    (0x0001, 0x010A),
    (0x1209, 0x8007),
}

SystemModeEnum = clusters.OperationalState.Enums.SystemModeEnum
ControlSequenceEnum = clusters.OperationalState.Enums.ControlSequenceOfOperationEnum
ThermostatFeature = clusters.OperationalState.Bitmaps.Feature
'''

class DishwasherOperationalState(IntEnum):
    """Dishwasher OperationalState, Matter spec"""
    Stopped = 0
    Running = 1
    Paused = 2
    Error = 3

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Matter dishwasher platform from Config Entry."""
    matter = get_matter(hass)
    matter.register_platform_handler(Platform.DISHWASHER, async_add_entities)


class MatterDishwasher(MatterEntity, ClimateEntity):
    """Representation of a Matter dishwasher entity."""

    #_attr_temperature_unit: str = UnitOfTemperature.CELSIUS
    #_attr_hvac_mode: HVACMode = HVACMode.OFF
    #_enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        matter_client: MatterClient,
        endpoint: MatterEndpoint,
        entity_info: MatterEntityInfo,
    ) -> None:
        """Initialize the Matter dishwasher entity."""
        super().__init__(matter_client, endpoint, entity_info)
        product_id = self._endpoint.node.device_info.productID
        vendor_id = self._endpoint.node.device_info.vendorID

        """
        # set hvac_modes based on feature map
        self._attr_hvac_modes: list[HVACMode] = [HVACMode.OFF]
        feature_map = int(
            self.get_matter_attribute_value(clusters.OperationalState.Attributes.FeatureMap)
        )
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF
        )
        if feature_map & ThermostatFeature.kHeating:
            self._attr_hvac_modes.append(HVACMode.HEAT)
        if feature_map & ThermostatFeature.kCooling:
            self._attr_hvac_modes.append(HVACMode.COOL)
        if (vendor_id, product_id) in SUPPORT_DRY_MODE_DEVICES:
            self._attr_hvac_modes.append(HVACMode.DRY)
        if (vendor_id, product_id) in SUPPORT_FAN_MODE_DEVICES:
            self._attr_hvac_modes.append(HVACMode.FAN_ONLY)
        if feature_map & ThermostatFeature.kAutoMode:
            self._attr_hvac_modes.append(HVACMode.HEAT_COOL)
            # only enable temperature_range feature if the device actually supports that

            if (vendor_id, product_id) not in SINGLE_SETPOINT_DEVICES:
                self._attr_supported_features |= (
                    ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
                )
        if any(mode for mode in self.hvac_modes if mode != HVACMode.OFF):
            self._attr_supported_features |= ClimateEntityFeature.TURN_ON
        """

    @callback
    def _update_from_device(self) -> None:
        """Update from device."""


"""
Matter-1.3-Application-Cluster-Specification.pdf Page 120

0x0060 Operational State Cluster

This cluster supports remotely monitoring and, where supported, changing the operational state of any device where a state machine is a part of the operation.
This cluster defines common states, scoped to this cluster (e.g. Stopped, Running, Paused, Error). A derived cluster specification may define more states scoped to the derivation. Manufacturer specific states are supported in this cluster and any derived clusters thereof. When defined in a derived instance, such states are scoped to the derivation.

Actual state transitions are dependent on both the implementation, and the requirements that may additionally be imposed by a derived cluster.
An implementation that supports remotely starting its operation can make use of this cluster’s Start command to do so. A device that supports remote pause or stop of its currently selected operation can similarly make use of this cluster’s Pause and Stop commands to do so. The ability to remotely  pause or stop is independent of how the operation was started (for example, an operation started by using a manual button press can be stopped by using a Stop command if the device supports remotely stopping the operation).
Additionally, this cluster provides events for monitoring the operational state of the device.
"""


"""
Matter-1.3-Application-Cluster-Specification.pdf Page 124

0x0000 PhaseList Attribute
    This attribute SHALL indicate a list of names of different phases that the device can go through for
 the selected function or mode.

0x0001 CurrentPhase Attribute
    This attribute represents the current phase of operation being performed by the server. 

0x0003 OperationalStateList Attribute
    This attribute describes the set of possible operational states that the device exposes. An operational state is a fundamental device state such as Running or Error.

0x0004 OperationalState Attribute
    This attribute specifies the current operational state of a device.
"""


# Discovery schema(s) to map Matter Attributes to HA entities
DISCOVERY_SCHEMAS = [
    MatterDiscoverySchema(
        platform=Platform.DISHWASHER,
        entity_description=DishwasherEntityDescription(
            key="MatterDishwasher",
            translation_key="dishwasher",
        ),
        entity_class=MatterDishwasher,
        required_attributes=(
            clusters.OperationalState.Attributes.PhaseList,
            clusters.OperationalState.Attributes.CurrentPhase,
            clusters.OperationalState.Attributes.OperationalState,
            clusters.OperationalState.Attributes.OperationalStateList,
            clusters.OperationalState.Attributes.OperationalState,
        ),
        optional_attributes=(
            clusters.OperationalState.Attributes.FeatureMap,
            clusters.OperationalState.Attributes.GeneratedCommandList,
            clusters.OperationalState.Attributes.AcceptedCommandList,
            
            clusters.OperationalState.Attributes.CountdownTime,
        ),
        device_type=(device_types.Dishwasher),
    ),
]


"""
Matter-1.3-Application-Cluster-Specification.pdf Page 126

Commands
    0x00 Pause
    0x01 Stop
    0x02 Start
    0x03 Resume
    0x04 OperationalCommandResponse

"""
