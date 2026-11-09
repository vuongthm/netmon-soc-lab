# NetMon SOC — application source and deployment

The NetMon SOC application is a **Flask-based monitoring and security operations dashboard** for the PNETLab network defined in [`../../configuration/`](../../configuration/README.md). The source, frontend assets, PostgreSQL models, service modules and seven runtime model artifacts are all present in this directory.

This guide describes the **actual supplied code layout and configuration**. It does not depend on a missing project root at `/opt/netmon`, and it does not assume that an `.env.example` file exists.

## 1. Architecture and components

| Module | Files | Responsibility |
| --- | --- | --- |
| Application entry | `app.py`, `config.py` | Load local environment, create database tables, mount routes, start background workers |
| HTTP/API | `routes/` | Dashboard, alerts, SOC events and AI routes |
| Core logic | `services/` | Prometheus collection, service checks, Suricata ingestion, alerts, notifications, AI integration |
| Data storage | `database/` | SQLAlchemy models, sessions and repositories on PostgreSQL |
| User interface | `templates/`, `static/` | Jinja pages, HTML and CSS |
| Model artifacts | `models/` | Seven serialized Isolation Forest model/scaler bundles for runtime loading |
| Administrative scripts | `scripts/` | Database setup, model retraining and a schema-related helper |
| Scrape configuration | `prometheus.yml` | Canonical Prometheus jobs for the lab |

The application monitors **six devices**: pfSense, Core-Router, SwL3A, SwL3B, Server02 and Server01. Its configured services are the pfSense WebGUI, Nginx HTTP endpoint, BIND9 DNS lookup and FTP TCP port check.

**Background polling in `app.py`:** Prometheus collection/threshold evaluation every `REFRESH_INTERVAL` (default **15 s**); Suricata SSH ingestion every **10 s** when enabled; service checks every **30 s**; daily summary at the configured local time. The application uses PostgreSQL and Prometheus as separate systems: PostgreSQL stores application events while Prometheus stores timeseries metrics.

## 2. Requirements and prerequisites

- Python 3 and a working `venv`/`pip` installation (use a Python version compatible with the pinned environment and installed dependencies; the manifest specifies minimum package versions, not a locked environment).
- PostgreSQL with a database and user accessible through `DATABASE_URL`.
- Prometheus and SNMP Exporter available to the monitor; see [`../../configuration/monitoring/monitor-host.md`](../../configuration/monitoring/monitor-host.md).
- Accessible lab nodes and Node Exporter endpoints for complete device monitoring.
- Optional: pfSense Suricata logs accessible through an SSH identity; Telegram bot token/recipient IDs; Groq API key.

**Monitor host in this lab: `172.24.0.10`**. The `172.24.0.100` address refers to the PNETLab web interface. Do not copy older examples that described `172.24.0.100` as the monitoring host.

## 3. Local installation

From the **repository root**, create a virtual environment in the application folder:

```bash
cd source/code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Alternatively, on a separate monitor host, copy **the contents of `source/code/`** to a chosen application directory, e.g. `/opt/netmon`, and run all subsequent commands there. Do not copy the repository root to `/opt/netmon` and then expect `app.py` to be at the top level.

### PostgreSQL provisioning

The application initializes SQLAlchemy tables during import/startup, so the **database must already exist**. The following is a manual **example for a fresh, isolated lab**, not a production database migration:

```bash
sudo apt install -y postgresql postgresql-client
sudo systemctl enable --now postgresql
sudo -u postgres createuser --pwprompt netmon
sudo -u postgres createdb --owner=netmon netmon
```

Enter a strong, lab-specific password when prompted. If the user/database already exists, inspect it rather than re-running the creation commands. The application connects using `DATABASE_URL=postgresql://netmon:<PASSWORD>@localhost:5432/netmon` (URL-encode reserved characters in the password as required).

The included [`scripts/setup_db.sh`](scripts/setup_db.sh) is an **optional system-administration script**. Review it before use: it installs packages, modifies PostgreSQL configuration, and contains a fallback default database password. Do not blindly run it on a shared or production host.

