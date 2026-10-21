# Solvis Heating — Home Assistant Integration

Custom Home Assistant integration for Solvis heating devices.

[Solvis GmbH](https://www.solvis.de/) is a German manufacturer of innovative and energy-efficient heating systems. The company develops hybrid heating solutions, solar panels, and heat pumps that can be flexibly combined.

This integration connects to the **SolvisRemote** web interface via HTTP Digest Auth and reads sensor data directly from the controller — no Modbus required.

## Supported Devices

This integration supports **SolvisControl 2 (SC2)** devices with a **SolvisRemote** module.

The SolvisRemote module provides a local web interface that exposes the controller's sensor data as an XML/hex payload. This integration reads that payload via HTTP Digest Auth, decodes the hex values, and creates Home Assistant sensor entities. All communication is **read-only** and **local** — no cloud connection is needed.

### How It Works

```
SolvisMax (SC2) ──► SolvisRemote Module ──► Local Web Interface (HTTP)
                                                     │
                                            HTTP Digest Auth
                                                     │
                                            Home Assistant ◄── This Integration
```

1. The SolvisRemote module exposes sensor data at its local IP address
2. This integration polls the XML endpoint at a configurable interval (default: 60s)
3. The hex payload is decoded into temperature values, flow rates, pump states, etc.
4. Derived values (solar temperature delta, burner power) are computed automatically

### Compatibility

| Device | Status | Notes |
|--------|--------|-------|
| SolvisControl 2 (SC2) + SolvisRemote | Supported | Requires SolvisRemote module with web interface enabled |
| SolvisControl 3 (SC3) | Not tested | SC3 uses a different interface; this integration is designed for the SolvisRemote HTTP protocol |
| Older controllers (SC1) | Not compatible | No SolvisRemote support |

### Supported Firmware (SC2 / SolvisRemote)

Some features may depend on the firmware version of the SolvisRemote module. The following versions are confirmed to work:

| Version | Status |
|---------|--------|
| MA205 and later | Supported |

If you have information about the compatibility of an unlisted version, or encounter issues with a listed version, feedback is welcome via [GitHub Issues](https://github.com/othorg/solvis-ha-integration/issues).

## Features

- **20 sensors**: temperatures, flow rates, solar power/yield, burner modulation, computed values
- **5 binary sensors**: pump states, burner state
- **4 device groups**: Solaranlage, Kessel, Heizkreis 1, Warmwasser
- **Config Flow** with connection validation
- **Reauth Flow** — automatic re-authentication prompt on credential failure
- **Options Flow** — change connection parameters (host, credentials) and scan interval at runtime
- **Diagnostics** — downloadable debug data with redacted credentials
- **CGI control** (optional) — select entities that switch settings by touching the display, e.g. the heating mode
- **Remote display** — the controller display as a camera entity, plus admin services to touch it and press its two buttons (see below)
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

### Initial Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Solvis Heating"
3. Enter:
   - **Host**: IP address of your SolvisRemote module (e.g. `192.168.1.100`)
   - **Username** / **Password**: Digest Auth credentials (as configured on the SolvisRemote)
   - **Realm**: `SolvisRemote` (default, usually unchanged)
   - **Scan interval**: polling interval in seconds (default: 60, range: 10–600)

### Reconfiguration

All parameters (host, credentials, realm, scan interval) can be changed at any time via **Settings** → **Devices & Services** → **Solvis Heating** → **Configure**. The connection is validated before changes are applied.

## Sensors

| Sensor | Key | Unit | Device |
|--------|-----|------|--------|
| Hot water buffer | S1 | °C | Warmwasser |
| Hot water temperature | S2 | °C | Warmwasser |
| Circulation temperature | S11 | °C | Warmwasser |
| Flow rate hot water | S18 | l/min | Warmwasser |
| Storage reference | S3 | °C | Kessel |
| Heating buffer top | S4 | °C | Kessel |
| Heating buffer bottom | S9 | °C | Kessel |
| Flow temperature solar | S5 | °C | Solaranlage |
| Return temperature | S6 | °C | Solaranlage |
| Collector temperature | S8 | °C | Solaranlage |
| Collector transfer | S15 | °C | Solaranlage |
| Flow rate solar | S17 | l/h | Solaranlage |
| Solar power | SLV | kW | Solaranlage |
| Solar yield | SEV | kWh | Solaranlage |
| Solar temperature delta | S5−S6 | K | Solaranlage |
| Outdoor temperature | S10 | °C | Heizkreis 1 |
| Flow temperature heating | S12 | °C | Heizkreis 1 |
| Room temperature | RF1 | °C | Heizkreis 1 |
| Burner modulation | AO1 | % | Heizkreis 1 |
| Burner power | computed | kW | Heizkreis 1 |

### Binary Sensors

| Sensor | Key | Device |
|--------|-----|--------|
| Solar pump | A1 | Solaranlage |
| Hot water pump | A2 | Warmwasser |
| Heating circuit pump | A3 | Heizkreis 1 |
| Circulation pump | A5 | Warmwasser |
| Burner | A12 | Heizkreis 1 |

### Computed Values

- **Solar temperature delta** = Flow temperature solar (S5) − Return temperature (S6)
- **Burner power** = 5.0 + Burner modulation (AO1) × 15.0 / 100.0 kW (when burner is on; 0 when off)

## Remote Display

Mirrors the controller's own remote page (`remote.html` on the SolvisRemote):

- **Camera `Display`**: the current display (`display.bmp`, 240x128) as JPEG at double size (480x256), as still image or Motion JPEG stream. It is only fetched while someone looks; viewers share one fetch.
- **Services** (admin only, require *CGI control* in the options; target the display camera):
  - `solvis_remote.touch` — tap at `x`/`y`, hold for `duration` (0.5–10 s), release
  - `solvis_remote.touch_down` / `solvis_remote.touch_up` — press and hold until released; a held touch is released automatically after 10 s
  - `solvis_remote.press_button` — the buttons next to the display, `links` or `rechts`

Coordinates are those of the display shown at double size (0–479 × 0–255), as the native page sends them. Like there, a touch is released at least 500 ms after the press, and a sleeping display swallows the first touch. While a touch is held, no other command (e.g. a CGI select) runs.

The interactive card is part of the [Solvis Lovelace card](https://github.com/othorg/solvis-home-assistant-lovelace-card) (`custom:solvis-remote-card`).

## Known Limitations

- **Control by touch**: Settings are changed by touching the display (CGI), not through a documented API. The touch positions depend on the controller's screens and firmware.
- **SC2/SolvisRemote only**: Designed for the SolvisRemote HTTP protocol. SC3 and Modbus-based setups are not supported by this integration.
- **Entity names**: Due to the wide range of Solvis configuration options, some entity names may be inaccurate for less common setups (e.g. district heating, external boilers, swimming pool circuits, east/west solar configurations). If you encounter such cases, feedback with a description of your system is welcome via [GitHub Issues](https://github.com/othorg/solvis-ha-integration/issues).

## Requirements

- SolvisMax with SolvisControl 2 (SC2)
- SolvisRemote module with web interface enabled
- HTTP Digest Auth credentials configured on the SolvisRemote
- Network access from Home Assistant to the SolvisRemote module

## Releasing

HACS installs this integration from GitHub releases. To publish one:

1. Bump `version` in `custom_components/solvis_remote/manifest.json`.
2. Commit that and push it to `main`; wait for CI to pass.
3. Tag the same commit and push the tag:

   ```bash
   git tag v1.2.3 && git push origin v1.2.3
   ```

The `Release` workflow refuses a tag whose version does not match the
manifest, then creates the GitHub release with generated notes. In Home
Assistant, HACS picks the new release up after *Update information* on the
integration; a restart is required because custom component code is only
loaded at startup.

## License

MIT — see [LICENSE](LICENSE).
