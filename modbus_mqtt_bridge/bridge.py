"""Main bridge loop — polls Modbus devices and publishes readings to MQTT."""

from __future__ import annotations

import asyncio
import logging
from typing import List

from .config import BridgeConfig, DeviceConfig
from .publisher import MqttPublisher
from .reader import ModbusReader

logger = logging.getLogger(__name__)

async def run_bridge(cfg: BridgeConfig) -> None:
    """Run all device pollers concurrently under a shared MQTT connection."""
    if not cfg.devices:
        logger.warning("No devices configured — nothing to do.")
        return

    logger.info("Starting bridge: %d device(s) → mqtt://%s:%d",
                len(cfg.devices), cfg.mqtt.host, cfg.mqtt.port)

    async with MqttPublisher(cfg.mqtt) as publisher:
        tasks = [
            asyncio.create_task(
                _device_loop(device, publisher),
                name=f"device:{device.name}",
            )
            for device in cfg.devices
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            raise


async def _device_loop(device: DeviceConfig, publisher: MqttPublisher) -> None:
    """Poll a single device forever, reconnecting on failure with exponential backoff."""
    reader = ModbusReader(device)
    logger.info("[%s] starting — poll every %.1fs", device.name, device.poll_interval)
    delay = device.reconnect_delay

    while True:
        if not reader.connected:
            connected = await reader.connect()
            if not connected:
                logger.info("[%s] retrying in %.0fs…", device.name, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, device.max_reconnect_delay)
                continue
            delay = device.reconnect_delay  # reset on successful connect

        try:
            readings = await reader.read_all()

            if readings:
                await publisher.publish_readings(device, readings)
                logger.info("[%s] published %d register(s): %s",
                            device.name, len(readings),
                            {k: v for k, v in list(readings.items())[:4]})
            else:
                logger.warning("[%s] no readings returned", device.name)

        except Exception as exc:
            logger.error("[%s] poll error: %s", device.name, exc, exc_info=True)
            await reader.close()

        await asyncio.sleep(device.poll_interval)
