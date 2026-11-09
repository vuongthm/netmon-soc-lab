# routes/ai_agent.py

from flask import Blueprint, jsonify, render_template, request

from services.ai_service import chat, reset_conversation, run_anomaly_scan, get_model_status
from services.collector  import collect_all

bp = Blueprint("ai_agent", __name__)


@bp.route("/ai")
def ai_page():
    return render_template("ai_agent.html")


@bp.route("/api/ai/status")
def api_status():
    models = get_model_status()
    return jsonify({
        "models":  models,
        "loaded":  sum(1 for v in models.values() if v),
        "total":   len(models),
        "groq_ok": bool(__import__("config").GROQ_API_KEY),
    })


@bp.route("/api/ai/scan")
def api_scan():
    try:
        snapshots = collect_all()
        anomalies = run_anomaly_scan(snapshots)
        return jsonify({"status": "ok", "total": len(anomalies), "anomalies": anomalies})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@bp.route("/api/ai/chat", methods=["POST"])
def api_chat():
    question = (request.json or {}).get("question", "").strip()
    if not question:
        return jsonify({"status": "error", "message": "question is required"}), 400
    result = chat(question)
    return jsonify({"status": "ok", **result})


@bp.route("/api/ai/chat/reset", methods=["POST"])
def api_reset():
    reset_conversation()
    return jsonify({"status": "ok"})