## 4. Environment configuration

`app.py` reads a `.env` file from **the same directory as `app.py`** before importing `config.py`. Existing environment variables take precedence. The repository **does not include `.env.example`**; create `source/code/.env` locally using the following *sample keys*, replacing all placeholders with your own values:

```dotenv
APP_HOST=0.0.0.0
APP_PORT=5000
DEBUG=false
SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_SECRET
DATABASE_URL=postgresql://netmon:REPLACE_DB_PASSWORD@localhost:5432/netmon
PROMETHEUS_URL=http://localhost:9090
REFRESH_INTERVAL=15
CACHE_TTL=12
SURICATA_ENABLED=false
SURICATA_SSH_HOST=172.24.0.115
SURICATA_SSH_USER=admin
SURICATA_SSH_KEY=/absolute/path/to/your/private/ssh_key
TELEGRAM_BOT_TOKEN=
TELEGRAM_VUONG_ID=
TELEGRAM_TUAN_ID=
GROQ_API_KEY=
```

**Important:** `SURICATA_ENABLED=false` is a safe first-launch choice until SSH and EVE logging are configured. Set it to `true` only after verifying each `SURICATA_INTERFACES` path in `config.py`. The source currently defaults to `true` if that variable is not set. Do not use or publish hard-coded lab secrets found in old example notes.

Protect local secrets:

```bash
chmod 600 .env
```

The repository `.gitignore` excludes `.env`, local virtual environments and private keys. Check the files staged for commit regardless.

### Canonical Prometheus configuration

**This file is the source of truth:** [`prometheus.yml`](prometheus.yml). Do not edit a second independent YAML copy in a Markdown guide. On the monitor host, from `source/code/`:

```bash
sudo install -m 0644 prometheus.yml /etc/prometheus/prometheus.yml
promtool check config /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus
curl -fsS http://localhost:9090/-/healthy
```

The YAML contains **four SNMP jobs**, **two Node Exporter jobs**, and **three optional mtail jobs**. The optional mtail targets will remain DOWN unless the corresponding server-side exporters are installed and operational. Verify the `if_mib` module on the installed SNMP Exporter version.

## 5. Start the application

From `source/code/` with the venv active, after PostgreSQL and the required monitoring endpoints are configured:

```bash
python app.py
```

Open `http://127.0.0.1:5000/` from the host itself or `http://172.24.0.10:5000/` from an authorized machine with overlay connectivity. `APP_HOST=0.0.0.0` binds to all host interfaces; restrict exposure with host firewall rules or use loopback binding when remote access is unnecessary.

**Do not enable Flask debug/reloader in this lab.** The entry point starts threads under `if __name__ == '__main__'`, and a debug reloader may create duplicate workers. The built-in Flask server is for demonstration, not a production deployment with multiple web workers. Running multiple worker processes without redesign can also duplicate collectors, checks and notifications.

## 6. API surface

These routes exist in the supplied `routes/` source:

| Area | Method and endpoint | Purpose |
| --- | --- | --- |
| Overview | `GET /api/summary` | Device totals/status |
| Devices | `GET /api/devices` | Device details |
| Services | `GET /api/services` | Service health checks |
| Charts | `GET /api/chart/<job>` | Timeseries chart data |
| Alerts | `GET /api/alerts`, `GET /api/alerts/stats`, `GET /api/alerts/history` | Query alert records and summaries |
| Alert updates | `POST /api/alerts/<alert_id>/resolve`, `POST /api/alerts/clear` | Resolve or clear records |
| SOC | `GET /api/soc/stats`, `GET /api/soc/events`, `GET /api/soc/timeline`, `GET /api/soc/interfaces` | Suricata views |
| Attacker detail | `GET /api/soc/attacker/<src_ip>` | Source IP event detail |
| AI | `GET /api/ai/status`, `GET /api/ai/scan` | AI/model availability and analysis |
| AI chat | `POST /api/ai/chat`, `POST /api/ai/chat/reset` | Chat interaction and reset |

