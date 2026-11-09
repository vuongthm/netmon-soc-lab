# NetMon SOC application integration

The **application source is present** at [`../../source/code/`](../../source/code/README.md). This guide explains how the lab's monitoring configuration maps to that source; it is not a separate copy of `config.py` or a second application implementation.

## Runtime entry point

| Component | Current source of truth |
| --- | --- |
| Flask entry point and background workers | [`../../source/code/app.py`](../../source/code/app.py) |
| Device inventory / thresholds / ownership | [`../../source/code/config.py`](../../source/code/config.py) |
| Prometheus scrape configuration | [`../../source/code/prometheus.yml`](../../source/code/prometheus.yml) |
| Python dependencies | [`../../source/code/requirements.txt`](../../source/code/requirements.txt) |
| Database models and repositories | [`../../source/code/database/`](../../source/code/database/) |
| HTTP/API routes | [`../../source/code/routes/`](../../source/code/routes/) |
| Data collection, alerting, IDS, ML, notifications | [`../../source/code/services/`](../../source/code/services/) |
| Application-level deployment details | [`../../source/code/README.md`](../../source/code/README.md) |

## Device-to-metric mapping

The application's `config.DEVICES` contains exactly **six monitored devices**. Match each device's `job` with `job_name` in `prometheus.yml`:

| Device | Metric source | `job_name` | Target |
| --- | --- | --- | --- |
| pfSense | SNMP Exporter | `snmp-pfsense` | `172.24.0.115` |
| Core-Router | SNMP Exporter | `snmp-core-router` | `10.20.0.1` |
| SwL3A | SNMP Exporter | `snmp-swl3a` | `10.20.0.2` |
| SwL3B | SNMP Exporter | `snmp-swl3b` | `10.20.0.3` |
| Server02 | Node Exporter | `node-server02` | `10.20.200.10:9100` |
| Server01 | Node Exporter | `node-server01` | `10.20.201.10:9100` |

The same Prometheus file additionally declares **three mtail targets**, which are optional service metrics, **not additional monitored devices** in `config.DEVICES`.

## Prepare the application

From the repository root:

```bash
cd source/code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a local **`source/code/.env`** with at least the correct `DATABASE_URL` and `PROMETHEUS_URL`. The application loads `.env` from the directory containing `app.py`, even if the process is launched from another working directory. This repository **does not contain a `.env.example`**; see the [application README](../../source/code/README.md#environment-configuration) for a minimal template and warnings.

The application initializes PostgreSQL tables when it starts. The provided `scripts/setup_db.sh` is an optional, intrusive lab administration script; **review it before running** because it modifies database settings. Use manual provisioning when possible.

```bash
python app.py
```

Set `DEBUG=false` in `.env` to avoid the Flask development reloader starting background workers twice. This entry point is for **local/lab demonstration**, not a hardened public deployment.

## Integration checks

```bash
curl -fsS http://localhost:9090/-/healthy
curl -fsS http://localhost:5000/api/summary
curl -fsS http://localhost:5000/api/devices
curl -fsS http://localhost:5000/api/services
curl -fsS http://localhost:5000/api/ai/status
```

The application uses **SSH** to read Suricata EVE JSON per interface. Confirm the SSH identity, host key, remote permissions, and `SURICATA_INTERFACES` paths in `config.py`. Current source code has `StrictHostKeyChecking=no`; apply stricter host-key verification for any use outside a controlled lab. The app also needs locally supplied Telegram/Groq credentials to enable those optional integrations.

For end-to-end checks, see [`../verification.md`](../verification.md). Do not treat an exporter being reachable as proof that alerting, model inference, notifications, or the SOC dashboard has passed functional tests.
