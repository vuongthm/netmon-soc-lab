# Machine-learning dataset, notebook, and trained models

This directory contains the NetMon SOC **Isolation Forest development materials**. The runtime integration lives separately in [`../code/services/ai_service.py`](../code/services/ai_service.py).

## Contents

| Path | Purpose |
| --- | --- |
| `network_monitor_ml.ipynb` | Exploratory analysis and Isolation Forest training workflow developed as a Colab notebook |
| `data/metrics_history.csv` | Historical metric observations used in the notebook |
| `data/metrics_history.xlsx` | Spreadsheet-format copy of the historical data |
| `models/isolation_forest_*.pkl` | Seven metric-specific serialized models |

The CSV fields include `timestamp`, `device`, `site`, `type`, `interface`, `metric`, and `value`.

## Model families

The seven supplied artifacts are named for the metrics they model:

- `cpu_percent` — server CPU utilization
- `mem_used_pct` — server memory utilization
- `disk_used_pct` — server disk utilization
- `traffic_in_bps` — inbound interface throughput
- `traffic_out_bps` — outbound interface throughput
- `in_errors` — inbound interface errors
- `out_errors` — outbound interface errors

The notebook uses **Google Colab/Google Drive paths**, so its dataset location needs adjustment before running it outside that environment. The application-specific online trainer at [`../code/scripts/train_models.py`](../code/scripts/train_models.py) is a different workflow: it fetches live Prometheus ranges and, as presently written, builds models only for **CPU, memory, inbound traffic and outbound traffic**. It does not regenerate all seven historical artifacts in a single run.

## How NetMon SOC uses models

At runtime, the Flask application's `services/ai_service.py` loads selected files from [`../code/models/`](../code/models/) via `config.MODELS_DIR='models'`. It expects serialized dictionaries containing `model` and `scaler` entries. The application focuses its live anomaly scan on CPU, memory and traffic; **the presence of seven files does not mean all seven metrics are scanned live**.

`code/models/` currently includes corresponding runtime copies. They are left in place for the supplied app. If training produces updated artifacts, compare and validate them before intentionally copying to the runtime directory.

## Reproducing results and safety

1. Open the notebook and inspect dependencies, data paths, preprocessing and feature definitions.
2. Use only trusted data; ensure metric units and field names match the expected model input.
3. Keep train/test separation when measuring detection performance. The Isolation Forest `contamination` parameter is a modeling assumption, **not a measured false-positive rate**.
4. Record runtime/library versions and validation results before replacing a model in the app.

**Security:** `joblib.load()` and pickle deserialization can execute arbitrary code. The supplied `.pkl` binaries were not opened, executed, or independently verified as part of the documentation update. Treat provenance as a prerequisite for use.
