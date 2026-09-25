# modbus-mqtt-bridge

> **Read any Modbus TCP or RTU device and publish its registers to an MQTT broker — configured with a single YAML file.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![pymodbus](https://img.shields.io/badge/pymodbus-3.x-orange)](https://github.com/pymodbus-dev/pymodbus)
[![MQTT](https://img.shields.io/badge/MQTT-aiomqtt-9cf)](https://github.com/empicano/aiomqtt)

Connect PLCs, inverters, energy meters and other Modbus devices to any MQTT broker — Home Assistant, ThingsBoard, Node-RED, EMQX, or a plain Mosquitto instance.

```
Modbus TCP/RTU Device  →  modbus-mqtt-bridge  →  MQTT Broker  →  Your App
       PLC                   (this tool)           Mosquitto       Dashboard
     Inverter                                       EMQX            Node-RED
  Energy Meter                                   ThingsBoard    Home Assistant
```

## Features

- **Modbus TCP** and **Modbus RTU** (RS-485 serial) support
- Multiple devices polled concurrently with configurable intervals
- All common register types: `uint16`, `int16`, `uint32`, `int32`, `float32`, `float64`, `bool`, coils
- Multiplier / scale factor per register
- Per-register or batched JSON publishing
- Auto-reconnect on both Modbus and MQTT connection loss
- Docker-ready

## Quick Start

```bash
pip install modbus-mqtt-bridge
cp config.example.yaml config.yaml
# edit config.yaml for your devices
modbus-mqtt-bridge -c config.yaml
```

Or with Docker:

```bash
docker run -v $(pwd)/config.yaml:/config/config.yaml ekicimustafa/modbus-mqtt-bridge
```

## Configuration

```yaml
mqtt:
  host: localhost
  port: 1883
  topic_prefix: modbus      # topics: modbus/{device}/{register}

devices:
  - name: inverter_1
    host: 192.168.1.10      # TCP
    port: 502
    unit_id: 1
    poll_interval: 5        # seconds
    registers:
      - name: ac_power_w
        address: 0
        type: float32
        function_code: 4    # 3=holding, 4=input, 1=coils, 2=discrete
        unit: W
      - name: daily_energy_kwh
        address: 6
        type: float32
        function_code: 4
        multiplier: 0.1
        unit: kWh

  - name: energy_meter
    serial_port: /dev/ttyUSB0    # RTU
    baudrate: 9600
    unit_id: 2
    poll_interval: 10
    registers:
      - name: active_power_kw
        address: 0
        type: float32
        function_code: 4
        unit: kW
```

See [`config.example.yaml`](config.example.yaml) for a full example with TCP, RTU and PLC configurations.

## MQTT Payload

Each register is published to `{topic_prefix}/{device_name}/{register_name}`:

```json
{
  "device": "inverter_1",
  "register": "ac_power_w",
  "value": 3450.5,
  "unit": "W",
  "timestamp": "2026-09-25T12:00:00+00:00"
}
```

Set `batch_publish: true` in the MQTT config to publish all registers for a device under one topic:

```json
{
  "device": "inverter_1",
  "timestamp": "2026-09-25T12:00:00+00:00",
  "values": {
    "ac_power_w": {"value": 3450.5, "unit": "W"},
    "daily_energy_kwh": {"value": 12.3, "unit": "kWh"}
  }
}
```

## Register Types

| Type | Registers | Description |
|---|---|---|
| `uint16` | 1 | Unsigned 16-bit integer |
| `int16` | 1 | Signed 16-bit integer |
| `uint32` | 2 | Unsigned 32-bit integer |
| `int32` | 2 | Signed 32-bit integer |
| `float32` | 2 | IEEE 754 single-precision float (most common) |
| `float64` | 4 | IEEE 754 double-precision float |
| `bool` | 1 | Register read as uint16, cast to bool |
| `coil` | — | Modbus coil (FC1) or discrete input (FC2) |

## Function Codes

| Code | Type |
|---|---|
| `1` | Read Coils |
| `2` | Read Discrete Inputs |
| `3` | Read Holding Registers |
| `4` | Read Input Registers |

## Integration Examples

### Home Assistant (MQTT sensor)
```yaml
sensor:
  - platform: mqtt
    name: "Inverter Power"
    state_topic: "modbus/inverter_1/ac_power_w"
    value_template: "{{ value_json.value }}"
    unit_of_measurement: "W"
```

### Node-RED
Subscribe to `modbus/#` and process the JSON payload.

### ThingsBoard
Use the ThingsBoard MQTT gateway plugin pointed at your broker, or set `topic_prefix` to match the ThingsBoard telemetry topic format: `v1/devices/me/telemetry`.

## CLI Reference

```
Usage: modbus-mqtt-bridge [OPTIONS]

  Read Modbus TCP/RTU devices and publish readings to an MQTT broker.

Options:
  -c, --config PATH                 Path to YAML configuration file. [default: config.yaml]
  --log-level [DEBUG|INFO|WARNING|ERROR]
                                    [default: INFO]
  --help                            Show this message and exit.
```

## License

MIT — see [LICENSE](LICENSE).
