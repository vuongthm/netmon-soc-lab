# services/ai_service.py
# =============================================================================
# AI service: Groq LLM chatbot + Isolation Forest anomaly detection.
#
# Context luôn được build từ Prometheus LIVE trước mỗi query.
# Lịch sử hội thoại giữ in-memory (tối đa 16 turns).
# =============================================================================

import os
import threading
import uuid
from datetime import datetime

import joblib

import config
from database.repository import alert_repo

_model_cache: dict = {}
_history:     list = []
_hist_lock         = threading.Lock()

_SYSTEM_PROMPT = f"""You are a network monitoring AI assistant for NetMon SOC.

INFRASTRUCTURE (mạng {config.DEVICES[0]['ip'].rsplit('.', 3)[0]}.0.0/16 nếu là 10.20):
{chr(10).join(f"- {d['name']} ({d['type']}) — {d['ip']}: {d['description']}" for d in config.DEVICES)}
- Monitoring stack: Prometheus + SNMP Exporter + Node Exporter + Suricata IDS

RULES:
1. Base all answers strictly on the provided live metrics.
2. If a metric shows NO DATA or OFFLINE, say so explicitly.
3. Never invent device status.
4. Suggest specific Cisco IOS or Linux CLI commands when asked for fixes.
5. Keep answers concise. Use bullet points.
6. Respond in Vietnamese when the user writes in Vietnamese; otherwise English."""


# ---------------------------------------------------------------------------
# Isolation Forest model helpers
# ---------------------------------------------------------------------------

def _load_model(metric: str):
    if metric in _model_cache:
        return _model_cache[metric]
    path = os.path.join(config.MODELS_DIR, f"isolation_forest_{metric}.pkl")
    if not os.path.exists(path):
        return None
    try:
        m = joblib.load(path)
        _model_cache[metric] = m
        return m
    except Exception:
        return None


def get_model_status() -> dict:
    metrics = ["traffic_in_bps", "traffic_out_bps", "cpu_percent", "mem_used_pct"]
    return {
        m: os.path.exists(os.path.join(config.MODELS_DIR, f"isolation_forest_{m}.pkl"))
        for m in metrics
    }


def _score_anomaly(metric: str, value: float) -> dict:
    m = _load_model(metric)
    if not m:
        return {"is_anomaly": False, "score": 0.0, "severity": "normal"}
    try:
        X     = m["scaler"].transform([[value]])
        pred  = m["model"].predict(X)[0]
        score = float(m["model"].score_samples(X)[0])
        if pred == 1:
            sev = "normal"
        elif score < config.SCORE_CRITICAL:
            sev = "critical"
        else:
            sev = "warning"
        return {"is_anomaly": pred == -1, "score": round(score, 4), "severity": sev}
    except Exception:
        return {"is_anomaly": False, "score": 0.0, "severity": "normal"}


# ---------------------------------------------------------------------------
# Anomaly scan
# ---------------------------------------------------------------------------

def run_anomaly_scan(snapshots: list) -> list[dict]:
    """
    Chạy Isolation Forest trên tất cả snapshots.
    Lưu anomaly vào DB nếu phát hiện.
    Trả về list anomaly dict.
    """
    from services.alerting import _make_alert_record

    anomalies = []

    for snap in snapshots:
        name = snap["name"]
        sm   = snap.get("server_metrics")

        # Server metrics
        if sm:
            for metric, value, label, min_val in [
                ("cpu_percent",  sm.get("cpu_percent"),      "CPU", config.MIN_CPU_PCT),
                ("mem_used_pct", sm.get("mem_used_percent"), "RAM", config.MIN_CPU_PCT),
            ]:
                if value and value >= min_val:
                    r = _score_anomaly(metric, value)
                    if r["is_anomaly"]:
                        anomalies.append({
                            "device":   name,
                            "metric":   metric,
                            "value":    value,
                            "score":    r["score"],
                            "severity": r["severity"],
                            "message":  f"[AI] {label} anomaly: {value:.1f}% (score={r['score']})",
                        })

        # Traffic metrics
        for t in snap.get("traffic", []):
            for metric, value in [
                ("traffic_in_bps",  t.get("in_bps",  0)),
                ("traffic_out_bps", t.get("out_bps", 0)),
            ]:
                if value >= config.MIN_TRAFFIC_BPS:
                    r = _score_anomaly(metric, value)
                    if r["is_anomaly"]:
                        anomalies.append({
                            "device":   name,
                            "metric":   metric,
                            "value":    value,
                            "score":    r["score"],
                            "severity": r["severity"],
                            "message":  f"[AI] Traffic anomaly {t['name']}: {value / 1e6:.2f} Mbps",
                        })

    # Lưu DB
    for a in anomalies:
        record = _make_alert_record(
            device   = a["device"],
            severity = a["severity"],
            category = "ai-anomaly",
            message  = a["message"],
            details  = f"score={a['score']}",
            sub_key  = f"{a['device']}::ai::{a['metric']}",
        )
        record["id"] = str(uuid.uuid4())
        alert_repo.save(record)

    return anomalies


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context() -> tuple[str, bool, bool]:
    from services.collector import build_prometheus_context
    return build_prometheus_context()


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def chat(question: str) -> dict:
    """Gửi câu hỏi đến Groq LLM với context live từ Prometheus."""
    global _history

    if not config.GROQ_ENABLED:
        return {"answer": "AI chưa được cấu hình. Vui lòng set GROQ_API_KEY.",
                "source": "disabled", "prometheus_alive": False}

    context, prom_alive, has_data = _build_context()

    if not prom_alive:
        return {
            "answer": (
                "Prometheus không phản hồi. Không thể lấy dữ liệu hệ thống.\n\n"
                "Kiểm tra:\n  systemctl status prometheus\n"
                "  curl http://localhost:9090/-/healthy"
            ),
            "source": "error-no-prometheus",
            "prometheus_alive": False,
        }

    user_msg = f"{context}\n\nUSER QUESTION:\n{question}"

    with _hist_lock:
        _history.append({"role": "user", "content": user_msg})
        if len(_history) > 16:
            _history = _history[-16:]

    try:
        from groq import Groq
        client = Groq(api_key=config.GROQ_API_KEY)
        with _hist_lock:
            hist = list(_history)

        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "system", "content": _SYSTEM_PROMPT}] + hist,
            max_tokens=1500,
            temperature=0.2,
        )
        answer = resp.choices[0].message.content
        with _hist_lock:
            _history.append({"role": "assistant", "content": answer})

        return {"answer": answer, "source": config.GROQ_MODEL,
                "prometheus_alive": True, "has_data": has_data}

    except ImportError:
        return {"answer": "Package groq chưa được cài. Chạy: pip install groq",
                "source": "error"}
    except Exception as exc:
        err = str(exc)
        if "rate_limit" in err.lower():
            return {"answer": "Groq rate limit. Vui lòng đợi 1 phút.", "source": "error-rate-limit"}
        if "invalid_api_key" in err.lower():
            return {"answer": "Groq API key không hợp lệ.", "source": "error-auth"}
        return {"answer": f"Lỗi AI: {err[:200]}", "source": "error"}


def reset_conversation() -> None:
    global _history
    with _hist_lock:
        _history = []
