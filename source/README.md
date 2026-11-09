# Source code and machine-learning materials

The repository contains **the NetMon SOC application source** and **the project's machine-learning materials**. They serve different purposes and are deliberately separated.

| Location | Contents | Start here |
| --- | --- | --- |
| [`code/`](code/README.md) | Flask application, REST API routes, monitoring and security services, database layer, templates, CSS, dependency manifest, Prometheus YAML, runtime model copies | [`code/README.md`](code/README.md) |
| [`machine-learning/`](machine-learning/README.md) | Data-analysis/training notebook, recorded metrics datasets, seven original serialized model artifacts | [`machine-learning/README.md`](machine-learning/README.md) |

## Application source

`code/app.py` is the entry point. Background workers collect Prometheus metrics, ingest Suricata EVE JSON, check service health, and produce periodic summaries. `config.py` defines six monitored devices, four checked services, security/log paths and notification recipients. The database uses PostgreSQL through SQLAlchemy.

`code/models/` contains **runtime copies** of seven `.pkl` artifacts; they are loaded by `services/ai_service.py` through `config.MODELS_DIR`. In contrast, `machine-learning/models/` belongs to the **training artifact package**. The filenames currently match, but the two directories can diverge if a model is retrained. Synchronize deliberately and validate model behavior before replacing production/runtime artifacts.

## Running the app

Follow the [application README](code/README.md) for Python environment setup, database configuration, `.env`, model paths and verification. From the repository root, the application directory is:

```bash
cd source/code
```

Running `python app.py` without a configured PostgreSQL database raises an initialization error because tables are created on startup. Deploy network monitoring services first and use the canonical [`code/prometheus.yml`](code/prometheus.yml) to configure Prometheus.

## Safety and reproducibility

- The project is an **isolated, authorized lab**; its interface addresses and device credentials are not production guidance.
- The Python source is included as-is; not all services or external credentials can be verified offline.
- **Do not commit** `.env`, database passwords, Telegram/Groq tokens, SSH private keys or internal host information from a real environment.
- Serialized `.pkl` artifacts may execute code when deserialized. Load only trusted models. The repository documentation refresh does **not** run or deserialize them.

For network-side setup, see [`../configuration/README.md`](../configuration/README.md). For the PDF reports, see [`../report/README.md`](../report/README.md).
