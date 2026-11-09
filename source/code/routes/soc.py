# routes/soc.py
import traceback
from flask import Blueprint, jsonify, render_template, request
from services import suricata as svc
import config

bp = Blueprint("soc", __name__)


@bp.route("/soc")
def soc_page():
    return render_template("soc.html")


@bp.route("/api/soc/stats")
def api_stats():
    try:
        hours = int(request.args.get("hours", 24))
        return jsonify(svc.get_stats(hours=hours))
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/soc/events")
def api_events():
    try:
        events = svc.get_events(
            limit          = min(int(request.args.get("limit", 100)), 500),
            severity       = request.args.get("severity")  or None,
            category       = request.args.get("category")  or None,
            src_ip         = request.args.get("src_ip")    or None,
            zone           = request.args.get("zone")      or None,
            interface_name = request.args.get("interface") or None,
            hours          = min(int(request.args.get("hours", 24)), 168),
        )
        return jsonify({"total": len(events), "events": events})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/soc/timeline")
def api_timeline():
    try:
        timeline = svc.get_timeline(
            hours          = int(request.args.get("hours", 24)),
            bucket_minutes = int(request.args.get("bucket_minutes", 60)),
        )
        return jsonify({"timeline": timeline})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/soc/attacker/<path:src_ip>")
def api_attacker(src_ip: str):
    # path: cho phép IP có dấu chấm không bị Flask cắt nhầm
    try:
        detail = svc.get_attacker_detail(src_ip)
        if not detail.get("total_events"):
            return jsonify({"error": f"Không có event nào từ IP {src_ip}"}), 404
        return jsonify(detail)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/soc/interfaces")
def api_interfaces():
    try:
        return jsonify({
            "interfaces": [
                {
                    "name":    i["name"],
                    "zone":    i.get("zone", "unknown"),
                    "enabled": i.get("enabled", True),
                }
                for i in config.SURICATA_INTERFACES
            ]
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500