"""Matter Camera platform."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from chip.clusters import Objects as clusters
from chip.clusters.Objects import NullValue
from matter_server.common.errors import MatterError
from matter_server.common.models import EventType, WebRTCCallbackData
from webrtc_models import RTCIceCandidateInit

from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    CameraEntityFeature,
    WebRTCAnswer,
    WebRTCCandidate,
    WebRTCSendMessage,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import MatterEntity, MatterEntityDescription
from .helpers import MatterConfigEntry
from .models import MatterDiscoverySchema


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MatterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Matter Camera platform from Config Entry."""
    matter = config_entry.runtime_data.adapter
    matter.register_platform_handler(Platform.CAMERA, async_add_entities)


@dataclass(frozen=True, kw_only=True)
class MatterCameraEntityDescription(CameraEntityDescription, MatterEntityDescription):
    """Describe Matter Camera entities."""


class MatterCamera(MatterEntity, Camera):
    """Representation of a Matter Camera entity with WebRTC live view support."""

    entity_description: MatterCameraEntityDescription
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Matter Camera entity."""
        super().__init__(*args, **kwargs)
        Camera.__init__(self)
        # maps HA webrtc session_id to the Matter WebRTCSessionID
        self._webrtc_sessions: dict[str, int] = {}
        self._unsub_webrtc: dict[str, Callable[[], None]] = {}

    @override
    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Matter cameras do not support still images in this version."""
        return None

    @override
    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        """Handle the WebRTC offer by forwarding it to the Matter camera."""

        @callback
        def _on_webrtc_callback(event: EventType, data: WebRTCCallbackData) -> None:
            if (
                data.endpoint_id != self._endpoint.endpoint_id
                or data.webrtc_session_id != self._webrtc_sessions.get(session_id)
                or data.data is None
            ):
                return
            if data.event_type == "answer":
                send_message(WebRTCAnswer(data.data["sdp"]))
            elif data.event_type == "ice_candidates":
                for candidate in data.data["ice_candidates"]:
                    send_message(
                        WebRTCCandidate(
                            RTCIceCandidateInit(
                                candidate.candidate,
                                sdp_mid=candidate.sdpMid,
                                sdp_m_line_index=candidate.sdpMLineIndex,
                            )
                        )
                    )
            elif data.event_type == "end":
                self.close_webrtc_session(session_id)

        # subscribe before sending the offer to avoid missing a fast answer
        self._unsub_webrtc[session_id] = self.matter_client.subscribe_events(
            callback=_on_webrtc_callback,
            event_filter=EventType.WEBRTC_CALLBACK,
            node_filter=self._endpoint.node.node_id,
        )
        try:
            response = await self.matter_client.send_webrtc_provider_command(
                node_id=self._endpoint.node.node_id,
                endpoint_id=self._endpoint.endpoint_id,
                command_name="ProvideOffer",
                payload={
                    "webRtcSessionID": NullValue,
                    "sdp": offer_sdp,
                    "streamUsage": clusters.Globals.Enums.StreamUsageEnum.kLiveView,
                },
            )
        except MatterError as err:
            self.close_webrtc_session(session_id)
            raise HomeAssistantError(str(err) or err.__class__.__name__) from err
        self._webrtc_sessions[session_id] = response["webRtcSessionID"]

    @override
    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        """Ignore local ICE candidates.

        The Matter server does not yet expose a way to forward locally
        generated ICE candidates to the camera (only ProvideOffer/SolicitOffer
        are wired up), so trickle ICE from the HA side is not supported yet.
        """

    @callback
    @override
    def close_webrtc_session(self, session_id: str) -> None:
        """Close a WebRTC session."""
        self._webrtc_sessions.pop(session_id, None)
        if unsub := self._unsub_webrtc.pop(session_id, None):
            unsub()
        super().close_webrtc_session(session_id)

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Clean up any open WebRTC sessions when the entity is removed."""
        await super().async_will_remove_from_hass()
        for session_id in list(self._webrtc_sessions):
            self.close_webrtc_session(session_id)


# Discovery schema(s) to map Matter Attributes to HA entities
DISCOVERY_SCHEMAS = [
    MatterDiscoverySchema(
        platform=Platform.CAMERA,
        entity_description=MatterCameraEntityDescription(key="MatterCamera"),
        entity_class=MatterCamera,
        required_attributes=(
            clusters.WebRtcTransportProvider.Attributes.CurrentSessions,
        ),
    ),
]
