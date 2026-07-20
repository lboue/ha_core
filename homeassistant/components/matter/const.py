"""Constants for the Matter integration."""

import logging
from typing import Final

from chip.clusters import Objects as clusters

ADDON_SLUG = "core_matter_server"

CONF_INTEGRATION_CREATED_ADDON = "integration_created_addon"
CONF_USE_ADDON = "use_addon"

DOMAIN = "matter"
LOGGER = logging.getLogger(__package__)

# prefixes to identify device identifier id types
ID_TYPE_DEVICE_ID = "deviceid"
ID_TYPE_SERIAL = "serial"

FEATUREMAP_ATTRIBUTE_ID = 65532

# --- Lock domain constants ---

# Shared field keys
ATTR_CREDENTIAL_RULE = "credential_rule"
ATTR_MAX_CREDENTIALS_PER_USER = "max_credentials_per_user"
ATTR_MAX_PIN_USERS = "max_pin_users"
ATTR_MAX_RFID_USERS = "max_rfid_users"
ATTR_MAX_USERS = "max_users"
ATTR_SUPPORTS_USER_MGMT = "supports_user_management"
ATTR_USER_INDEX = "user_index"
ATTR_USER_NAME = "user_name"
ATTR_USER_STATUS = "user_status"
ATTR_USER_TYPE = "user_type"

# Magic values
CLEAR_ALL_INDEX = 0xFFFE  # Matter spec: pass to ClearUser/ClearCredential to clear all

# Timed request timeout for lock commands that modify state.
# 10 seconds accounts for Thread network latency and retransmissions.
LOCK_TIMED_REQUEST_TIMEOUT_MS = 10000

# Credential field keys
ATTR_CREDENTIAL_DATA = "credential_data"
ATTR_CREDENTIAL_INDEX = "credential_index"
ATTR_CREDENTIAL_TYPE = "credential_type"

# Credential type strings
CRED_TYPE_FACE = "face"
CRED_TYPE_FINGERPRINT = "fingerprint"
CRED_TYPE_FINGER_VEIN = "finger_vein"
CRED_TYPE_PIN = "pin"
CRED_TYPE_RFID = "rfid"

# User status mapping (Matter DoorLock UserStatusEnum)
_UserStatus = clusters.DoorLock.Enums.UserStatusEnum
USER_STATUS_MAP: dict[int, str] = {
    _UserStatus.kAvailable: "available",
    _UserStatus.kOccupiedEnabled: "occupied_enabled",
    _UserStatus.kOccupiedDisabled: "occupied_disabled",
}
USER_STATUS_REVERSE_MAP: dict[str, int] = {v: k for k, v in USER_STATUS_MAP.items()}

# User type mapping (Matter DoorLock UserTypeEnum)
_UserType = clusters.DoorLock.Enums.UserTypeEnum
USER_TYPE_MAP: dict[int, str] = {
    _UserType.kUnrestrictedUser: "unrestricted_user",
    _UserType.kYearDayScheduleUser: "year_day_schedule_user",
    _UserType.kWeekDayScheduleUser: "week_day_schedule_user",
    _UserType.kProgrammingUser: "programming_user",
    _UserType.kNonAccessUser: "non_access_user",
    _UserType.kForcedUser: "forced_user",
    _UserType.kDisposableUser: "disposable_user",
    _UserType.kExpiringUser: "expiring_user",
    _UserType.kScheduleRestrictedUser: "schedule_restricted_user",
    _UserType.kRemoteOnlyUser: "remote_only_user",
}
USER_TYPE_REVERSE_MAP: dict[str, int] = {v: k for k, v in USER_TYPE_MAP.items()}

# Credential type mapping (Matter DoorLock CredentialTypeEnum)
_CredentialType = clusters.DoorLock.Enums.CredentialTypeEnum
CREDENTIAL_TYPE_MAP: dict[int, str] = {
    _CredentialType.kProgrammingPIN: "programming_pin",
    _CredentialType.kPin: CRED_TYPE_PIN,
    _CredentialType.kRfid: CRED_TYPE_RFID,
    _CredentialType.kFingerprint: CRED_TYPE_FINGERPRINT,
    _CredentialType.kFingerVein: CRED_TYPE_FINGER_VEIN,
    _CredentialType.kFace: CRED_TYPE_FACE,
    _CredentialType.kAliroCredentialIssuerKey: "aliro_credential_issuer_key",
    _CredentialType.kAliroEvictableEndpointKey: "aliro_evictable_endpoint_key",
    _CredentialType.kAliroNonEvictableEndpointKey: "aliro_non_evictable_endpoint_key",
}

# Credential rule mapping (Matter DoorLock CredentialRuleEnum)
_CredentialRule = clusters.DoorLock.Enums.CredentialRuleEnum
CREDENTIAL_RULE_MAP: dict[int, str] = {
    _CredentialRule.kSingle: "single",
    _CredentialRule.kDual: "dual",
    _CredentialRule.kTri: "tri",
}
CREDENTIAL_RULE_REVERSE_MAP: dict[str, int] = {
    v: k for k, v in CREDENTIAL_RULE_MAP.items()
}

