#!/usr/bin/env python3
# scripts/train_models.py
# =============================================================================
# Train Isolation Forest models từ dữ liệu Prometheus lịch sử.
#
# Cách dùng:
#   cd /path/to/netmon
#   python scripts/train_models.py
#
# Yêu cầu:
#   - Prometheus đang chạy và có ít nhất 24h dữ liệu
#   - pip install scikit-learn joblib numpy
#
# Output:
#   models/isolation_forest_<metric>.pkl  (1 file mỗi metric)
# =============================================================================

import os
import sys

# Thêm project root vào path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import joblib
import requests
import time

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

import config

MODELS_DIR = config.MODELS_DIR
os.makedirs(MODELS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Cấu hình từng metric cần train
# ---------------------------------------------------------------------------
# Mỗi entry: (metric_name, promql_query, min_value_to_include)
METRIC_CONFIGS = []

for device in config.DEVICES:
    job   = device["job"]
    dtype = device["type"]

    if dtype in ("firewall", "router", "switch"):
        METRIC_CONFIGS.append((
            "traffic_in_bps",
            f'irate(ifHCInOctets{{job="{job}"}}[5m])*8',
            config.MIN_TRAFFIC_BPS,
        ))
        METRIC_CONFIGS.append((
            "traffic_out_bps",
            f'irate(ifHCOutOctets{{job="{job}"}}[5m])*8',
            config.MIN_TRAFFIC_BPS,
        ))

    elif dtype == "server":
        METRIC_CONFIGS.append((
            "cpu_percent",
            f'100-(avg by(instance)(irate(node_cpu_seconds_total{{job="{job}",mode="idle"}}[5m]))*100)',
            config.MIN_CPU_PCT,
        ))
        METRIC_CONFIGS.append((
            "mem_used_pct",
            f'(1-node_memory_MemAvailable_bytes{{job="{job}"}}/node_memory_MemTotal_bytes{{job="{job}"}})*100',
            config.MIN_CPU_PCT,
        ))

# Deduplicate theo metric name (nhiều device cùng loại)
seen = set()
METRIC_CONFIGS = [m for m in METRIC_CONFIGS if not (m[0] in seen or seen.add(m[0]))]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_range(promql: str, hours: int = 168, step: str = "5m") -> list[float]:
    """
    Lấy dữ liệu range từ Prometheus (mặc định 7 ngày).
    Trả về list các giá trị float.
    """
    end   = time.time()
    start = end - hours * 3600
    try:
        r = requests.get(
            f"{config.PROMETHEUS_URL}/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
            timeout=30,
        )
        d = r.json()
        if d.get("status") != "success":
            return []
        values = []
        for series in d["data"]["result"]:
            for _, val in series["values"]:
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    pass
        return values
    except Exception as exc:
        print(f"  [fetch] Lỗi: {exc}")
        return []


def train_model(metric_name: str, values: list[float], min_val: float) -> bool:
    """
    Train Isolation Forest cho 1 metric.
    Trả về True nếu thành công.
    """
    # Lọc giá trị đủ lớn để train (loại bỏ 0 và noise)
    filtered = [v for v in values if v >= min_val]

    if len(filtered) < 50:
        print(f"  ⚠️  Không đủ dữ liệu ({len(filtered)} mẫu, cần ≥ 50) — bỏ qua")
        return False

    X = np.array(filtered).reshape(-1, 1)

    # Chuẩn hóa
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train Isolation Forest
    # contamination: ước tính % điểm bất thường trong training data
    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,  # 5% outlier
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)

    # Lưu model + scaler vào cùng 1 file
    path = os.path.join(MODELS_DIR, f"isolation_forest_{metric_name}.pkl")
    joblib.dump({"model": model, "scaler": scaler}, path)
    print(f"   Đã lưu: {path} ({len(filtered)} mẫu)")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 56)
    print("  NetMon SOC — Train Isolation Forest Models")
    print("=" * 56)
    print()

    # Kiểm tra Prometheus
    try:
        r = requests.get(f"{config.PROMETHEUS_URL}/-/healthy", timeout=5)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
        print(f" Prometheus: {config.PROMETHEUS_URL}")
    except Exception as exc:
        print(f"❌ Không thể kết nối Prometheus: {exc}")
        sys.exit(1)

    print()

    success_count = 0

    for metric_name, promql, min_val in METRIC_CONFIGS:
        print(f"📊 Training: {metric_name}")
        print(f"   Query: {promql[:70]}...")

        values = fetch_range(promql, hours=168)  # 7 ngày
        print(f"   Lấy được: {len(values)} điểm dữ liệu")

        ok = train_model(metric_name, values, min_val)
        if ok:
            success_count += 1
        print()

    print("=" * 56)
    print(f"  Kết quả: {success_count}/{len(METRIC_CONFIGS)} models đã train")
    print("=" * 56)
    print()

    if success_count == 0:
        print("⚠️  Không train được model nào.")
        print("   Kiểm tra:")
        print("   1. Prometheus có dữ liệu ít nhất 24h chưa?")
        print(f"   2. PROMETHEUS_URL trong config: {config.PROMETHEUS_URL}")
        print("   3. Các job SNMP/Node Exporter đang scrape đúng không?")
    else:
        print(f" Models đã lưu tại thư mục: {MODELS_DIR}/")
        print("   Khởi động lại app để load models mới:")
        print("   python app.py")
    print()


if __name__ == "__main__":
    main()
