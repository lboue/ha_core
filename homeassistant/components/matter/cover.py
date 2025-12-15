"""Matter cover."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import floor
from typing import Any

from chip.clusters import Objects as clusters

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import LOGGER
from .entity import MatterEntity, MatterEntityDescription
from .helpers import get_matter
from .models import MatterDiscoverySchema

# The MASK used for extracting bits 0 to 1 of the byte.
OPERATIONAL_STATUS_MASK = 0b11

# map Matter window cover types to HA device class
TYPE_MAP = {
    clusters.WindowCovering.Enums.Type.kRollerShade: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kRollerShade2Motor: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kRollerShadeExterior: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kRollerShadeExterior2Motor: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kAwning: CoverDeviceClass.AWNING,
    clusters.WindowCovering.Enums.Type.kDrapery: CoverDeviceClass.CURTAIN,
    clusters.WindowCovering.Enums.Type.kTiltBlindTiltOnly: CoverDeviceClass.BLIND,
    clusters.WindowCovering.Enums.Type.kTiltBlindLiftAndTilt: CoverDeviceClass.BLIND,
}


def _extract_struct_field(value: Any, index: int, attr_name: str) -> Any:
    """Extract a field from a Matter struct value.

    Matter server can expose cluster struct attributes either as objects or
    simple dictionaries keyed by the TLV field index. We normalize access by
    first checking dict keys and falling back to attribute lookup.
    """

    if value is None:
        return None

    if isinstance(value, dict):
        if index in value:
            return value[index]
        if (index_str := str(index)) in value:
            return value[index_str]

    return getattr(value, attr_name, None)


class OperationalStatus(IntEnum):
    """Currently ongoing operations enumeration for coverings, as defined in the Matter spec."""

    COVERING_IS_CURRENTLY_NOT_MOVING = 0b00
    COVERING_IS_CURRENTLY_OPENING = 0b01
    COVERING_IS_CURRENTLY_CLOSING = 0b10
    RESERVED = 0b11


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Matter Cover from Config Entry."""
    matter = get_matter(hass)
    matter.register_platform_handler(Platform.COVER, async_add_entities)


@dataclass(frozen=True, kw_only=True)
class MatterCoverEntityDescription(CoverEntityDescription, MatterEntityDescription):
    """Describe Matter Cover entities."""


class MatterCover(MatterEntity, CoverEntity):
    """Representation of a Matter Cover."""

    entity_description: MatterCoverEntityDescription

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, if there is no position report, return None."""
        if not self._entity_info.endpoint.has_attribute(
            None, clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths
        ):
            return None

        return (
            self.current_cover_position == 0
            if self.current_cover_position is not None
            else None
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover movement."""
        await self.send_device_command(clusters.WindowCovering.Commands.StopMotion())

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.send_device_command(clusters.WindowCovering.Commands.UpOrOpen())

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.send_device_command(clusters.WindowCovering.Commands.DownOrClose())

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover to a specific position."""
        position = kwargs[ATTR_POSITION]
        await self.send_device_command(
            # value needs to be inverted and is sent in 100ths
            clusters.WindowCovering.Commands.GoToLiftPercentage((100 - position) * 100)
        )

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Set the cover tilt to a specific position."""
        position = kwargs[ATTR_TILT_POSITION]
        await self.send_device_command(
            # value needs to be inverted and is sent in 100ths
            clusters.WindowCovering.Commands.GoToTiltPercentage((100 - position) * 100)
        )

    @callback
    def _update_from_device(self) -> None:
        """Update from device."""
        operational_status = self.get_matter_attribute_value(
            clusters.WindowCovering.Attributes.OperationalStatus
        )

        assert operational_status is not None

        LOGGER.debug(
            "Operational status %s for %s",
            f"{operational_status:#010b}",
            self.entity_id,
        )

        state = operational_status & OPERATIONAL_STATUS_MASK
        match state:
            case OperationalStatus.COVERING_IS_CURRENTLY_OPENING:
                self._attr_is_opening = True
                self._attr_is_closing = False
            case OperationalStatus.COVERING_IS_CURRENTLY_CLOSING:
                self._attr_is_opening = False
                self._attr_is_closing = True
            case _:
                self._attr_is_opening = False
                self._attr_is_closing = False

        if self._entity_info.endpoint.has_attribute(
            None, clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths
        ):
            # current position is inverted in matter (100 is closed, 0 is open)
            current_cover_position = self.get_matter_attribute_value(
                clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths
            )
            self._attr_current_cover_position = (
                100 - floor(current_cover_position / 100)
                if current_cover_position is not None
                else None
            )

            LOGGER.debug(
                "Current position for %s - raw: %s - corrected: %s",
                self.entity_id,
                current_cover_position,
                self.current_cover_position,
            )

        if self._entity_info.endpoint.has_attribute(
            None, clusters.WindowCovering.Attributes.CurrentPositionTiltPercent100ths
        ):
            # current tilt position is inverted in matter (100 is closed, 0 is open)
            current_cover_tilt_position = self.get_matter_attribute_value(
                clusters.WindowCovering.Attributes.CurrentPositionTiltPercent100ths
            )
            self._attr_current_cover_tilt_position = (
                100 - floor(current_cover_tilt_position / 100)
                if current_cover_tilt_position is not None
                else None
            )

            LOGGER.debug(
                "Current tilt position for %s - raw: %s - corrected: %s",
                self.entity_id,
                current_cover_tilt_position,
                self.current_cover_tilt_position,
            )

        # map matter type to HA deviceclass
        device_type: clusters.WindowCovering.Enums.Type = (
            self.get_matter_attribute_value(clusters.WindowCovering.Attributes.Type)
        )
        self._attr_device_class = TYPE_MAP.get(device_type, CoverDeviceClass.AWNING)

        supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )
        commands = self.get_matter_attribute_value(
            clusters.WindowCovering.Attributes.AcceptedCommandList
        )
        if clusters.WindowCovering.Commands.GoToLiftPercentage.command_id in commands:
            supported_features |= CoverEntityFeature.SET_POSITION
        if clusters.WindowCovering.Commands.GoToTiltPercentage.command_id in commands:
            supported_features |= CoverEntityFeature.SET_TILT_POSITION
        self._attr_supported_features = supported_features