# Reverse mapping for credential types (str -> int)
CREDENTIAL_TYPE_REVERSE_MAP: dict[str, int] = {
    v: k for k, v in CREDENTIAL_TYPE_MAP.items()
}

# Credential types allowed in set/clear services (excludes programming_pin, aliro_*)
SERVICE_CREDENTIAL_TYPES = [
    CRED_TYPE_PIN,
    CRED_TYPE_RFID,
    CRED_TYPE_FINGERPRINT,
    CRED_TYPE_FINGER_VEIN,
    CRED_TYPE_FACE,
]

CONCENTRATION_BECQUERELS_PER_CUBIC_METER: Final = "Bq/m³"

# ISO 4217 numeric currency code to alpha-3 code, for the CommodityPrice cluster
# (which reports the numeric code). Home Assistant's generated currency list
# (homeassistant/generated/currencies.py) only tracks alpha codes, so this is
# kept as a small local table instead of adding a dependency for data that
# rarely changes.
ISO_4217_NUMERIC_TO_ALPHA: dict[int, str] = {
    8: "ALL",
    12: "DZD",
    32: "ARS",
    36: "AUD",
    44: "BSD",
    48: "BHD",
    50: "BDT",
    51: "AMD",
    52: "BBD",
    60: "BMD",
    64: "BTN",
    68: "BOB",
    72: "BWP",
    84: "BZD",
    90: "SBD",
    96: "BND",
    104: "MMK",
    108: "BIF",
    116: "KHR",
    124: "CAD",
    132: "CVE",
    136: "KYD",
    144: "LKR",
    152: "CLP",
    156: "CNY",
    170: "COP",
    174: "KMF",
    188: "CRC",
    192: "CUP",
    203: "CZK",
    208: "DKK",
    214: "DOP",
    222: "SVC",
    230: "ETB",
    232: "ERN",
    238: "FKP",
    242: "FJD",
    262: "DJF",
    270: "GMD",
    292: "GIP",
    320: "GTQ",
    324: "GNF",
    328: "GYD",
    332: "HTG",
    340: "HNL",
    344: "HKD",
    348: "HUF",
    352: "ISK",
    356: "INR",
    360: "IDR",
    364: "IRR",
    368: "IQD",
    376: "ILS",
    388: "JMD",
    392: "JPY",
    396: "XAD",
    398: "KZT",
    400: "JOD",
    404: "KES",
    408: "KPW",
    410: "KRW",
    414: "KWD",
    417: "KGS",
    418: "LAK",
    422: "LBP",
    426: "LSL",
    430: "LRD",
    434: "LYD",
    446: "MOP",
    454: "MWK",
    458: "MYR",
    462: "MVR",
    480: "MUR",
    484: "MXN",
    496: "MNT",
    498: "MDL",
    504: "MAD",
    512: "OMR",
    516: "NAD",
    524: "NPR",
    532: "XCG",
    533: "AWG",
    548: "VUV",
    554: "NZD",
    558: "NIO",
    566: "NGN",
    578: "NOK",
    586: "PKR",
    590: "PAB",
    598: "PGK",
    600: "PYG",
    604: "PEN",
    608: "PHP",
    634: "QAR",
    643: "RUB",
    646: "RWF",
    654: "SHP",
    682: "SAR",
    690: "SCR",
    702: "SGD",
    704: "VND",
    706: "SOS",
    710: "ZAR",  # codespell:ignore zar
    728: "SSP",
    748: "SZL",
    752: "SEK",
    756: "CHF",
    760: "SYP",
    764: "THB",
    776: "TOP",
    780: "TTD",
    784: "AED",
    788: "TND",
    800: "UGX",
    807: "MKD",
    818: "EGP",
    826: "GBP",
    834: "TZS",
    840: "USD",
    858: "UYU",
    860: "UZS",
    882: "WST",
    886: "YER",
    901: "TWD",
    924: "ZWG",
    925: "SLE",
    926: "VED",
    927: "UYW",
    928: "VES",
    929: "MRU",
    930: "STN",
    933: "BYN",
    934: "TMT",
    936: "GHS",
    938: "SDG",
    941: "RSD",
    943: "MZN",
    944: "AZN",
    946: "RON",
    949: "TRY",
    950: "XAF",
    951: "XCD",
    952: "XOF",
    953: "XPF",
    967: "ZMW",
    968: "SRD",
    969: "MGA",
    971: "AFN",
    972: "TJS",
    973: "AOA",
    976: "CDF",
    977: "BAM",
    978: "EUR",
    980: "UAH",
    981: "GEL",
    985: "PLN",
    986: "BRL",
}
