# routes/alerts.py

from datetime import datetime
from flask import Blueprint, jsonify, render_template, request

from database.repository import alert_repo
from services.alerting   import resolve_alert, clear_all_alerts, get_stats

bp = Blueprint("alerts", __name__)


@bp.route("/alerts")
def alerts_page():
    return render_template("alerts.html")


@bp.route("/api/alerts")
def api_alerts():
    severity = request.args.get("severity")
    category = request.args.get("category")
    device   = request.args.get("device")
    limit    = min(int(request.args.get("limit", 300)), 1000)

    resolved_param = request.args.get("status")
    resolved = None
    if resolved_param == "unresolved":
        resolved = False
    elif resolved_param == "resolved":
        resolved = True

    from_dt = to_dt = None
    try:
        if request.args.get("from"):
            from_dt = datetime.fromisoformat(request.args["from"])
        if request.args.get("to"):
            to_dt = datetime.fromisoformat(request.args["to"])
    except ValueError:
        pass

    alerts = alert_repo.get_many(
        limit=limit, severity=severity, category=category,
        resolved=resolved, device=device, from_dt=from_dt, to_dt=to_dt,
    )
    return jsonify({"total": len(alerts), "alerts": alerts})


@bp.route("/api/alerts/stats")
def api_stats():
    return jsonify(get_stats())


@bp.route("/api/alerts/history")
def api_history():
    bucket = request.args.get("bucket", "day")
    try:
        from_dt = datetime.fromisoformat(request.args["from"])
        to_dt   = datetime.fromisoformat(request.args["to"])
    except (KeyError, ValueError):
        to_dt   = datetime.utcnow()
        from_dt = to_dt.replace(day=1)

    series = alert_repo.get_timeline(from_dt=from_dt, to_dt=to_dt, bucket=bucket)
    return jsonify({"series": series, "bucket": bucket,
                    "from": from_dt.isoformat(), "to": to_dt.isoformat()})


@bp.route("/api/alerts/<alert_id>/resolve", methods=["POST"])
def api_resolve(alert_id: str):
    body        = request.json or {}
    resolved_by = body.get("resolved_by", "").strip()
    note        = body.get("note", "").strip()
    if not resolved_by:
        return jsonify({"status": "error", "message": "resolved_by is required"}), 400
    ok = resolve_alert(alert_id, resolved_by, note)
    return jsonify({"status": "ok" if ok else "error",
                    "message": "" if ok else "Alert not found"})


@bp.route("/api/alerts/clear", methods=["POST"])
def api_clear():
    clear_all_alerts()
    return jsonify({"status": "ok"})
