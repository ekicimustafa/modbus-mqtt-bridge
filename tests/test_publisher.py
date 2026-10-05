"""MqttPublisher against a real (in-process) MQTT broker."""

from __future__ import annotations

import asyncio
import json
import socket

import aiomqtt
import pytest
from amqtt.broker import Broker

from modbus_mqtt_bridge.config import DeviceConfig, MqttConfig
from modbus_mqtt_bridge.publisher import MqttPublisher

DEVICE = DeviceConfig(
    name="meter",
    host="127.0.0.1",
    registers=[{"name": "power_kw", "address": 0, "unit": "kW"}],
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def start_broker(port: int) -> Broker:
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
        "sys_interval": 0,
        "auth": {"allow-anonymous": True},
        "topic-check": {"enabled": False},
    })
    await broker.start()
    return broker


async def next_message(messages, timeout: float = 10) -> dict:
    message = await asyncio.wait_for(anext(messages), timeout)
    return json.loads(message.payload)


def mqtt_config(port: int, **kwargs) -> MqttConfig:
    return MqttConfig(host="127.0.0.1", port=port, client_id="bridge-under-test", **kwargs)


async def test_publishes_one_topic_per_register():
    port = _free_port()
    broker = await start_broker(port)
    try:
        async with aiomqtt.Client("127.0.0.1", port, identifier="observer") as observer:
            await observer.subscribe("modbus/#")
            messages = aiter(observer.messages)
            async with MqttPublisher(mqtt_config(port)) as publisher:
                await publisher.publish_readings(DEVICE, {"power_kw": 12.5})
                payload = await next_message(messages)
        assert payload["device"] == "meter"
        assert payload["register"] == "power_kw"
        assert payload["value"] == 12.5
        assert payload["unit"] == "kW"
    finally:
        await broker.shutdown()


async def test_reconnects_after_broker_restart():
    port = _free_port()
    broker = await start_broker(port)
    async with MqttPublisher(mqtt_config(port, reconnect_delay=1, max_reconnect_delay=1)) as publisher:
        await publisher.publish_readings(DEVICE, {"power_kw": 1.0})

        await broker.shutdown()
        # Publishing while the broker is down must not raise.
        await asyncio.wait_for(publisher.publish_readings(DEVICE, {"power_kw": 2.0}), 2)

        broker = await start_broker(port)
        try:
            async with aiomqtt.Client("127.0.0.1", port, identifier="observer") as observer:
                await observer.subscribe("modbus/#")
                messages = aiter(observer.messages)

                # The bridge keeps polling; within a few cycles readings must flow again.
                async def keep_publishing():
                    while True:
                        await publisher.publish_readings(DEVICE, {"power_kw": 3.0})
                        await asyncio.sleep(0.5)

                producer = asyncio.create_task(keep_publishing())
                try:
                    payload = await next_message(messages, timeout=15)
                finally:
                    producer.cancel()
            assert payload["value"] == 3.0
        finally:
            await broker.shutdown()


async def test_starts_even_when_broker_is_down():
    port = _free_port()
    publisher = MqttPublisher(mqtt_config(port, reconnect_delay=1, max_reconnect_delay=1))
    # Entering the context must not fail just because the broker is not up yet.
    await asyncio.wait_for(publisher.__aenter__(), 5)
    try:
        await asyncio.wait_for(publisher.publish_readings(DEVICE, {"power_kw": 1.0}), 3)
    finally:
        await publisher.__aexit__(None, None, None)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
