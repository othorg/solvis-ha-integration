"""Constants for the Solvis Heating integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    Platform,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)

DOMAIN = "solvis_remote"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.IMAGE]

CONF_REALM = "realm"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CGI_PROFILES = "cgi_profiles"
CONF_ENABLE_CGI = "enable_cgi_control"

DEFAULT_REALM = "SolvisRemote"
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_TIMEOUT = 10  # seconds
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

# CGI profile validation limits
CGI_WAKEUP_MAX = 10
CGI_DELAY_MIN = 0.1
CGI_DELAY_MAX = 5.0
CGI_COORD_MAX = 800

# CGI timing constants
CGI_SECTION_DELAY = 0.5  # Pause after section touch (seconds)
CGI_TOUCH_DELAY = 0.5    # Pause after option touch (seconds)

# CGI menu sections (SolvisRemote hierarchical menu)
CGI_SECTIONS: dict[str, dict] = {
    "heizung": {"x": 43, "y": 25},
    "wasser": {"x": 47, "y": 77},
    "zirkulation": {"x": 49, "y": 126},
    "solar": {"x": 38, "y": 181},
    "sonstig": {"x": 53, "y": 225},
}

MANUFACTURER = "Solvis"
MODEL = "SolvisMax"

# Device groups
DEVICE_SOLAR = "Solaranlage"
DEVICE_BOILER = "Kessel"
DEVICE_HEATING_CIRCUIT = "Heizkreis 1"
DEVICE_HOT_WATER = "Warmwasser"

# Mapping: CGI section key → device group for entity assignment
SECTION_TO_DEVICE_GROUP: dict[str, str] = {
    "heizung": DEVICE_HEATING_CIRCUIT,
    "wasser": DEVICE_HOT_WATER,
    "zirkulation": DEVICE_HOT_WATER,
    "solar": DEVICE_SOLAR,
    "sonstig": DEVICE_BOILER,
}

# Mapping: target_device dropdown key → device group (empty = derive from section)
TARGET_DEVICE_OPTIONS: dict[str, str] = {
    "auto": "",
    "heating_circuit": DEVICE_HEATING_CIRCUIT,
    "hot_water": DEVICE_HOT_WATER,
    "solar": DEVICE_SOLAR,
    "boiler": DEVICE_BOILER,
}

# ---------------------------------------------------------------------------
# Default CGI command profiles (used as fallback when not yet persisted)
# ---------------------------------------------------------------------------

DEFAULT_CGI_PROFILES: dict[str, dict] = {
    "heating_mode": {
        "name": "Heating Mode",
        "target_device": "heating_circuit",
        "icon": "mdi:radiator",
        "section": "heizung",
        "wakeup_count": 4,
        "wakeup_delay": 1.0,
        "reset_touch": {"x": 510, "y": 510},
        "options": {
            "off": {"label": "Off", "x": 315, "y": 215},
            "auto": {"label": "Auto", "x": 120, "y": 218},
            "day": {"label": "Day", "x": 188, "y": 220},
            "night": {"label": "Night", "x": 253, "y": 215},
        },
    },
}


# ---------------------------------------------------------------------------
# Extended entity descriptions with Solvis-specific fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class SolvisSensorEntityDescription(SensorEntityDescription):
    """Sensor entity description with Solvis sensor key and device group."""

    solvis_key: str
    device_group: str


@dataclass(frozen=True, kw_only=True)
class SolvisBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor entity description with Solvis sensor key and device group."""

    solvis_key: str
    device_group: str


# ---------------------------------------------------------------------------
# Sensor definitions (20 sensors)
# ---------------------------------------------------------------------------

