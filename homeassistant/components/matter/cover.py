"""Matter cover."""

from dataclasses import dataclass
from enum import IntEnum
from math import floor
from typing import Any

from chip.clusters import Objects as clusters
from chip.clusters.cluster_defs.Globals import Globals
from matter_server.client.models import device_types

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import LOGGER
from .entity import MatterEntity, MatterEntityDescription
from .helpers import MatterConfigEntry
from .models import MatterDiscoverySchema

# The MASK used for extracting bits 0 to 1 of the byte.
OPERATIONAL_STATUS_MASK = 0b11

# map Matter window cover types to HA device class
TYPE_MAP = {
    clusters.WindowCovering.Enums.Type.kRollerShade: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kRollerShade2Motor: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kRollerShadeExterior: CoverDeviceClass.SHADE,
    clusters.WindowCovering.Enums.Type.kRollerShadeExterior2Motor: (
        CoverDeviceClass.SHADE
    ),
    clusters.WindowCovering.Enums.Type.kAwning: CoverDeviceClass.AWNING,
    clusters.WindowCovering.Enums.Type.kDrapery: CoverDeviceClass.CURTAIN,
    clusters.WindowCovering.Enums.Type.kTiltBlindTiltOnly: CoverDeviceClass.BLIND,
    clusters.WindowCovering.Enums.Type.kTiltBlindLiftAndTilt: CoverDeviceClass.BLIND,
}

POSITION_TO_PERCENT = {
    clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyClosed: 0,
    clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyOpened: 100,
    clusters.ClosureControl.Enums.CurrentPositionEnum.kPartiallyOpened: 50,
    clusters.ClosureControl.Enums.CurrentPositionEnum.kOpenedForPedestrian: 25,
    clusters.ClosureControl.Enums.CurrentPositionEnum.kOpenedForVentilation: 75,
    clusters.ClosureControl.Enums.CurrentPositionEnum.kOpenedAtSignature: 90,
}

GARAGE_DOOR_TAG_NAMESPACE_ID = int(Globals.Enums.namespace.kClosure)

# Closure Semantic Tag Namespace
# tuple format: (tag name, tag id)
CLOSURE_TAGS: tuple[tuple[str, int], ...] = (
    ("Covering", 0x00),
    ("Window", 0x01),
    ("Barrier", 0x02),
    ("Cabinet", 0x03),
    ("Gate", 0x04),
    ("GarageDoor", 0x05),
    ("Door", 0x06),
)

CLOSURE_TAG_ID_BY_NAME = dict(CLOSURE_TAGS)


def _has_closure_tag(endpoint: Any, namespace_id: int, tag_id: int) -> bool:
    """Return true if the endpoint Descriptor TagList includes a semtag."""
    tag_list = endpoint.get_attribute_value(
        None, clusters.Descriptor.Attributes.TagList
    )
    return any(
        (
            getattr(tag, "namespaceID", None) == namespace_id
            and getattr(tag, "tag", None) == tag_id
        )
        for tag in tag_list or []
    )


def _current_closure_position_percent(position: Any) -> int | None:
    """Convert a ClosureControl position enum to a cover percentage."""
    if position is None:
        return None
    return POSITION_TO_PERCENT.get(position)


def _target_closure_position_for_percent(
    position: int,
) -> clusters.ClosureControl.Enums.TargetPositionEnum:
    """Convert a cover percentage to a ClosureControl target position."""
    if position <= 0:
        return clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyClosed
    if position >= 100:
        return clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyOpen
    if position <= 25:
        return (
            clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToPedestrianPosition
        )
    if position <= 75:
        return (
            clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToVentilationPosition
        )
    return clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToSignaturePosition


class OperationalStatus(IntEnum):
    """Ongoing operations enumeration for coverings per Matter spec."""

    COVERING_IS_CURRENTLY_NOT_MOVING = 0b00
    COVERING_IS_CURRENTLY_OPENING = 0b01
    COVERING_IS_CURRENTLY_CLOSING = 0b10
    RESERVED = 0b11


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MatterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Matter Cover from Config Entry."""
    matter = config_entry.runtime_data.adapter
    matter.register_platform_handler(Platform.COVER, async_add_entities)


@dataclass(frozen=True, kw_only=True)
class MatterCoverEntityDescription(CoverEntityDescription, MatterEntityDescription):
    """Describe Matter Cover entities."""


class MatterCover(MatterEntity, CoverEntity):
    """Representation of a Matter Cover."""

    entity_description: MatterCoverEntityDescription

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, None if no position."""
        if self._entity_info.endpoint.has_cluster(clusters.ClosureControl):
            current_state = self.get_matter_attribute_value(
                clusters.ClosureControl.Attributes.OverallCurrentState
            )
            if current_state is None or current_state.position is None:
                return None
            return (
                current_state.position
                == clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyClosed
            )

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
        if self._entity_info.endpoint.has_cluster(clusters.ClosureControl):
            await self.send_device_command(clusters.ClosureControl.Commands.Stop())
            return

        await self.send_device_command(clusters.WindowCovering.Commands.StopMotion())

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self._entity_info.endpoint.has_cluster(clusters.ClosureControl):
            await self.send_device_command(
                clusters.ClosureControl.Commands.MoveTo(
                    position=clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyOpen
                )
            )
            return

        await self.send_device_command(clusters.WindowCovering.Commands.UpOrOpen())

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if self._entity_info.endpoint.has_cluster(clusters.ClosureControl):
            await self.send_device_command(
                clusters.ClosureControl.Commands.MoveTo(
                    position=clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyClosed
                )
            )
            return

        await self.send_device_command(clusters.WindowCovering.Commands.DownOrClose())

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set the cover to a specific position."""
        position = kwargs[ATTR_POSITION]
        if self._entity_info.endpoint.has_cluster(clusters.ClosureControl):
            await self.send_device_command(
                clusters.ClosureControl.Commands.MoveTo(
                    position=_target_closure_position_for_percent(position)
                )
            )
            return

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
        if self._entity_info.endpoint.has_cluster(clusters.ClosureControl):
            current_state = self.get_matter_attribute_value(
                clusters.ClosureControl.Attributes.OverallCurrentState
            )
            target_state = self.get_matter_attribute_value(
                clusters.ClosureControl.Attributes.OverallTargetState
            )
            current_position = getattr(current_state, "position", None)
            target_position = getattr(target_state, "position", None)

            self._attr_is_opening = False
            self._attr_is_closing = False
            if current_position is not None:
                self._attr_current_cover_position = _current_closure_position_percent(
                    current_position
                )
                if (
                    target_position is not None
                    and current_state.position != target_state.position
                ):
                    current_percent = _current_closure_position_percent(
                        current_position
                    )
                    target_percent = _current_closure_position_percent(target_position)
                    if current_percent is not None and target_percent is not None:
                        self._attr_is_opening = current_percent < target_percent
                        self._attr_is_closing = current_percent > target_percent

            self._attr_device_class = (
                CoverDeviceClass.GARAGE
                if _has_closure_tag(
                    self._entity_info.endpoint,
                    GARAGE_DOOR_TAG_NAMESPACE_ID,
                    CLOSURE_TAG_ID_BY_NAME["GarageDoor"],
                )
                else CoverDeviceClass.AWNING
            )
            supported_features = (
                CoverEntityFeature.OPEN
                | CoverEntityFeature.CLOSE
                | CoverEntityFeature.STOP
            )
            commands = self.get_matter_attribute_value(
                clusters.ClosureControl.Attributes.AcceptedCommandList
            )
            if clusters.ClosureControl.Commands.MoveTo.command_id in commands:
                supported_features |= CoverEntityFeature.SET_POSITION
            self._attr_supported_features = supported_features
            return

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
            key="MatterClosureControlGarageDoor", name=None
        ),
        entity_class=MatterCover,
        device_type=(device_types.Closure,),
        required_attributes=(
            clusters.ClosureControl.Attributes.MainState,
            clusters.Descriptor.Attributes.TagList,
            clusters.ClosureControl.Attributes.OverallCurrentState,
            clusters.ClosureControl.Attributes.OverallTargetState,
        ),
        tag_list_contains=(
            GARAGE_DOOR_TAG_NAMESPACE_ID,
            CLOSURE_TAG_ID_BY_NAME["GarageDoor"],
        ),
        featuremap_contains=clusters.ClosureControl.Bitmaps.Feature.kPositioning,
    ),
]