def _map_position_to_percentage(
    position: clusters.ClosureControl.Enums.CurrentPositionEnum | None,
) -> int | None:
    """Map ClosureControl position enum to a coarse percentage."""

    match position:
        case clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyClosed:
            return 0
        case clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyOpened:
            return 100
        case clusters.ClosureControl.Enums.CurrentPositionEnum.kPartiallyOpened:
            return 50
        case _:
            return None


class MatterClosureCover(MatterEntity, CoverEntity):
    """Representation of a Matter Closure (garage door) cover."""

    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the closure."""

        await self.send_device_command(
            clusters.ClosureControl.Commands.MoveTo(
                position=clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyOpen,
            )
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the closure."""

        await self.send_device_command(
            clusters.ClosureControl.Commands.MoveTo(
                position=clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyClosed,
            )
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop movement."""

        await self.send_device_command(clusters.ClosureControl.Commands.Stop())

    @callback
    def _update_from_device(self) -> None:
        """Update the entity from ClosureControl attributes."""

        overall_current_state = self.get_matter_attribute_value(
            clusters.ClosureControl.Attributes.OverallCurrentState
        )
        main_state = self.get_matter_attribute_value(
            clusters.ClosureControl.Attributes.MainState
        )
        overall_target_state = self.get_matter_attribute_value(
            clusters.ClosureControl.Attributes.OverallTargetState
        )

        position = _extract_struct_field(overall_current_state, 0, "position")
        target_position = _extract_struct_field(overall_target_state, 0, "position")

        if isinstance(position, int):
            position = clusters.ClosureControl.Enums.CurrentPositionEnum(position)
        if isinstance(target_position, int):
            target_position = clusters.ClosureControl.Enums.TargetPositionEnum(
                target_position
            )
        if isinstance(main_state, int):
            main_state = clusters.ClosureControl.Enums.MainStateEnum(main_state)

        if position is None:
            self._attr_is_closed = None
            self._attr_current_cover_position = None
        else:
            self._attr_is_closed = (
                position
                == clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyClosed
            )
            self._attr_current_cover_position = _map_position_to_percentage(position)

        self._attr_is_opening = False
        self._attr_is_closing = False

        if main_state == clusters.ClosureControl.Enums.MainStateEnum.kMoving:
            if (
                target_position
                == clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyOpen
            ):
                self._attr_is_opening = True
            elif (
                target_position
                == clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyClosed
            ):
                self._attr_is_closing = True


# Discovery schema(s) to map Matter Attributes to HA entities
DISCOVERY_SCHEMAS = [
    MatterDiscoverySchema(
        platform=Platform.COVER,
        entity_description=MatterCoverEntityDescription(
            key="MatterCover",
            name=None,
        ),
        entity_class=MatterCover,
        required_attributes=(
            clusters.WindowCovering.Attributes.OperationalStatus,
            clusters.WindowCovering.Attributes.Type,
        ),
        absent_attributes=(
            clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths,
            clusters.WindowCovering.Attributes.CurrentPositionTiltPercent100ths,
        ),
    ),
    MatterDiscoverySchema(
        platform=Platform.COVER,
        entity_description=MatterCoverEntityDescription(
            key="MatterCoverPositionAwareLift", name=None
        ),
        entity_class=MatterCover,
        required_attributes=(
            clusters.WindowCovering.Attributes.OperationalStatus,
            clusters.WindowCovering.Attributes.Type,
            clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths,
        ),
        absent_attributes=(
            clusters.WindowCovering.Attributes.CurrentPositionTiltPercent100ths,
        ),
    ),
    MatterDiscoverySchema(
        platform=Platform.COVER,
        entity_description=MatterCoverEntityDescription(
            key="MatterCoverPositionAwareTilt", name=None
        ),
        entity_class=MatterCover,
        required_attributes=(
            clusters.WindowCovering.Attributes.OperationalStatus,
            clusters.WindowCovering.Attributes.Type,
            clusters.WindowCovering.Attributes.CurrentPositionTiltPercent100ths,
        ),
        absent_attributes=(
            clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths,
        ),
    ),
    MatterDiscoverySchema(
        platform=Platform.COVER,
        entity_description=MatterCoverEntityDescription(
            key="MatterCoverPositionAwareLiftAndTilt", name=None
        ),
        entity_class=MatterCover,
        required_attributes=(
            clusters.WindowCovering.Attributes.OperationalStatus,
            clusters.WindowCovering.Attributes.Type,
            clusters.WindowCovering.Attributes.CurrentPositionLiftPercent100ths,
            clusters.WindowCovering.Attributes.CurrentPositionTiltPercent100ths,
        ),
    ),
    MatterDiscoverySchema(
        platform=Platform.COVER,
        entity_description=MatterCoverEntityDescription(
            key="MatterClosureCover",
            name=None,
        ),
        entity_class=MatterClosureCover,
        required_attributes=(clusters.ClosureControl.Attributes.OverallCurrentState,),
        optional_attributes=(
            clusters.ClosureControl.Attributes.MainState,
            clusters.ClosureControl.Attributes.OverallTargetState,
        ),
        allow_none_value=True,
    ),
]
