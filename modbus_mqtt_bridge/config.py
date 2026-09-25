"""Configuration models — loaded from YAML via Pydantic."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class RegisterConfig(BaseModel):
    name: str
    address: int
    type: Literal[
        "uint16", "int16", "uint32", "int32",
        "float32", "float64", "bool", "coil",
    ] = "uint16"
    function_code: Literal[1, 2, 3, 4] = Field(
        3,
        description="1=coils, 2=discrete inputs, 3=holding registers (default), 4=input registers",
    )
    multiplier: float = 1.0
    unit: Optional[str] = None


class DeviceConfig(BaseModel):
    name: str

    # TCP connection (host required for TCP)
    host: Optional[str] = None
    port: int = 502

    # RTU connection (serial port path, e.g. /dev/ttyUSB0 or COM3)
    serial_port: Optional[str] = None
    baudrate: int = 9600
    parity: Literal["N", "E", "O"] = "N"
    stopbits: int = 1
    bytesize: int = 8

    unit_id: int = Field(1, ge=1, le=247)
    poll_interval: float = Field(5.0, description="Poll interval in seconds", ge=0.5)
    timeout: float = Field(3.0, description="Modbus request timeout in seconds")
    reconnect_delay: float = Field(5.0, description="Initial delay between reconnect attempts in seconds", ge=1.0)
    max_reconnect_delay: float = Field(60.0, description="Maximum reconnect delay (exponential backoff cap) in seconds", ge=1.0)
    byte_order: Literal["big", "little"] = "big"
    word_order: Literal["big", "little"] = "big"

    registers: List[RegisterConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        return v.strip().replace(" ", "_")

    @property
    def is_rtu(self) -> bool:
        return self.serial_port is not None


class MqttConfig(BaseModel):
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    client_id: str = "modbus-mqtt-bridge"
    topic_prefix: str = "modbus"
    keepalive: int = 60
    qos: Literal[0, 1, 2] = 1
    retain: bool = False

    # Publish all registers as one JSON object per device instead of one topic per register
    batch_publish: bool = False


class BridgeConfig(BaseModel):
    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    devices: List[DeviceConfig] = Field(default_factory=list)
