"""The tests for the Netatmo api."""

from unittest.mock import Mock

from pyatmo.const import ALL_SCOPES
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components import cloud
from homeassistant.components.netatmo import api
from homeassistant.components.netatmo.const import (
    API_SCOPES_EXCLUDED_FROM_CLOUD,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation,
    LocalOAuth2Implementation,
    OAuth2Session,
)


async def test_get_api_scopes_cloud() -> None:
    """Test method to get API scopes when using cloud auth implementation."""
    result = api.get_api_scopes(cloud.DOMAIN)

    for scope in API_SCOPES_EXCLUDED_FROM_CLOUD:
        assert scope not in result


async def test_get_api_scopes_other() -> None:
    """Test method to get API scopes when using cloud auth implementation."""
    result = api.get_api_scopes("netatmo_239846i2f0j2")

    assert sorted(ALL_SCOPES) == result


@pytest.fixture(name="entry")
def entry_fixture(hass: HomeAssistant) -> MockConfigEntry:
    """Return a bare config entry, only needed to build an OAuth2Session."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    return entry


async def test_webhook_signing_secret_local_implementation(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Test the webhook signing secret is the local implementation's client secret."""
    implementation = LocalOAuth2Implementation(
        hass,
        DOMAIN,
        "client-id",
        "client-secret",
        "https://example.com/auth",
        "https://example.com/token",
    )
    session = OAuth2Session(hass, entry, implementation)
    auth = api.AsyncConfigEntryNetatmoAuth(Mock(), session)

    assert auth.webhook_signing_secret == "client-secret"


async def test_webhook_signing_secret_cloud_implementation(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Test the webhook signing secret is unavailable for a non-local implementation."""
    session = OAuth2Session(hass, entry, Mock(spec=AbstractOAuth2Implementation))
    auth = api.AsyncConfigEntryNetatmoAuth(Mock(), session)

    assert auth.webhook_signing_secret is None
