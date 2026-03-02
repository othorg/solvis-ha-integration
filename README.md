# Solvis Heating — Home Assistant Integration

Custom integration for [Home Assistant](https://www.home-assistant.io/) that connects to Solvis heating controllers (SolvisMax) via the local web interface.

## Features

- **20 sensors**: temperatures, flow rates, solar power/yield, burner modulation, computed values
- **5 binary sensors**: pump states, burner state
- **4 device groups**: Solaranlage, Kessel, Heizkreis 1, Warmwasser
- **Config Flow** with connection validation
- **Reauth Flow** — automatic re-authentication prompt on credential failure
- **Options Flow** — adjust scan interval at runtime (10–600s)
- **Diagnostics** — downloadable debug data with redacted credentials
- **Translations**: English and German

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **Custom repositories**
3. Add `https://github.com/othorg/solvis-ha-integration` as **Integration**
4. Search for "Solvis Heating" and install
5. Restart Home Assistant

### Manual

Copy `custom_components/solvis_remote/` to your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Solvis Heating"
3. Enter:
   - **Host**: IP address of your Solvis controller
   - **Username** / **Password**: Digest Auth credentials
   - **Realm**: `SolvisRemote` (default, usually unchanged)
   - **Scan interval**: polling interval in seconds (default: 60)

## Sensors

| Sensor | Unit | Device |
|--------|------|--------|
| Hot water buffer (S1) | °C | Warmwasser |
| Hot water temperature (S2) | °C | Warmwasser |
| Circulation temperature (S11) | °C | Warmwasser |
| Flow rate hot water (S18) | l/min | Warmwasser |
| Storage reference (S3) | °C | Kessel |
| Heating buffer top (S4) | °C | Kessel |
| Heating buffer bottom (S9) | °C | Kessel |
| Flow temperature solar (S5) | °C | Solaranlage |
| Return temperature (S6) | °C | Solaranlage |
| Collector temperature (S8) | °C | Solaranlage |
| Collector transfer (S15) | °C | Solaranlage |
| Flow rate solar (S17) | l/h | Solaranlage |
| Solar power | kW | Solaranlage |
| Solar yield | kWh | Solaranlage |
| Solar temperature delta | K | Solaranlage |
| Outdoor temperature (S10) | °C | Heizkreis 1 |
| Flow temperature heating (S12) | °C | Heizkreis 1 |
| Room temperature (RF1) | °C | Heizkreis 1 |
| Burner modulation | % | Heizkreis 1 |
| Burner power | kW | Heizkreis 1 |

### Binary Sensors

| Sensor | Device |
|--------|--------|
| Solar pump (A1) | Solaranlage |
| Hot water pump (A2) | Warmwasser |
| Heating circuit pump (A3) | Heizkreis 1 |
| Circulation pump (A5) | Warmwasser |
| Burner (A12) | Heizkreis 1 |

## Requirements

- Solvis controller with web interface (tested with SolvisMax)
- HTTP Digest Auth enabled on the controller
- Network access from Home Assistant to the controller

## License

MIT — see [LICENSE](LICENSE).