SENSOR_DESCRIPTIONS: tuple[SolvisSensorEntityDescription, ...] = (
    # --- Warmwasser ---
    SolvisSensorEntityDescription(
        key="hot_water_buffer",
        solvis_key="s1",
        device_group=DEVICE_HOT_WATER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="hot_water_buffer",
    ),
    SolvisSensorEntityDescription(
        key="hot_water_temperature",
        solvis_key="s2",
        device_group=DEVICE_HOT_WATER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="hot_water_temperature",
    ),
    SolvisSensorEntityDescription(
        key="circulation_temperature",
        solvis_key="s11",
        device_group=DEVICE_HOT_WATER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="circulation_temperature",
    ),
    SolvisSensorEntityDescription(
        key="flow_rate_hot_water",
        solvis_key="s18",
        device_group=DEVICE_HOT_WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="l/min",
        translation_key="flow_rate_hot_water",
    ),
    # --- Kessel ---
    SolvisSensorEntityDescription(
        key="storage_reference",
        solvis_key="s3",
        device_group=DEVICE_BOILER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="storage_reference",
    ),
    SolvisSensorEntityDescription(
        key="heating_buffer_top",
        solvis_key="s4",
        device_group=DEVICE_BOILER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="heating_buffer_top",
    ),
    SolvisSensorEntityDescription(
        key="heating_buffer_bottom",
        solvis_key="s9",
        device_group=DEVICE_BOILER,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="heating_buffer_bottom",
    ),
    # --- Solaranlage ---
    SolvisSensorEntityDescription(
        key="flow_temperature_solar",
        solvis_key="s5",
        device_group=DEVICE_SOLAR,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="flow_temperature_solar",
    ),
    SolvisSensorEntityDescription(
        key="return_temperature",
        solvis_key="s6",
        device_group=DEVICE_SOLAR,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="return_temperature",
    ),
    SolvisSensorEntityDescription(
        key="collector_temperature",
        solvis_key="s8",
        device_group=DEVICE_SOLAR,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="collector_temperature",
    ),
    SolvisSensorEntityDescription(
        key="collector_transfer",
        solvis_key="s15",
        device_group=DEVICE_SOLAR,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="collector_transfer",
    ),
    SolvisSensorEntityDescription(
        key="flow_rate_solar",
        solvis_key="s17",
        device_group=DEVICE_SOLAR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="l/h",
        translation_key="flow_rate_solar",
    ),
    SolvisSensorEntityDescription(
        key="solar_power",
        solvis_key="slv",
        device_group=DEVICE_SOLAR,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        translation_key="solar_power",
    ),
    SolvisSensorEntityDescription(
        key="solar_yield",
        solvis_key="sev",
        device_group=DEVICE_SOLAR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        translation_key="solar_yield",
    ),
    SolvisSensorEntityDescription(
        key="solar_temperature_delta",
        solvis_key="delta_s5s6",
        device_group=DEVICE_SOLAR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="K",
        translation_key="solar_temperature_delta",
    ),
    # --- Heizkreis 1 ---
    SolvisSensorEntityDescription(
        key="outdoor_temperature",
        solvis_key="s10",
        device_group=DEVICE_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="outdoor_temperature",
    ),
    SolvisSensorEntityDescription(
        key="flow_temperature_heating",
        solvis_key="s12",
        device_group=DEVICE_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="flow_temperature_heating",
    ),
    SolvisSensorEntityDescription(
        key="room_temperature",
        solvis_key="rf1",
        device_group=DEVICE_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        translation_key="room_temperature",
    ),
    SolvisSensorEntityDescription(
        key="burner_modulation",
        solvis_key="ao1",
        device_group=DEVICE_HEATING_CIRCUIT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        translation_key="burner_modulation",
    ),
    SolvisSensorEntityDescription(
        key="burner_power",
        solvis_key="brennerleistung",
        device_group=DEVICE_HEATING_CIRCUIT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        translation_key="burner_power",
    ),
)


# ---------------------------------------------------------------------------
# Binary sensor definitions (5 binary sensors)
# ---------------------------------------------------------------------------

BINARY_SENSOR_DESCRIPTIONS: tuple[SolvisBinarySensorEntityDescription, ...] = (
    SolvisBinarySensorEntityDescription(
        key="solar_pump",
        solvis_key="a1",
        device_group=DEVICE_SOLAR,
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:pump",
        translation_key="solar_pump",
    ),
    SolvisBinarySensorEntityDescription(
        key="hot_water_pump",
        solvis_key="a2",
        device_group=DEVICE_HOT_WATER,
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:pump",
        translation_key="hot_water_pump",
    ),
    SolvisBinarySensorEntityDescription(
        key="heating_circuit_pump",
        solvis_key="a3",
        device_group=DEVICE_HEATING_CIRCUIT,
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:pump",
        translation_key="heating_circuit_pump",
    ),
    SolvisBinarySensorEntityDescription(
        key="circulation_pump",
        solvis_key="a5",
        device_group=DEVICE_HOT_WATER,
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:pump",
        translation_key="circulation_pump",
    ),
    SolvisBinarySensorEntityDescription(
        key="burner",
        solvis_key="a12",
        device_group=DEVICE_HEATING_CIRCUIT,
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:fire",
        translation_key="burner",
    ),
)


# ---------------------------------------------------------------------------
# Anlagenschema image overlay definitions
# Positions are relative (0.0–1.0), scaled to image size at render time
# ---------------------------------------------------------------------------

ANLAGENSCHEMA_FONT_SIZE = 14

ANLAGENSCHEMA_OVERLAYS: tuple[dict, ...] = (
    {"key": "s10", "rel_pos": (0.495, 0.100), "format": "{v}°C", "label": "S10"},
    {"key": "s1",  "rel_pos": (0.558, 0.227), "format": "{v}°C", "label": "S1"},
    {"key": "s4",  "rel_pos": (0.558, 0.391), "format": "{v}°C", "label": "S4"},
    {"key": "s9",  "rel_pos": (0.558, 0.536), "format": "{v}°C", "label": "S9"},
    {"key": "s3",  "rel_pos": (0.558, 0.936), "format": "{v}°C", "label": "S3"},
    {"key": "slv", "rel_pos": (0.192, 0.689), "format": "{v}kW", "label": "SL"},
    {"key": "sev", "rel_pos": (0.192, 0.729), "format": "{v}kWh", "label": "SE"},
    {"key": "s17", "rel_pos": (0.192, 0.769), "format": "{v}l/h", "label": "S17"},
    {"key": "s8",  "rel_pos": (0.192, 0.809), "format": "{v}°C", "label": "S8"},
    {"key": "s2",  "rel_pos": (0.742, 0.536), "format": "{v}°C", "label": "S2"},
    {"key": "s11", "rel_pos": (0.742, 0.622), "format": "{v}°C", "label": "S11"},
    {"key": "s12", "rel_pos": (0.742, 0.787), "format": "{v}°C", "label": "S12"},
)

ANLAGENSCHEMA_STATUS_OVERLAY: dict = {
    "key": "a12",
    "rel_pos": (0.389, 0.445),
    "text": "Nachheizung",
    "color_on": (220, 40, 40),
    "color_off": (160, 160, 160),
}
