"""Matter SmokeCO sensor."""

from __future__ import annotations

from dataclasses import dataclass

from chip.clusters import Objects as clusters
from chip.clusters.Objects import uint
from chip.clusters.Types import Nullable, NullValue
from matter_server.client.models import device_types

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import MatterEntity, MatterEntityDescription
from .helpers import get_matter
from .models import MatterDiscoverySchema


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Matter binary sensor from Config Entry."""
    matter = get_matter(hass)
    matter.register_platform_handler(Platform.BINARY_SENSOR, async_add_entities)


@dataclass(frozen=True)
class MatterSmokeCOSensorEntityDescription(
    BinarySensorEntityDescription, MatterEntityDescription
):
    """Describe Matter binary sensor entities."""


class MatterSmokeCOSensor(MatterEntity, BinarySensorEntity):
    """Representation of a Matter binary sensor."""

    entity_description: MatterSmokeCOSensorEntityDescription

    @callback
    def _update_from_device(self) -> None:
        """Update from device."""
        value: bool | uint | int | Nullable | None
        value = self.get_matter_attribute_value(self._entity_info.primary_attribute)
        if value in (None, NullValue):
            value = None
        elif value_convert := self.entity_description.measurement_to_ha:
            value = value_convert(value)
        self._attr_is_on = value


# Discovery schema(s) to map Matter Attributes to HA entities
DISCOVERY_SCHEMAS = [
    # BooleanState sensors (tied to device type)
    MatterDiscoverySchema(
        platform=Platform.BINARY_SENSOR,
        entity_description=MatterSmokeCOSensorEntityDescription(
            key="SmokeStateSensor",
            device_class=BinarySensorDeviceClass.SMOKE,
            # pylint: disable=unnecessary-lambda
            measurement_to_ha=lambda x: {
                clusters.SmokeCoAlarm.Enums.SmokeState.kNormal: True,
                clusters.SmokeCoAlarm.Enums.SmokeState.kWarning: True,
                clusters.SmokeCoAlarm.Enums.SmokeState.kCritical: False,
            }.get(x),
        ),
        entity_class=MatterSmokeCOSensor,
        required_attributes=(clusters.SmokeCoAlarm.Attributes.SmokeState,),
    ),
    MatterDiscoverySchema(
        platform=Platform.BINARY_SENSOR,
        entity_description=MatterSmokeCOSensorEntityDescription(
            key="COStateSensor",
            device_class=BinarySensorDeviceClass.CARBON_MONOXIDE,
            # pylint: disable=unnecessary-lambda
            measurement_to_ha=lambda x: {
                clusters.SmokeCoAlarm.Enums.COState.kNormal: True,
                clusters.SmokeCoAlarm.Enums.COState.kWarning: True,
                clusters.SmokeCoAlarm.Enums.COState.kCritical: False,
            }.get(x),
        ),
        entity_class=MatterSmokeCOSensor,
        required_attributes=(clusters.SmokeCoAlarm.Attributes.COState,),
    ),
]
