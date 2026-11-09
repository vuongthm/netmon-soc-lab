# services/checker.py
# =============================================================================
# Kiểm tra sức khỏe các endpoint: HTTP/HTTPS, DNS, TCP, Ping.
# Kết quả được lưu vào DB qua repository.
# =============================================================================

import socket
import subprocess
from datetime import datetime, timedelta
from services.timezone import now_vn_naive

import requests

import config
from database.repository import service_repo

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Check implementations — mỗi hàm độc lập, dễ test riêng lẻ
# ---------------------------------------------------------------------------

def _check_ping(target: str, timeout: int = 3) -> dict:
    try:
        rc = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), target],
            capture_output=True, timeout=timeout + 2,
        ).returncode
        return {"status": "up" if rc == 0 else "down",
                "latency_ms": None,
                "error": None if rc == 0 else "timeout"}
    except Exception as exc:
        return {"status": "down", "latency_ms": None, "error": str(exc)[:80]}


def _check_http(target: str, timeout: int = 5) -> dict:
    try:
        r  = requests.get(target, timeout=timeout, verify=False, allow_redirects=True)
        up = r.status_code < 500
        return {
            "status":      "up" if up else "down",
            "status_code": r.status_code,
            "latency_ms":  round(r.elapsed.total_seconds() * 1000, 1),
            "error":       None if up else f"HTTP {r.status_code}",
        }
    except requests.exceptions.SSLError:
        return {"status": "up", "status_code": None, "latency_ms": None, "error": "self-signed cert"}
    except requests.exceptions.ConnectionError:
        return {"status": "down", "status_code": None, "latency_ms": None, "error": "connection refused"}
    except requests.exceptions.Timeout:
        return {"status": "down", "status_code": None, "latency_ms": None, "error": "timeout"}
    except Exception as exc:
        return {"status": "down", "status_code": None, "latency_ms": None, "error": str(exc)[:80]}


def _check_tcp(target: str, port: int, timeout: int = 5) -> dict:
    try:
        start = datetime.now()
        sock  = socket.create_connection((target, port), timeout=timeout)
        ms    = (datetime.now() - start).total_seconds() * 1000
        try:
            sock.settimeout(1)
            banner = sock.recv(256).decode(errors="ignore").strip()[:60]
        except Exception:
            banner = ""
        sock.close()
        return {"status": "up", "latency_ms": round(ms, 1), "banner": banner, "error": None}
    except socket.timeout:
        return {"status": "down", "latency_ms": None, "error": f"port {port} timeout"}
    except ConnectionRefusedError:
        return {"status": "down", "latency_ms": None, "error": f"port {port} refused"}
    except Exception as exc:
        return {"status": "down", "latency_ms": None, "error": str(exc)[:80]}


def _check_dns(target: str, query_name: str = "google.com", timeout: int = 5) -> dict:
    try:
        import dns.resolver
        res             = dns.resolver.Resolver()
        res.nameservers = [target]
        res.lifetime    = float(timeout)
        start   = datetime.now()
        answers = res.resolve(query_name, "A")
        ms      = (datetime.now() - start).total_seconds() * 1000
        return {
            "status":     "up",
            "latency_ms": round(ms, 1),
            "resolved":   [str(a) for a in answers][:3],
            "error":      None,
        }
    except ImportError:
        try:
            rc = subprocess.run(
                ["nslookup", query_name, target],
                capture_output=True, timeout=timeout + 2,
            ).returncode
            return {"status": "up" if rc == 0 else "down", "latency_ms": None,
                    "resolved": [], "error": None if rc == 0 else "nslookup failed"}
        except Exception as exc:
            return {"status": "down", "latency_ms": None, "resolved": [], "error": str(exc)[:80]}
    except Exception as exc:
        return {"status": "down", "latency_ms": None, "resolved": [], "error": str(exc)[:80]}


# ---------------------------------------------------------------------------
# Dispatch table — thêm check type mới chỉ cần thêm ở đây
# ---------------------------------------------------------------------------
_DISPATCH = {
    "http":  lambda svc: _check_http(svc["target"], svc.get("timeout", 5)),
    "https": lambda svc: _check_http(svc["target"], svc.get("timeout", 5)),
    "tcp":   lambda svc: _check_tcp(svc["target"], svc.get("port", 80), svc.get("timeout", 5)),
    "dns":   lambda svc: _check_dns(svc["target"], svc.get("query", "google.com"), svc.get("timeout", 5)),
    "ping":  lambda svc: _check_ping(svc["target"], svc.get("timeout", 3)),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_all() -> list[dict]:
    """
    Kiểm tra tất cả services trong config.SERVICES.
    Lưu kết quả vào DB và trả về list kết quả.
    """
    results = []
    for svc in config.SERVICES:
        handler = _DISPATCH.get(svc["type"])
        check   = handler(svc) if handler else {"status": "unknown", "error": "unsupported type"}

        result = {
            "name":       svc["name"],
            "type":       svc["type"],
            "target":     svc["target"],
            "port":       svc.get("port"),
            "owner":      svc.get("owner", ""),
            "checked_at": now_vn_naive().isoformat(),
            **check,
        }
        results.append(result)
        service_repo.save(result)

    return results


def get_latest() -> list[dict]:
    """Lấy kết quả check mới nhất từ DB."""
    return service_repo.get_latest()


def get_uptime(name: str, hours: int = 24) -> float:
    """Tính % uptime của service trong N giờ."""
    return service_repo.get_uptime_pct(name, hours)
