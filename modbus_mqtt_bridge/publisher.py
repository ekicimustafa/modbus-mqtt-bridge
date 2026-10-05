"""Async MQTT publisher using aiomqtt, with automatic reconnect."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiomqtt

from .config import DeviceConfig, MqttConfig, RegisterConfig

logger = logging.getLogger(__name__)


class MqttPublisher:
    """Wraps an aiomqtt client and publishes Modbus readings.

    The broker connection is (re)established on demand: if the broker is down
    at startup or drops later, publishing reconnects with exponential back-off
    instead of failing for the rest of the process lifetime. Readings polled
    while the broker is unreachable are dropped, not queued.
    """

    def __init__(self, cfg: MqttConfig) -> None:
        self._cfg = cfg
        self._client: Optional[aiomqtt.Client] = None
        self._lock = asyncio.Lock()
        self._delay = cfg.reconnect_delay
        self._next_attempt = 0.0

    async def __aenter__(self) -> "MqttPublisher":
        await self._ensure_connected()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._disconnect()

    async def publish_readings(
        self,
        device: DeviceConfig,
        readings: Dict[str, Any],
    ) -> None:
        if not readings:
            return

        ts = datetime.now(timezone.utc).isoformat()
        reg_map: Dict[str, RegisterConfig] = {r.name: r for r in device.registers}

        if self._cfg.batch_publish:
            # Single topic with all values as one JSON object
            topic = f"{self._cfg.topic_prefix}/{device.name}"
            payload = {
                "device": device.name,
                "timestamp": ts,
                "values": {
                    name: {
                        "value": value,
                        **({"unit": reg_map[name].unit} if reg_map.get(name) and reg_map[name].unit else {}),
                    }
                    for name, value in readings.items()
                },
            }
            await self._publish(topic, payload)
        else:
            # One topic per register: {prefix}/{device}/{register}
            for name, value in readings.items():
                reg = reg_map.get(name)
                topic = f"{self._cfg.topic_prefix}/{device.name}/{name}"
                payload = {
                    "device": device.name,
                    "register": name,
                    "value": value,
                    "timestamp": ts,
                    **({"unit": reg.unit} if reg and reg.unit else {}),
                }
                if not await self._publish(topic, payload):
                    break  # broker unreachable: skip the rest of this poll cycle

    async def _publish(self, topic: str, payload: Dict[str, Any]) -> bool:
        if not await self._ensure_connected():
            return False
        try:
            await self._client.publish(
                topic,
                payload=json.dumps(payload),
                qos=self._cfg.qos,
                retain=self._cfg.retain,
            )
            logger.debug("Published → %s", topic)
            return True
        except aiomqtt.MqttError as exc:
            logger.warning("MQTT publish failed (%s): %s — reconnecting", topic, exc)
            await self._disconnect()
            return False

    async def _ensure_connected(self) -> bool:
        """Connect if needed. Never blocks longer than one connect attempt."""
        async with self._lock:
            if self._client is not None:
                return True

            loop = asyncio.get_running_loop()
            if loop.time() < self._next_attempt:
                return False  # still backing off; drop this reading

            client = aiomqtt.Client(
                hostname=self._cfg.host,
                port=self._cfg.port,
                username=self._cfg.username,
                password=self._cfg.password,
                identifier=self._cfg.client_id,
                keepalive=self._cfg.keepalive,
            )
            try:
                await client.__aenter__()
            except aiomqtt.MqttError as exc:
                logger.warning(
                    "MQTT connect to %s:%d failed: %s — retrying in %.0fs",
                    self._cfg.host, self._cfg.port, exc, self._delay,
                )
                self._next_attempt = loop.time() + self._delay
                self._delay = min(self._delay * 2, self._cfg.max_reconnect_delay)
                return False

            self._client = client
            self._delay = self._cfg.reconnect_delay
            self._next_attempt = 0.0
            logger.info("MQTT connected to %s:%d", self._cfg.host, self._cfg.port)
            return True

    async def _disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.__aexit__(None, None, None)
        except aiomqtt.MqttError:
            pass  # connection already gone
