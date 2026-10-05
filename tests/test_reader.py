"""ModbusReader against a real (in-process) Modbus TCP server."""

from __future__ import annotations

import pytest

from modbus_mqtt_bridge.config import DeviceConfig
from modbus_mqtt_bridge.reader import ModbusReader

from .conftest import UNIT_ID, float32_words


def make_device(port: int, registers: list, **kwargs) -> DeviceConfig:
    return DeviceConfig(
        name="test_device",
        host="127.0.0.1",
        port=port,
        unit_id=UNIT_ID,
        timeout=1,
        registers=registers,
        **kwargs,
    )


async def read(device: DeviceConfig) -> dict:
    reader = ModbusReader(device)
    assert await reader.connect(), "reader should connect to the fake device"
    try:
        return await reader.read_all()
    finally:
        await reader.close()


async def test_reads_every_register_type(fake_device):
    port = await fake_device(
        holding={
            0: [1234],                  # uint16
            1: [0xFFFB],                # int16 -5
            2: float32_words(230.5),    # float32
            4: [0x0001, 0x1170],        # uint32 70000
        },
        input={0: [1000]},              # uint16 × 0.1
        coils={0: [True]},
        discrete={0: [True]},
    )

    values = await read(make_device(port, [
        {"name": "count", "address": 0, "type": "uint16"},
        {"name": "offset", "address": 1, "type": "int16"},
        {"name": "voltage", "address": 2, "type": "float32"},
        {"name": "energy", "address": 4, "type": "uint32"},
        {"name": "level_pct", "address": 0, "type": "uint16", "function_code": 4, "multiplier": 0.1},
        {"name": "pump_running", "address": 0, "type": "bool", "function_code": 1},
        {"name": "door_closed", "address": 0, "type": "bool", "function_code": 2},
    ]))

    assert values == {
        "count": 1234,
        "offset": -5,
        "voltage": pytest.approx(230.5),
        "energy": 70000,
        "level_pct": pytest.approx(100.0),
        "pump_running": True,
        "door_closed": True,
    }


async def test_word_order_little_swaps_registers(fake_device):
    high, low = float32_words(50.0)
    port = await fake_device(holding={0: [low, high]})

    values = await read(make_device(
        port,
        [{"name": "frequency", "address": 0, "type": "float32"}],
        word_order="little",
    ))

    assert values == {"frequency": pytest.approx(50.0)}


def swap_bytes(word: int) -> int:
    return ((word & 0xFF) << 8) | (word >> 8)


async def test_byte_order_little_swaps_bytes_in_each_register(fake_device):
    port = await fake_device(holding={
        0: [swap_bytes(w) for w in float32_words(50.0)],
        2: [swap_bytes(1234)],
    })

    values = await read(make_device(
        port,
        [
            {"name": "frequency", "address": 0, "type": "float32"},
            {"name": "count", "address": 2, "type": "uint16"},
        ],
        byte_order="little",
    ))

    assert values == {"frequency": pytest.approx(50.0), "count": 1234}


async def test_byte_and_word_order_little_together(fake_device):
    high, low = float32_words(-12.25)
    port = await fake_device(holding={0: [swap_bytes(low), swap_bytes(high)]})

    values = await read(make_device(
        port,
        [{"name": "temperature", "address": 0, "type": "float32"}],
        byte_order="little",
        word_order="little",
    ))

    assert values == {"temperature": pytest.approx(-12.25)}


async def test_unreachable_device_does_not_connect():
    reader = ModbusReader(make_device(1, [{"name": "x", "address": 0}]))
    assert not await reader.connect()
    assert await reader.read_all() == {}
