"""Test Matter cameras."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, call, patch

from chip.clusters import Objects as clusters
from chip.clusters.Objects import NullValue
from matter_server.client.models.node import MatterNode
from matter_server.common.models import EventType, WebRTCCallbackData
import pytest
from syrupy.assertion import SnapshotAssertion
from webrtc_models import RTCIceCandidateInit

from homeassistant.components.camera import (
    WebRTCAnswer,
    WebRTCCandidate,
    get_camera_from_entity_id,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import snapshot_matter_entities, trigger_subscription_callback

CAMERA_ENTITY_ID = "camera.mock_camera"


@pytest.fixture(autouse=True)
def mock_getrandbits() -> Generator[None]:
    """Mock camera access token which normally is randomized."""
    with patch(
        "homeassistant.components.camera.SystemRandom.getrandbits",
        return_value=1,
    ):
        yield


@pytest.mark.usefixtures("matter_devices")
async def test_cameras(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test cameras."""
    snapshot_matter_entities(hass, entity_registry, snapshot, Platform.CAMERA)


@pytest.mark.parametrize("node_fixture", ["mock_camera"])
async def test_webrtc_offer(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test a WebRTC offer is forwarded to the Matter camera."""
    matter_client.send_webrtc_provider_command = AsyncMock(
        return_value={"webRtcSessionID": 42}
    )
    camera = get_camera_from_entity_id(hass, CAMERA_ENTITY_ID)
    send_message = MagicMock()

    await camera.async_handle_async_webrtc_offer(
        "v=0\r\n", "session_id_1", send_message
    )

    assert matter_client.send_webrtc_provider_command.call_count == 1
    assert matter_client.send_webrtc_provider_command.call_args == call(
        node_id=matter_node.node_id,
        endpoint_id=1,
        command_name="ProvideOffer",
        payload={
            "webRtcSessionID": NullValue,
            "sdp": "v=0\r\n",
            "streamUsage": clusters.Globals.Enums.StreamUsageEnum.kLiveView,
        },
    )

    # simulate the camera's answer arriving via the WebRTCTransportRequestor cluster
    await trigger_subscription_callback(
        hass,
        matter_client,
        EventType.WEBRTC_CALLBACK,
        WebRTCCallbackData(
            event_type="answer",
            webrtc_session_id=42,
            node_id=matter_node.node_id,
            endpoint_id=1,
            fabric_index=1,
            data={"sdp": "answer-sdp"},
        ),
    )

    send_message.assert_called_once_with(WebRTCAnswer("answer-sdp"))


@pytest.mark.parametrize("node_fixture", ["mock_camera"])
async def test_webrtc_ice_candidates(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test ICE candidates received from the camera are forwarded to HA."""
    matter_client.send_webrtc_provider_command = AsyncMock(
        return_value={"webRtcSessionID": 42}
    )
    camera = get_camera_from_entity_id(hass, CAMERA_ENTITY_ID)
    send_message = MagicMock()

    await camera.async_handle_async_webrtc_offer(
        "v=0\r\n", "session_id_1", send_message
    )

    candidate = MagicMock(candidate="candidate-1", sdpMid="0", sdpMLineIndex=0)
    await trigger_subscription_callback(
        hass,
        matter_client,
        EventType.WEBRTC_CALLBACK,
        WebRTCCallbackData(
            event_type="ice_candidates",
            webrtc_session_id=42,
            node_id=matter_node.node_id,
            endpoint_id=1,
            fabric_index=1,
            data={"ice_candidates": [candidate]},
        ),
    )

    send_message.assert_called_once_with(
        WebRTCCandidate(
            RTCIceCandidateInit("candidate-1", sdp_mid="0", sdp_m_line_index=0)
        )
    )


@pytest.mark.parametrize("node_fixture", ["mock_camera"])
@pytest.mark.usefixtures("matter_node")
async def test_webrtc_candidate_from_ha_is_ignored(
    hass: HomeAssistant,
    matter_client: MagicMock,
) -> None:
    """Test local ICE candidates are not forwarded (not yet supported)."""
    camera = get_camera_from_entity_id(hass, CAMERA_ENTITY_ID)

    await camera.async_on_webrtc_candidate(
        "session_id_1", RTCIceCandidateInit("candidate-1")
    )

    assert not hasattr(matter_client, "send_webrtc_provider_ice_command")


@pytest.mark.parametrize("node_fixture", ["mock_camera"])
async def test_webrtc_session_end(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_node: MatterNode,
) -> None:
    """Test the camera cleans up its session when the device ends it."""
    matter_client.send_webrtc_provider_command = AsyncMock(
        return_value={"webRtcSessionID": 42}
    )
    camera = get_camera_from_entity_id(hass, CAMERA_ENTITY_ID)
    send_message = MagicMock()

    await camera.async_handle_async_webrtc_offer(
        "v=0\r\n", "session_id_1", send_message
    )
    assert "session_id_1" in camera._webrtc_sessions

    await trigger_subscription_callback(
        hass,
        matter_client,
        EventType.WEBRTC_CALLBACK,
        WebRTCCallbackData(
            event_type="end",
            webrtc_session_id=42,
            node_id=matter_node.node_id,
            endpoint_id=1,
            fabric_index=1,
            data={"reason": 0},
        ),
    )

    assert "session_id_1" not in camera._webrtc_sessions


@pytest.mark.parametrize("node_fixture", ["mock_camera"])
@pytest.mark.usefixtures("matter_node")
async def test_camera_image_not_supported(
    hass: HomeAssistant,
    matter_client: MagicMock,
) -> None:
    """Test still images are not supported in this version."""
    camera = get_camera_from_entity_id(hass, CAMERA_ENTITY_ID)
    assert await camera.async_camera_image() is None
