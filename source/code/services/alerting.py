# services/alerting.py
import threading
import uuid
from datetime import timedelta
from typing import Optional

import config
from database.repository import alert_repo
from services.notifications import notifier
from services.timezone import now_vn_naive

_state: dict[str, dict] = {}
_lock  = threading.Lock()


def _make_key(device: str, category: str, sub: str = "") -> str:
    return f"{device}::{category}::{sub}"


def _init_state() -> dict:
    now = now_vn_naive()
    return {
        "confirmed":      False,
        "fail_count":     0,
        "first_seen":     now,
        "fired_at":       None,
        "resolved":       False,
        "resolved_at":    None,
        "last_reminder":  now,
        "grace_deadline": None,
    }


def _make_alert_record(device: str, severity: str, category: str,
                       message: str, details: str = "", sub_key: str = "") -> dict:
    return {
        "id":         str(uuid.uuid4()),
        "created_at": now_vn_naive().isoformat(),
        "device":     device,
        "severity":   severity,
        "category":   category,
        "message":    message,
        "details":    details,
        "sub_key":    sub_key,
        "resolved":   False,
    }


def _increment_fail(key: str) -> int:
    with _lock:
        if key not in _state:
            _state[key] = _init_state()
        st = _state[key]
        if st["resolved"] and st["resolved_at"]:
            elapsed = (now_vn_naive() - st["resolved_at"]).total_seconds()
            if elapsed >= config.REOPEN_GRACE_SECONDS:
                _state[key] = _init_state()
                st = _state[key]
            else:
                return 0
        st["fail_count"] += 1
        return st["fail_count"]


def _clear_fail(key: str) -> None:
    with _lock:
        if key not in _state:
            return
        st = _state[key]
        st["fail_count"] = 0
        if st["confirmed"] and not st["resolved"] and st["grace_deadline"] is None:
            st["grace_deadline"] = now_vn_naive() + timedelta(seconds=config.AUTO_RESOLVE_GRACE)


def _should_fire(key: str, threshold: int) -> bool:
    with _lock:
        st = _state.get(key)
        if not st or st["confirmed"] or st["fail_count"] < threshold:
            return False
        st["confirmed"] = True
        st["fired_at"]  = now_vn_naive()
        return True


def _should_remind(key: str) -> bool:
    with _lock:
        st = _state.get(key)
        if not st or not st["confirmed"] or st["resolved"]:
            return False
        elapsed = (now_vn_naive() - st["last_reminder"]).total_seconds()
        if elapsed >= config.REMINDER_INTERVAL_SECONDS:
            st["last_reminder"] = now_vn_naive()
            return True
        return False


def _mark_resolved(key: str, mode: str) -> None:
    with _lock:
        if key in _state:
            _state[key]["resolved"]       = True
            _state[key]["resolved_at"]    = now_vn_naive()
            _state[key]["grace_deadline"] = None


def _sweep_auto_resolve(active_keys: set) -> None:
    now        = now_vn_naive()
    candidates = []
    with _lock:
        for key, st in _state.items():
            if (st["confirmed"] and not st["resolved"]
                    and key not in active_keys
                    and st.get("grace_deadline")
                    and now >= st["grace_deadline"]):
                candidates.append(key)
    for key in candidates:
        _mark_resolved(key, "auto")
        resolved_list = alert_repo.resolve_by_subkey(key, mode="auto")
        for alert in resolved_list:
            notifier.send_resolved(alert, "system", "Condition cleared automatically")


def _should_alert_iface(iface: dict) -> bool:
    return (
        bool(iface.get("alias", "").strip())
        and iface.get("admin_status", 1) == 1
        and iface.get("status") == 2
    )


