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


def _get_closure_device_class(tag_list: Any) -> CoverDeviceClass:
    """Get device class for a closure device from TagList.

    TagList (Descriptor attribute 4) contains semantic tags that identify the
    device type. Returns the appropriate CoverDeviceClass based on the tags
    found. Prioritizes more specific Covering.* tags over generic Closure.* tags.
    """
    if not isinstance(tag_list, list):
        return CoverDeviceClass.GARAGE  # Default for closures

    # Map covering tags to device classes
    # Check Covering.* tags first (more specific), then Closure.* tags (more generic)
    tag_mapping_priority = [
        {
            "Covering.Blind": CoverDeviceClass.BLIND,
            "Covering.Awning": CoverDeviceClass.AWNING,
            "Covering.Shutter": CoverDeviceClass.SHUTTER,
            "Covering.Venetian": CoverDeviceClass.BLIND,
            "Covering.Curtain": CoverDeviceClass.CURTAIN,
        },
        {
            "Closure.GarageDoor": CoverDeviceClass.GARAGE,
        },
    ]

    for tag_mapping in tag_mapping_priority:
        for tag in tag_list:
            tag_value_obj: Any | None = None
            if isinstance(tag, dict):
                tag_value_obj = tag.get("3")
            elif isinstance(tag, str):
                tag_value_obj = tag
            else:
                # Handle semantic tag structs (objects with a 'label' attribute)
                tag_value_obj = getattr(tag, "label", None)

            tag_value = str(tag_value_obj) if tag_value_obj is not None else None

            if tag_value and tag_value in tag_mapping:
                return tag_mapping[tag_value]

            # Fallback: if label isn't matched, try namespace/tag numeric values
            # Covering.Venetian is commonly namespaceID=70, tag=3
            namespace_id = _extract_struct_field(tag, 1, "namespaceID")
            tag_id = _extract_struct_field(tag, 2, "tag")
            if namespace_id == 70 and tag_id == 3:
                return CoverDeviceClass.BLIND

    return CoverDeviceClass.GARAGE


def _map_position_to_percentage(
    position: clusters.ClosureControl.Enums.CurrentPositionEnum | None,
) -> int | None:
    """Map ClosureControl position enum to a coarse percentage when Positioning is supported.

    Used only when the device advertises Positioning feature support.
    """
    match position:
        case clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyClosed:
            return 0
        case clusters.ClosureControl.Enums.CurrentPositionEnum.kFullyOpened:
            return 100
        case clusters.ClosureControl.Enums.CurrentPositionEnum.kPartiallyOpened:
            return 50
        case _:
            return None


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


# Closure devices support only discrete open/close/stop commands, not arbitrary positioning.
# Even with the Positioning feature, it only guarantees fully open (0%) and fully closed (100%)
# states, not arbitrary position control. Do not expose current_position or SET_POSITION.


class MatterClosure(MatterEntity, CoverEntity):
    """Representation of a Matter Closure (garage door, shade, etc.) cover.

    Closure devices only support OPEN, CLOSE, and STOP commands, with discrete
    position states (fully open or fully closed). They do not support arbitrary
    position control, so position attributes and SET_POSITION feature are not exposed.
    """

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        matter_client: Any,
        endpoint: Any,
        entity_info: Any,
    ) -> None:
        """Initialize the Matter Closure.

        Determine device class from Descriptor.TagList before base init so the
        initial state includes the correct device_class.
        """
        # Precompute device class from TagList on the endpoint's Descriptor cluster
        # Attribute ID 4 in the Descriptor cluster (ID 29) is the TagList containing semantic tags.
        # Access it directly via node.attributes.
        pre_tag_list: Any | None = None
        # Prefer reading via endpoint API (Descriptor.TagList is attribute 4)
        try:
            pre_tag_list = endpoint.get_attribute_value(
                None, clusters.Descriptor.Attributes.TagList
            )
        except (AttributeError, LookupError, TypeError, ValueError):
            pre_tag_list = None

        # Fallback to raw node attribute store if API doesn't surface TagList
        if (
            pre_tag_list is None
            and hasattr(endpoint, "node")
            and hasattr(endpoint.node, "attributes")
        ):
            cluster_key = f"{endpoint.endpoint_id}/29/4"
            pre_tag_list = endpoint.node.attributes.get(cluster_key)

        self._attr_device_class = _get_closure_device_class(pre_tag_list)

        # Continue with base initialization
        super().__init__(matter_client, endpoint, entity_info)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the closure."""

        command_kwargs = {
            "position": clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyOpen,
        }

        if self._motion_latching_supported():
            command_kwargs["latch"] = False

        await self.send_device_command(
            clusters.ClosureControl.Commands.MoveTo(**command_kwargs),
            timed_request_timeout_ms=1000,
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the closure."""

        command_kwargs = {
            "position": clusters.ClosureControl.Enums.TargetPositionEnum.kMoveToFullyClosed,
        }

        if self._motion_latching_supported():
            command_kwargs["latch"] = False

        await self.send_device_command(
            clusters.ClosureControl.Commands.MoveTo(**command_kwargs),
            timed_request_timeout_ms=1000,
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop movement."""

        await self.send_device_command(
            clusters.ClosureControl.Commands.Stop(),
            timed_request_timeout_ms=1000,
        )

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
            # Closure devices with Positioning feature only support discrete positions
            # (fully open at 0% and fully closed at 100%), not arbitrary positioning.
            # Do not expose current_position or enable SET_POSITION.
            self._attr_current_cover_position = None

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

    def _motion_latching_supported(self) -> bool:
        """Return True if MotionLatching feature is supported."""

        feature_map = self.get_matter_attribute_value(
            clusters.ClosureControl.Attributes.FeatureMap
        )

        if not isinstance(feature_map, int):
            return False

        return bool(
            feature_map & clusters.ClosureControl.Bitmaps.Feature.kMotionLatching
        )


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
            key="MatterClosure",
            name=None,
        ),
        entity_class=MatterClosure,
        required_attributes=(clusters.ClosureControl.Attributes.OverallCurrentState,),
        optional_attributes=(
            clusters.ClosureControl.Attributes.MainState,
            clusters.ClosureControl.Attributes.OverallTargetState,
        ),
        allow_none_value=True,
    ),
    MatterDiscoverySchema(
        platform=Platform.COVER,
        entity_description=MatterCoverEntityDescription(
            key="MatterClosureMotionLatching",
            name=None,
        ),
        entity_class=MatterClosure,
        required_attributes=(clusters.ClosureControl.Attributes.OverallCurrentState,),
        optional_attributes=(
            clusters.ClosureControl.Attributes.MainState,
            clusters.ClosureControl.Attributes.OverallTargetState,
        ),
        allow_none_value=True,
        featuremap_contains=clusters.ClosureControl.Bitmaps.Feature.kMotionLatching,
    ),
]
