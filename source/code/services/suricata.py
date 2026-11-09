# services/suricata.py
# =============================================================================
# Pull Suricata eve.json từ nhiều interface trên pfSense qua SSH.
#
# Cấu hình interfaces trong config.SURICATA_INTERFACES.
# Mỗi interface pull độc lập, lưu DB với interface_name + zone để phân biệt.
#
# Debug từng bước:
#   python3 -c "from services.suricata import debug_check; debug_check()"
# =============================================================================

import json
import subprocess
from datetime import datetime
from typing import Optional

import config
from database.repository import soc_repo
from services.timezone import now_vn_naive

_CATEGORY_MAP = {
    "A Network Trojan was detected":           "Trojan",
    "Attempted Administrator Privilege Gain":  "Privilege Escalation",
    "Attempted Denial of Service":             "DoS",
    "Attempted Information Leak":              "Recon",
    "Detection of a Network Scan":             "Port Scan",
    "Executable Code was Detected":            "Exploit",
    "Misc Attack":                             "Attack",
    "Potentially Bad Traffic":                 "Suspicious",
    "Successful Administrator Privilege Gain": "Compromise",
    "Web Application Attack":                  "Web Attack",
    "Not Suspicious Traffic":                  "Normal",
    "Unknown Traffic":                         "Unknown",
}


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

def _ssh_base_cmd() -> list[str]:
    """Base SSH command dùng chung cho mọi lần kết nối."""
    return [
        "ssh",
        "-i", config.SURICATA_SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        f"{config.SURICATA_SSH_USER}@{config.SURICATA_SSH_HOST}",
    ]


