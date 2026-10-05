"""Command-line entry point."""

from __future__ import annotations

from click.testing import CliRunner

from modbus_mqtt_bridge.__main__ import main


def test_starts_and_exits_cleanly_with_no_devices(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("mqtt:\n  host: 127.0.0.1\ndevices: []\n")

    result = CliRunner().invoke(main, ["-c", str(config)])

    assert result.exit_code == 0, result.output or repr(result.exception)


def test_invalid_config_exits_with_error(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("devices:\n  - name: meter\n    unit_id: 999\n")

    result = CliRunner().invoke(main, ["-c", str(config)])

    assert result.exit_code == 1
