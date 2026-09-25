"""Async Modbus reader — TCP and RTU."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException

from .config import DeviceConfig, RegisterConfig

logger = logging.getLogger(__name__)

_FC_COIL = 1
_FC_DISCRETE = 2
_FC_HOLDING = 3
_FC_INPUT = 4


class ModbusReader:
    """Manages a single Modbus device connection and reads its registers."""

    def __init__(self, device: DeviceConfig) -> None:
        self._cfg = device
        self._client: Optional[Any] = None

    # ── connection ──────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        try:
            if self._cfg.is_rtu:
                self._client = AsyncModbusSerialClient(
                    port=self._cfg.serial_port,
                    baudrate=self._cfg.baudrate,
                    parity=self._cfg.parity,
                    stopbits=self._cfg.stopbits,
                    bytesize=self._cfg.bytesize,
                    timeout=self._cfg.timeout,
                )
            else:
                self._client = AsyncModbusTcpClient(
                    host=self._cfg.host,
                    port=self._cfg.port,
                    timeout=self._cfg.timeout,
                )
            await self._client.connect()
            if not self._client.connected:
                logger.warning("[%s] connection failed", self._cfg.name)
                return False
            _ensure_datatype_map(self._client)
            logger.info("[%s] connected", self._cfg.name)
            return True
        except Exception as exc:
            logger.error("[%s] connect error: %s", self._cfg.name, exc)
            return False

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    @property
    def connected(self) -> bool:
        return bool(self._client and self._client.connected)

    # ── reading ──────────────────────────────────────────────────────────────

    async def read_all(self) -> Dict[str, Any]:
        """Poll every configured register. Returns {name: value} (skips failed reads)."""
        if not self.connected:
            return {}

        results: Dict[str, Any] = {}
        for reg in self._cfg.registers:
            try:
                value = await self._read_register(reg)
                if value is not None:
                    results[reg.name] = value
            except Exception as exc:
                logger.debug("[%s] register %s error: %s", self._cfg.name, reg.name, exc)
        return results

    async def _read_register(self, reg: RegisterConfig) -> Optional[Any]:
        fc = reg.function_code
        count = _register_count(reg.type)

        try:
            if fc == _FC_COIL:
                raw = await self._client.read_coils(reg.address, count=count, slave=self._cfg.unit_id)
            elif fc == _FC_DISCRETE:
                raw = await self._client.read_discrete_inputs(reg.address, count=count, slave=self._cfg.unit_id)
            elif fc == _FC_HOLDING:
                raw = await self._client.read_holding_registers(reg.address, count=count, slave=self._cfg.unit_id)
            else:
                raw = await self._client.read_input_registers(reg.address, count=count, slave=self._cfg.unit_id)
        except (ConnectionException, ModbusException) as exc:
            logger.warning("[%s] read error addr=%d: %s", self._cfg.name, reg.address, exc)
            return None

        if raw.isError():
            logger.debug("[%s] Modbus error response addr=%d", self._cfg.name, reg.address)
            return None

        return self._decode(raw, reg, fc)

    def _decode(self, raw: Any, reg: RegisterConfig, fc: int) -> Optional[Any]:
        # Coils / discrete inputs → bool
        if fc in (_FC_COIL, _FC_DISCRETE):
            bits = list(raw.bits or [])
            if not bits:
                return None
            return bool(bits[0])

        if reg.type == "coil":
            return bool(raw.bits[0]) if raw.bits else None

        # Registers → numeric types via pymodbus convert_from_registers
        datatype = _DATATYPE_MAP.get(reg.type)
        if datatype is None:
            logger.warning("[%s] unknown type %r for register %s", self._cfg.name, reg.type, reg.name)
            return None

        word_order = "big" if self._cfg.word_order == "big" else "little"

        try:
            value = self._client.convert_from_registers(
                raw.registers, data_type=datatype, word_order=word_order
            )
        except Exception as exc:
            logger.debug("[%s] decode error %s: %s", self._cfg.name, reg.name, exc)
            return None

        if reg.type == "bool":
            return bool(value)

        if reg.multiplier != 1.0:
            value *= reg.multiplier

        return value


# ── helpers ──────────────────────────────────────────────────────────────────

def _register_count(data_type: str) -> int:
    return {"float64": 4, "uint32": 2, "int32": 2, "float32": 2}.get(data_type, 1)


def _build_datatype_map(client_cls: type) -> Dict[str, Any]:
    dt = client_cls.DATATYPE
    return {
        "uint16":  dt.UINT16,
        "int16":   dt.INT16,
        "uint32":  dt.UINT32,
        "int32":   dt.INT32,
        "float32": dt.FLOAT32,
        "float64": dt.FLOAT64,
        "bool":    dt.UINT16,
    }


# Lazy-init so importing this module before pymodbus is available doesn't crash.
_DATATYPE_MAP: Dict[str, Any] = {}


def _ensure_datatype_map(client: Any) -> None:
    global _DATATYPE_MAP
    if not _DATATYPE_MAP:
        _DATATYPE_MAP = _build_datatype_map(type(client))