**Security note:** The provided Flask application does not demonstrate a full production authentication/authorization layer. Do not expose the built-in HTTP server and its state-changing APIs to untrusted networks without adding access controls.

### Basic read-only checks

```bash
curl -fsS http://127.0.0.1:5000/api/summary
curl -fsS http://127.0.0.1:5000/api/devices
curl -fsS http://127.0.0.1:5000/api/services
curl -fsS http://127.0.0.1:5000/api/soc/stats
curl -fsS http://127.0.0.1:5000/api/ai/status
```

A responding API confirms only that the endpoint returned, **not** that every exporter, database write, notification channel or anomaly model has passed a full test. Use the [integration checklist](../../configuration/verification.md) to validate the system layers.

## 7. Suricata, Telegram, and AI integrations

**Suricata:** `services/suricata.py` SSHes to pfSense and reads the tail of each enabled EVE JSON path listed in `config.SURICATA_INTERFACES`. Inspect the actual pfSense paths and ensure the SSH account has permission to read them. The source currently sets `StrictHostKeyChecking=no`; that is a lab convenience, **not** a recommended security control for a real deployment.

**Telegram:** configure `TELEGRAM_BOT_TOKEN`, `TELEGRAM_VUONG_ID`, and `TELEGRAM_TUAN_ID` in the local environment, then verify authorized delivery without sharing tokens. `config.MEMBERS` maps owner roles and notification preferences; changing labels in Prometheus does not independently grant or enforce authorization.

**Groq:** set `GROQ_API_KEY` for the optional LLM-powered AI assistant. The current model identifier is configured in `config.py`; availability requires an active, authorized API account and compatible service response. Never embed this key in the repository.

## 8. Isolation Forest models

The runtime loads models from `source/code/models/`, because `config.MODELS_DIR` is currently `models` and `app.py` changes the working directory to the directory containing `app.py`.

- **Runtime copies:** [`models/`](models/) (seven `.pkl` files).
- **Training notebook, datasets and original model files:** [`../machine-learning/`](../machine-learning/README.md).
- **Prometheus-based training script:** [`scripts/train_models.py`](scripts/train_models.py). This script uses Prometheus range queries; as written, its metric configuration covers **CPU, memory and traffic**, not the complete seven-metric set.

For the source code's anomaly scoring, each joblib model file is expected to contain a `model` and a `scaler`. Only load serialized Python objects from a **trusted source**. Retraining will overwrite selected files in `models/`; validate and back up deliberately before retraining.

## 9. Troubleshooting and operating limits

| Symptom | What to check |
| --- | --- |
| Application exits immediately at startup | PostgreSQL reachable via `DATABASE_URL`; existing role/db; Python packages installed |
| `/api/devices` shows no fresh metrics | Prometheus `/api/v1/targets` and connectivity; `job` names match `config.py` |
| SNMP jobs DOWN | UDP/161 from exporter to device; community/module `if_mib`; overlay route, ACL/firewall |
| Node Exporter jobs DOWN | `systemctl status node_exporter`; reachability TCP/9100 from monitor |
| Suricata events missing | `SURICATA_ENABLED`, SSH key/permissions, per-interface EVE paths, sensor status |
| Telegram missing | Bot token and member chat IDs; recipient consent/permissions; notification selection |
| AI status unavailable | Groq API key or missing/untrusted model; check logs rather than assuming success |
| Optional mtail jobs DOWN | mtail process, matching log input, parser output, target port 3903/3904/3905 |

### Known source assumptions

- The included `setup_db.sh` is not a migration framework and may alter system PostgreSQL configuration; review before running.
- `.env.example` is referenced in some code comments but **is not included**. The sample in §4 is illustrative; secrets must be user-supplied.
- Source files contain development-oriented defaults and comments; runtime security and model behavior have **not** been independently audited.
- The repository's lab evidence does not provide production-grade detection benchmarking, load testing, or a guaranteed service-level objective.

**Next:** [infrastructure configuration](../../configuration/README.md) · [training artifacts](../machine-learning/README.md) · [project reports](../../report/README.md).
