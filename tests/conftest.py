"""Shared fixtures: an in-process Modbus TCP server acting as a field device."""

from __future__ import annotations

import asyncio
import socket
import struct
from typing import AsyncIterator, Awaitable, Callable, Dict, List

import pytest
from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import ModbusTcpServer

UNIT_ID = 1
_SIZE = 100

RegisterMap = Dict[int, list]  # start address -> consecutive values


def float32_words(value: float) -> List[int]:
    """IEEE-754 float32 as two big-endian 16-bit registers."""
    high, low = struct.unpack(">HH", struct.pack(">f", value))
    return [high, low]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _block(values: RegisterMap, fill) -> ModbusSequentialDataBlock:
    data = [fill] * _SIZE
    for start, seq in values.items():
        data[start:start + len(seq)] = seq
    # pymodbus maps protocol address N to block index N+1, so the block starts at 1.
    return ModbusSequentialDataBlock(1, data)


async def _wait_until_listening(port: int) -> None:
    for _ in range(50):
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError(f"fake Modbus device did not start on port {port}")


StartDevice = Callable[..., Awaitable[int]]


@pytest.fixture
async def fake_device() -> AsyncIterator[StartDevice]:
    """Start a fake device with the given register values; returns its TCP port."""
    servers = []

    async def start(
        holding: RegisterMap | None = None,
        input: RegisterMap | None = None,
        coils: RegisterMap | None = None,
        discrete: RegisterMap | None = None,
    ) -> int:
        device = ModbusDeviceContext(
            hr=_block(holding or {}, 0),
            ir=_block(input or {}, 0),
            co=_block(coils or {}, False),
            di=_block(discrete or {}, False),
        )
        port = _free_port()
        server = ModbusTcpServer(
            ModbusServerContext(devices={UNIT_ID: device}, single=False),
            address=("127.0.0.1", port),
        )
        task = asyncio.create_task(server.serve_forever())
        servers.append((server, task))
        await _wait_until_listening(port)
        return port

    yield start

    for server, task in servers:
        await server.shutdown()
        task.cancel()
