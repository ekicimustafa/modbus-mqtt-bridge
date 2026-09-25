"""Async MQTT publisher using aiomqtt."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiomqtt

from .config import DeviceConfig, MqttConfig, RegisterConfig

logger = logging.getLogger(__name__)


class MqttPublisher:
    """Wraps an aiomqtt client and publishes Modbus readings."""

    def __init__(self, cfg: MqttConfig) -> None:
        self._cfg = cfg
        self._client: Optional[aiomqtt.Client] = None

    async def __aenter__(self) -> "MqttPublisher":
        self._client = aiomqtt.Client(
            hostname=self._cfg.host,
            port=self._cfg.port,
            username=self._cfg.username,
            password=self._cfg.password,
            identifier=self._cfg.client_id,
            keepalive=self._cfg.keepalive,
        )
        await self._client.__aenter__()
        logger.info("MQTT connected to %s:%d", self._cfg.host, self._cfg.port)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.__aexit__(*args)
            self._client = None

    async def publish_readings(
        self,
        device: DeviceConfig,
        readings: Dict[str, Any],
    ) -> None:
        if not readings or not self._client:
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
                await self._publish(topic, payload)

    async def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        try:
            await self._client.publish(
                topic,
                payload=json.dumps(payload),
                qos=self._cfg.qos,
                retain=self._cfg.retain,
            )
            logger.debug("Published → %s", topic)
        except Exception as exc:
            logger.warning("MQTT publish failed (%s): %s", topic, exc)