def check_and_fire(snapshots: list[dict]) -> list[dict]:
    new_alerts:  list = []
    active_keys: set  = set()

    for snap in snapshots:
        name = snap["name"]

        if snap.get("status") == "offline":
            key = _make_key(name, "offline")
            active_keys.add(key)
            _increment_fail(key)
            if _should_fire(key, config.PING_FAIL_THRESHOLD):
                alert = _make_alert_record(
                    device=name, severity="critical", category="offline",
                    message=f"Device unreachable — ping failed {config.PING_FAIL_THRESHOLD}× ({snap['ip']})",
                    sub_key=key)
                new_alerts.append(alert)
                notifier.send_alert(alert, notify_leader=True)
            elif _should_remind(key):
                existing = alert_repo.get_active_by_subkey(key)
                if existing:
                    notifier.send_reminder(existing)
        else:
            _clear_fail(_make_key(name, "offline"))

        if config.THRESHOLDS.get("interface_down"):
            for iface in snap.get("interfaces", []):
                if not _should_alert_iface(iface):
                    _clear_fail(_make_key(name, "iface-down", iface["name"]))
                    continue
                key = _make_key(name, "iface-down", iface["name"])
                active_keys.add(key)
                _increment_fail(key)
                if _should_fire(key, threshold=1):
                    alert = _make_alert_record(
                        device=name, severity="critical", category="interface",
                        message=f"Interface down: {iface['name']} ({iface.get('alias','')})",
                        details="adminStatus=UP operStatus=DOWN", sub_key=key)
                    new_alerts.append(alert)
                    notifier.send_alert(alert, notify_leader=True)
                elif _should_remind(key):
                    existing = alert_repo.get_active_by_subkey(key)
                    if existing:
                        notifier.send_reminder(existing)

        thresh_bps = config.THRESHOLDS.get("traffic_mbps", 800) * 1e6
        for t in snap.get("traffic", []):
            for direction, val in (("in", t.get("in_bps", 0)), ("out", t.get("out_bps", 0))):
                key = _make_key(name, f"traffic-{direction}", t["name"])
                if val > thresh_bps:
                    active_keys.add(key)
                    _increment_fail(key)
                    if _should_fire(key, threshold=2):
                        alert = _make_alert_record(
                            device=name, severity="warning", category="traffic",
                            message=f"High traffic {direction.upper()}: {t['name']} ({val/1e6:.1f} Mbps)",
                            sub_key=key)
                        new_alerts.append(alert)
                        notifier.send_alert(alert, notify_leader=True)
                    elif _should_remind(key):
                        existing = alert_repo.get_active_by_subkey(key)
                        if existing: notifier.send_reminder(existing)
                else:
                    _clear_fail(key)

        err_thresh = config.THRESHOLDS.get("error_rate_ps", 10)
        for e in snap.get("errors", []):
            total_err = e.get("in_errors", 0) + e.get("out_errors", 0)
            key = _make_key(name, "iface-error", e["name"])
            if total_err > err_thresh:
                active_keys.add(key)
                _increment_fail(key)
                if _should_fire(key, threshold=2):
                    alert = _make_alert_record(
                        device=name, severity="warning", category="interface",
                        message=f"High error rate: {e['name']} ({total_err:.2f} err/s)",
                        sub_key=key)
                    new_alerts.append(alert)
                    notifier.send_alert(alert, notify_leader=True)
                elif _should_remind(key):
                    existing = alert_repo.get_active_by_subkey(key)
                    if existing: notifier.send_reminder(existing)
            else:
                _clear_fail(key)

        sm = snap.get("server_metrics")
        if sm:
            checks = [
                ("cpu",  sm.get("cpu_percent"),       config.THRESHOLDS.get("cpu_percent",    85), "CPU",  "critical"),
                ("mem",  sm.get("mem_used_percent"),  config.THRESHOLDS.get("memory_percent", 90), "RAM",  "critical"),
                ("disk", sm.get("disk_used_percent"), config.THRESHOLDS.get("disk_percent",   85), "Disk", "warning"),
            ]
            for metric, val, thresh, label, sev in checks:
                key = _make_key(name, f"server-{metric}")
                if val is not None and val > thresh:
                    active_keys.add(key)
                    _increment_fail(key)
                    if _should_fire(key, threshold=2):
                        alert = _make_alert_record(
                            device=name, severity=sev, category="server",
                            message=f"{label} usage high: {val:.1f}%", sub_key=key)
                        new_alerts.append(alert)
                        notifier.send_alert(alert, notify_leader=True)
                    elif _should_remind(key):
                        existing = alert_repo.get_active_by_subkey(key)
                        if existing: notifier.send_reminder(existing)
                else:
                    _clear_fail(key)

    _sweep_auto_resolve(active_keys)
    for alert in new_alerts:
        alert_repo.save(alert)
    return new_alerts


def resolve_alert(alert_id: str, resolved_by: str, note: str = "") -> bool:
    alert = alert_repo.get_by_id(alert_id)
    if not alert:
        return False
    ok = alert_repo.resolve(alert_id, resolved_by, note)
    if ok:
        _mark_resolved(alert.get("sub_key", ""), "human")
        notifier.send_resolved(alert, resolved_by, note)
    return ok


def clear_all_alerts() -> None:
    alert_repo.delete_all()
    with _lock:
        _state.clear()


def fire_suricata_alert(event: dict) -> None:
    key = _make_key("pfSense/IDS", "suricata", str(event.get("sig_id", "")))
    _increment_fail(key)
    if not _should_fire(key, threshold=1):
        return
    alert = _make_alert_record(
        device="pfSense/IDS", severity=event.get("severity", "warning"),
        category="suricata",
        message=f"[IDS] {event.get('signature', '')}",
        details=(f"src={event.get('src_ip')}:{event.get('src_port')} "
                 f"→ {event.get('dest_ip')}:{event.get('dest_port')} "
                 f"({event.get('proto', '')})"),
        sub_key=key)
    alert_repo.save(alert)
    notifier.send_suricata_alert(event)


def get_stats() -> dict:
    stats = alert_repo.get_stats()
    with _lock:
        active = sum(1 for st in _state.values() if st["confirmed"] and not st["resolved"])
    stats["active"] = active
    return stats
