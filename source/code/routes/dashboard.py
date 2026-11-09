# routes/dashboard.py
# =============================================================================
# HTTP endpoints cho dashboard chính.
# Route chỉ: nhận request → gọi service → trả JSON/HTML.
# Không chứa business logic.
# =============================================================================

import threading
import time

from flask import Blueprint, jsonify, request, render_template

import config
from services.collector import collect_all, collect_charts, fmt_uptime, fmt_bps
from services.alerting  import check_and_fire
from services.checker   import get_latest

bp = Blueprint("dashboard", __name__)

# Cache snapshot để tránh query Prometheus quá nhiều
_cache      = {"data": None, "ts": 0}
_cache_lock = threading.Lock()


def _get_snapshots() -> list:
    now = time.time()
    with _cache_lock:
        if _cache["data"] is not None and (now - _cache["ts"]) < config.CACHE_TTL:
            return _cache["data"]

    snapshots = collect_all()
    check_and_fire(snapshots)

    # Thêm formatted strings cho frontend
    for s in snapshots:
        s["uptime_str"] = fmt_uptime(s.get("uptime"))
        for t in s.get("traffic", []):
            t["in_bps_str"]  = fmt_bps(t.get("in_bps",  0))
            t["out_bps_str"] = fmt_bps(t.get("out_bps", 0))

    with _cache_lock:
        _cache["data"] = snapshots
        _cache["ts"]   = time.time()

    return snapshots


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


# ---------------------------------------------------------------------------
# APIs
# ---------------------------------------------------------------------------

@bp.route("/api/devices")
def api_devices():
    try:
        return jsonify({"status": "ok", "data": _get_snapshots()})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@bp.route("/api/summary")
def api_summary():
    try:
        data = _get_snapshots()
        return jsonify({
            "total":    len(data),
            "up":       sum(1 for d in data if d["status"] == "up"),
            "warning":  sum(1 for d in data if d["status"] == "warning"),
            "critical": sum(1 for d in data if d["status"] == "critical"),
            "offline":  sum(1 for d in data if d["status"] == "offline"),
            "if_down":  sum(
                sum(1 for i in d.get("interfaces", [])
                    if i["status"] == 2
                    and i.get("alias", "").strip()
                    and i.get("admin_status", 1) == 1)
                for d in data
            ),
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@bp.route("/api/services")
def api_services():
    try:
        return jsonify({"status": "ok", "services": get_latest()})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@bp.route("/api/chart/<job>")
def api_chart(job: str):
    try:
        minutes     = int(request.args.get("minutes", 60))
        device_type = request.args.get("type", "router")
        return jsonify({"status": "ok", "charts": collect_charts(job, device_type, minutes)})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
