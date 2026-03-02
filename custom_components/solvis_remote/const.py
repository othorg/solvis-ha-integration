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
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONF_REALM = "realm"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_REALM = "SolvisRemote"
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_TIMEOUT = 10  # seconds
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

MANUFACTURER = "Solvis"
MODEL = "SolvisMax"

# Device groups
DEVICE_SOLAR = "Solaranlage"
DEVICE_BOILER = "Kessel"
DEVICE_HEATING_CIRCUIT = "Heizkreis 1"
DEVICE_HOT_WATER = "Warmwasser"


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
