"""Constants for the Matter integration."""

import logging

ADDON_SLUG = "core_matter_server"

CONF_INTEGRATION_CREATED_ADDON = "integration_created_addon"
CONF_USE_ADDON = "use_addon"

DOMAIN = "matter"
LOGGER = logging.getLogger(__package__)

# prefixes to identify device identifier id types
ID_TYPE_DEVICE_ID = "deviceid"
ID_TYPE_SERIAL = "serial"

FEATUREMAP_ATTRIBUTE_ID = 65532

ATTR_UNOCCUPIED_HVAC_MODE = "unoccupied_hvac_mode"
ATTR_UNOCCUPIED_TEMPERATURE = "unoccupied_temperature"
ATTR_UNOCCUPIED_COOLING_TEMPERATURE = "unoccupied_cooling_temperature"
ATTR_UNOCCUPIED_HEATING_TEMPERATURE = "unoccupied_heating_temperature"
