"""Entry point: python -m modbus_mqtt_bridge -c config.yaml"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click
import yaml
from pydantic import ValidationError

from .bridge import run_bridge
from .config import BridgeConfig


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Silence noisy pymodbus internals unless DEBUG
    if level.upper() != "DEBUG":
        logging.getLogger("pymodbus").setLevel(logging.WARNING)


def new_event_loop() -> asyncio.AbstractEventLoop:
    """Event loop that aiomqtt can use on every platform.

    aiomqtt needs add_reader/add_writer, which Windows' default Proactor loop
    does not implement, so Windows gets a selector loop.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


@click.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default="config.yaml",
    show_default=True,
    help="Path to YAML configuration file.",
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
)
def main(config: Path, log_level: str) -> None:
    """Read Modbus TCP/RTU devices and publish readings to an MQTT broker."""
    _setup_logging(log_level)
    logger = logging.getLogger(__name__)

    try:
        raw = yaml.safe_load(config.read_text())
        cfg = BridgeConfig.model_validate(raw or {})
    except (yaml.YAMLError, ValidationError) as exc:
        logger.error("Config error: %s", exc)
        sys.exit(1)

    loop = new_event_loop()
    asyncio.set_event_loop(loop)

    task = loop.create_task(run_bridge(cfg))

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("Received %s — shutting down…", sig.name)
        task.cancel()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _shutdown, s)
        except NotImplementedError:
            # Windows event loops have no signal handlers; Ctrl+C arrives as
            # KeyboardInterrupt below instead.
            pass

    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        logger.info("Received SIGINT — shutting down…")
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()
        logger.info("Bridge stopped.")


if __name__ == "__main__":
    main()