def _ssh_run(remote_cmd: str, timeout: int = 10) -> tuple[bool, str, str]:
    """
    Chạy 1 lệnh qua SSH. Trả về (success, stdout, stderr).
    """
    try:
        result = subprocess.run(
            _ssh_base_cmd() + [remote_cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "SSH timeout"
    except FileNotFoundError:
        return False, "", "ssh command not found"
    except Exception as exc:
        return False, "", str(exc)


def _pull_eve(eve_path: str) -> Optional[str]:
    """
    Lấy N dòng cuối của 1 file eve.json cụ thể qua SSH.
    Trả về nội dung string hoặc None nếu lỗi.
    """
    rows = config.SURICATA_PULL_ROWS
    ok, stdout, stderr = _ssh_run(
        f"tail -n {rows} {eve_path} 2>/dev/null || echo ''"
    )
    if not ok:
        print(f"[suricata] Pull {eve_path} failed: {stderr[:100]}")
        return None
    return stdout if stdout.strip() else None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_line(line: str, interface_name: str, zone: str) -> Optional[dict]:
    """
    Parse 1 dòng JSON từ eve.json.
    Gắn thêm interface_name và zone vào mỗi event.
    Trả về dict chuẩn hóa hoặc None.
    """
    line = line.strip()
    if not line:
        return None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None

    # Chỉ xử lý event type là alert
    if raw.get("event_type") != "alert":
        return None

    alert_data   = raw.get("alert", {})
    priority     = alert_data.get("severity", 3)
    severity     = config.SURICATA_SEVERITY_MAP.get(priority, "info")
    raw_category = alert_data.get("category", "Unknown")
    http_info    = raw.get("http", {})

    return {
        "timestamp":      raw.get("timestamp", ""),
        "src_ip":         raw.get("src_ip", ""),
        "src_port":       raw.get("src_port", 0),
        "dest_ip":        raw.get("dest_ip", ""),
        "dest_port":      raw.get("dest_port", 0),
        "proto":          raw.get("proto", ""),
        "severity":       severity,
        "priority":       priority,
        "sig_id":         alert_data.get("signature_id", 0),
        "signature":      alert_data.get("signature", ""),
        "category":       _CATEGORY_MAP.get(raw_category, raw_category),
        "raw_category":   raw_category,
        "action":         alert_data.get("action", "allowed"),
        "http_url":       http_info.get("url", ""),
        "http_method":    http_info.get("http_method", ""),
        "http_status":    http_info.get("status", 0),
        "http_host":      http_info.get("hostname", ""),
        # Thông tin nguồn — biết alert đến từ interface nào
        "interface_name": interface_name,
        "zone":           zone,
    }


def _parse_content(content: str, interface_name: str, zone: str) -> list[dict]:
    """Parse toàn bộ nội dung eve.json của 1 interface."""
    return [
        ev for line in content.splitlines()
        if (ev := _parse_line(line, interface_name, zone))
    ]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> Optional[datetime]:
    """
    Chuyển Suricata timestamp string thành naive VN datetime.
    Suricata format: "2025-04-28T13:20:00.123456+0700"
    """
    if not ts_str:
        return None
    try:
        aware = datetime.fromisoformat(ts_str.replace("+0700", "+07:00"))
        return aware.replace(tzinfo=None)  # naive VN time để so sánh với DB
    except Exception:
        return None


def _filter_new(events: list[dict], last_ts: Optional[datetime]) -> list[dict]:
    """
    Bỏ event đã có trong DB (timestamp <= last_ts).
    Nếu last_ts là None (DB trống) → giữ tất cả.
    """
    if not last_ts:
        return events
    new = []
    for ev in events:
        ev_ts = _parse_ts(ev.get("timestamp", ""))
        if ev_ts is None or ev_ts > last_ts:
            new.append(ev)
    return new


# ---------------------------------------------------------------------------
# Main update cycle — gọi từ background worker
# ---------------------------------------------------------------------------

def update_events() -> int:
    """
    Pull events từ TẤT CẢ interface đang enabled, lưu vào DB.
    Trả về tổng số event mới đã lưu.

    Được gọi mỗi 10 giây từ _suricata_worker trong app.py.
    """
    if not config.SURICATA_ENABLED:
        return 0

    interfaces = [i for i in config.SURICATA_INTERFACES if i.get("enabled", True)]
    if not interfaces:
        return 0

    last_ts   = soc_repo.get_latest_timestamp()
    all_new   = []
    total_added = 0

    for iface in interfaces:
        name     = iface["name"]
        eve_path = iface["eve_path"]
        zone     = iface.get("zone", "unknown")

        content = _pull_eve(eve_path)
        if not content:
            continue

        events  = _parse_content(content, name, zone)
        new_evs = _filter_new(events, last_ts)

        if new_evs:
            added = soc_repo.save_many(new_evs)
            total_added += added
            all_new.extend(new_evs)

            if added > 0:
                print(f"[suricata:{name}] +{added} events (zone={zone})")

    # Fire alert cho critical events
    if all_new:
        _handle_critical(all_new)

    return total_added


def _handle_critical(events: list[dict]) -> None:
    """Gửi alert cho mọi critical Suricata event."""
    from services.alerting import fire_suricata_alert
    for ev in events:
        if ev.get("severity") == "critical":
            fire_suricata_alert(ev)


# ---------------------------------------------------------------------------
# Debug — kiểm tra từng bước
# ---------------------------------------------------------------------------

def debug_check() -> None:
    """
    Kiểm tra toàn bộ pipeline. Chạy:
        python3 -c "from services.suricata import debug_check; debug_check()"
    """
    import os

    # Load .env nếu chưa load
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

    print("=" * 60)
    print("  Suricata Multi-Interface Debug Check")
    print("=" * 60)
    print(f"  SURICATA_ENABLED  : {config.SURICATA_ENABLED}")
    print(f"  SURICATA_SSH_HOST : {config.SURICATA_SSH_HOST}")
    print(f"  SURICATA_SSH_USER : {config.SURICATA_SSH_USER}")
    print(f"  SURICATA_SSH_KEY  : {config.SURICATA_SSH_KEY}")
    print(f"  Interfaces        : {len(config.SURICATA_INTERFACES)} configured")
    print()

    # Bước 1: SSH key
    if not os.path.exists(config.SURICATA_SSH_KEY):
        print(f"❌ SSH key không tồn tại: {config.SURICATA_SSH_KEY}")
        print("   Tạo: ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ''")
        return
    print(f"✅ SSH key: {config.SURICATA_SSH_KEY}")

    # Bước 2: Test SSH
    print("\n[Bước 2] Test SSH kết nối...")
    ok, stdout, stderr = _ssh_run("echo SSH_OK")
    if not ok or "SSH_OK" not in stdout:
        print(f"❌ SSH thất bại: {stderr[:150]}")
        print(f"   Test thủ công: ssh -i {config.SURICATA_SSH_KEY} {config.SURICATA_SSH_USER}@{config.SURICATA_SSH_HOST}")
        return
    print("✅ SSH kết nối OK")

    # Bước 3: Kiểm tra từng interface
    print(f"\n[Bước 3] Kiểm tra {len(config.SURICATA_INTERFACES)} interface(s)...")
    print()

    total_alerts = 0
    for iface in config.SURICATA_INTERFACES:
        name     = iface["name"]
        eve_path = iface["eve_path"]
        zone     = iface.get("zone", "unknown")
        enabled  = iface.get("enabled", True)

        status = "enabled" if enabled else "DISABLED"
        print(f"  ── [{name}] zone={zone} ({status}) ──")
        print(f"     path: {eve_path}")

        if not enabled:
            print("     ⏭️  Bỏ qua (disabled)")
            print()
            continue

        # Kiểm tra file tồn tại
        ok, stdout, stderr = _ssh_run(f"ls -lh {eve_path} 2>&1 || echo FILE_NOT_FOUND")
        if "FILE_NOT_FOUND" in stdout or "No such file" in stdout:
            print(f"     ❌ File không tồn tại!")
            print(f"        Cần bật EVE JSON Log trong pfSense:")
            print(f"        Services → Suricata → Interfaces → [{name}] → Edit")
            print(f"        → EVE JSON Log: ✅ → EVE Log Alerts: ✅ → Save → Restart")

            # Tự tìm đường dẫn đúng
            ok2, out2, _ = _ssh_run("find /var/log/suricata -name 'eve.json' 2>/dev/null")
            if out2.strip():
                paths = out2.strip().splitlines()
                print(f"\n     💡 Tìm thấy {len(paths)} file eve.json trên pfSense:")
                for p in paths:
                    print(f"        {p}")
                print(f"\n     → Cập nhật eve_path trong config.SURICATA_INTERFACES")
        else:
            print(f"     ✅ File tồn tại: {stdout.strip()[:80]}")

            # Đọc và parse
            content = _pull_eve(eve_path)
            if not content:
                print("     ⚠️  File rỗng hoặc không đọc được")
                print()
                continue

            lines  = [l for l in content.splitlines() if l.strip()]
            events = _parse_content(content, name, zone)

            # Đếm event types
            types: dict = {}
            for line in lines:
                try:
                    d  = json.loads(line)
                    et = d.get("event_type", "?")
                    types[et] = types.get(et, 0) + 1
                except Exception:
                    types["parse_error"] = types.get("parse_error", 0) + 1

            print(f"     ✅ {len(lines)} dòng | {len(events)} alerts")
            type_str = ", ".join(f"{k}:{v}" for k, v in sorted(types.items(), key=lambda x:-x[1])[:4])
            print(f"     📊 Event types: {type_str}")

            total_alerts += len(events)

            if events:
                sev_count: dict = {}
                for ev in events:
                    s = ev.get("severity", "?")
                    sev_count[s] = sev_count.get(s, 0) + 1
                sev_str = " | ".join(f"{k}:{v}" for k, v in sev_count.items())
                print(f"     🚨 Severity: {sev_str}")

                print(f"     📋 3 alerts gần nhất:")
                for ev in events[-3:]:
                    ts = ev.get("timestamp", "")[:19].replace("T", " ")
                    print(f"        [{ev['severity'].upper()}] {ev['src_ip']} → {ev['dest_ip']}:{ev['dest_port']}")
                    print(f"        {ev['signature'][:65]}")
                    print(f"        {ts}")
            else:
                print("     ℹ️  Chưa có alert — tạo traffic để test:")
                print("        nmap -sV -p 1-1000 <target_ip>")
        print()

    print("=" * 60)
    print(f"  Tổng: {total_alerts} alerts từ tất cả interfaces")
    print("=" * 60)

    if total_alerts == 0:
        print("\n  Gợi ý tạo traffic test:")
        print("  # Từ máy Attacker (Ubuntu VLAN10):")
        print("  nmap -sV -p 1-1000 10.20.200.10")
        print("  curl 'http://10.20.200.10/?id=1 OR 1=1'")
        print("  # Rồi chạy debug lại sau 15 giây")


# ---------------------------------------------------------------------------
# Query API — routes gọi vào đây
# ---------------------------------------------------------------------------

def get_events(**kwargs) -> list[dict]:
    return soc_repo.get_many(**kwargs)

def get_stats(hours: int = 24) -> dict:
    return soc_repo.get_stats(hours=hours)

def get_timeline(hours: int = 24, bucket_minutes: int = 60) -> list[dict]:
    return soc_repo.get_timeline(hours=hours, bucket_minutes=bucket_minutes)

def get_attacker_detail(src_ip: str) -> dict:
    return soc_repo.get_attacker_detail(src_ip)