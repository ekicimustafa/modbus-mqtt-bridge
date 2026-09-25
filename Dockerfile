FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY modbus_mqtt_bridge/ modbus_mqtt_bridge/

ENTRYPOINT ["python", "-m", "modbus_mqtt_bridge"]
CMD ["-c", "/config/config.yaml"]
