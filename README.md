# Hiome Core Gateway

An archival source release of Hiome's sensor gateway and room-occupancy services, originally developed in 2019–2020. Published for reference and community exploration.

This is a clean source snapshot with a new history. It excludes historical device-specific configuration and retired radio-driver code. Optional telemetry and remote provisioning have no configured destinations by default.

## Original environment

The code targets Python 2.7, Raspberry Pi hardware, a local PostgreSQL database, and an MQTT broker reachable as `hiome`. The dependency versions are preserved in `requirements.txt`.

```sh
pip install -r requirements.txt
python main.py
```

The other top-level service entry points include `serial_reader.py`, `librarian.py`, `timer.py`, `solar.py`, `manifester.py`, `babelfish.py`, and `entry_metrics.py`. Their original deployment configuration, database schema, device firmware, and hardware are not included here.

## Optional configuration

`.env.example` documents placeholders for optional integrations. Export any values you need through the service environment; this project does not automatically load `.env` files.

- `SLACK_WEBHOOK_URL`: an operator-provided webhook, otherwise Slack telemetry is disabled.
- `STATSD_HOST` and `STATSD_PORT`: an operator-provided metrics destination, otherwise metrics are disabled.
- `DEVICE_DASHBOARD_URL`: an optional dashboard link in telemetry.
- `MANIFEST_BASE_URL` and `DEVICEID`: optional remote provisioning; both must be configured to enable it.

The application retains its original local-network design. It has not been modernized for deployment on an untrusted network. Installed dependencies retain their own licenses.

## License

MIT. See [LICENSE](LICENSE).
