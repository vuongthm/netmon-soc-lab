# services/collector.py
# =============================================================================
# Thu thập metrics từ Prometheus. Module này chỉ fetch và structure data.
# Không chứa alert logic — đó là việc của alerting.py.
# =============================================================================

import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SKIP_IFACES = frozenset({"Null0", "NVI0", "Nu0", "lo0", "lo"})

# ---------------------------------------------------------------------------
# Ping cache — tránh ping liên tục mỗi 15s
# ---------------------------------------------------------------------------
_ping_cache: dict[str, tuple[bool, float]] = {}
_ping_lock  = threading.Lock()


def _ping(ip: str, timeout: int = 2) -> bool:
    now = time.time()
    with _ping_lock:
        cached = _ping_cache.get(ip)
        if cached and (now - cached[1]) < config.CACHE_TTL:
            return cached[0]

    try:
        rc = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), ip],
            capture_output=True, timeout=timeout + 1,
        ).returncode
        alive = rc == 0
    except Exception:
        alive = False

    with _ping_lock:
        _ping_cache[ip] = (alive, time.time())
    return alive


def _ping_all(devices: list[dict]) -> dict[str, bool]:
    """Ping song song tất cả devices."""
    with ThreadPoolExecutor(max_workers=min(len(devices), 20)) as pool:
        futures = {pool.submit(_ping, d["ip"]): d["ip"] for d in devices}
        return {
            futures[f]: (f.result() if not f.exception() else False)
            for f in as_completed(futures)
        }


# ---------------------------------------------------------------------------
# Prometheus helpers
# ---------------------------------------------------------------------------

def prometheus_alive() -> bool:
    try:
        return requests.get(f"{config.PROMETHEUS_URL}/-/healthy", timeout=3).status_code == 200
    except Exception:
        return False


def prom_query(promql: str) -> list:
    """Instant query. Trả về result list hoặc []."""
    try:
        r = requests.get(
            f"{config.PROMETHEUS_URL}/api/v1/query",
            params={"query": promql}, timeout=5,
        )
        d = r.json()
        return d["data"]["result"] if d.get("status") == "success" else []
    except Exception:
        return []


def prom_val(promql: str) -> float | None:
    """Trả về scalar float từ kết quả đầu tiên, hoặc None."""
    try:
        res = prom_query(promql)
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def prom_range(promql: str, minutes: int = 60, step: str = "1m") -> list:
    """Range query cho charts."""
    try:
        end   = time.time()
        start = end - minutes * 60
        r = requests.get(
            f"{config.PROMETHEUS_URL}/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
            timeout=8,
        )
        d = r.json()
        return d["data"]["result"] if d.get("status") == "success" else []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Device-specific metric fetchers
# ---------------------------------------------------------------------------

def _fetch_interfaces(job: str) -> tuple[list, dict]:
    """
    Trả về (interfaces, admin_status_map).
    interfaces: list dict với name, alias, index, status, admin_status, speed_mbps.
    """
    oper  = prom_query(f'ifOperStatus{{job="{job}"}}')
    admin = prom_query(f'ifAdminStatus{{job="{job}"}}')
    speed = prom_query(f'ifHighSpeed{{job="{job}"}}')

    admin_map = {r["metric"].get("ifIndex", ""): int(float(r["value"][1])) for r in admin}
    speed_map = {r["metric"].get("ifIndex", ""): int(float(r["value"][1])) for r in speed}

    ifaces = []
    for r in oper:
        m    = r["metric"]
        name = m.get("ifDescr") or m.get("ifName", "unknown")
        if name in _SKIP_IFACES:
            continue
        idx = m.get("ifIndex", "")
        ifaces.append({
            "name":         name,
            "alias":        m.get("ifAlias", ""),
            "index":        idx,
            "status":       int(float(r["value"][1])),
            "admin_status": admin_map.get(idx, 1),
            "speed_mbps":   speed_map.get(idx, 0),
        })

    return sorted(ifaces, key=lambda x: x["name"]), admin_map


def _fetch_traffic(job: str) -> list:
    """Traffic in/out bps mỗi interface (5m irate)."""
    in_r  = prom_query(f'irate(ifHCInOctets{{job="{job}"}}[5m])*8')
    out_r = prom_query(f'irate(ifHCOutOctets{{job="{job}"}}[5m])*8')
    traffic: dict = {}

    def _add(results, key):
        for r in results:
            m = r["metric"]
            n = m.get("ifDescr") or m.get("ifName", "")
            if n in _SKIP_IFACES:
                continue
            idx = m.get("ifIndex", "")
            traffic.setdefault(idx, {"name": n, "alias": m.get("ifAlias", ""),
                                     "in_bps": 0.0, "out_bps": 0.0})
            traffic[idx][key] = float(r["value"][1])

    _add(in_r,  "in_bps")
    _add(out_r, "out_bps")
    return list(traffic.values())


def _fetch_errors(job: str) -> list:
    """Error/discard rate (irate 5m) mỗi interface."""
    errors: dict = {}

    def _add(results, key):
        for r in results:
            m = r["metric"]
            n = m.get("ifDescr") or m.get("ifName", "")
            if n in _SKIP_IFACES:
                continue
            idx = m.get("ifIndex", "")
            errors.setdefault(idx, {"name": n, "in_errors": 0.0, "out_errors": 0.0,
                                    "in_discards": 0.0, "out_discards": 0.0})
            errors[idx][key] = float(r["value"][1])

    _add(prom_query(f'irate(ifInErrors{{job="{job}"}}[5m])'),    "in_errors")
    _add(prom_query(f'irate(ifOutErrors{{job="{job}"}}[5m])'),   "out_errors")
    _add(prom_query(f'irate(ifInDiscards{{job="{job}"}}[5m])'),  "in_discards")
    _add(prom_query(f'irate(ifOutDiscards{{job="{job}"}}[5m])'), "out_discards")
    return list(errors.values())


def _fetch_server_metrics(job: str) -> dict:
    """CPU, RAM, disk, network, service-level metrics cho Linux server."""
    v = prom_val  # shorthand

    cpu = v(f'100-(avg by(instance)(irate(node_cpu_seconds_total{{job="{job}",mode="idle"}}[5m]))*100)')
    mt  = v(f'node_memory_MemTotal_bytes{{job="{job}"}}')
    mf  = v(f'node_memory_MemAvailable_bytes{{job="{job}"}}')
    dt  = v(f'node_filesystem_size_bytes{{job="{job}",mountpoint="/"}}')
    df  = v(f'node_filesystem_free_bytes{{job="{job}",mountpoint="/"}}')
    upt = v(f'node_time_seconds{{job="{job}"}}-node_boot_time_seconds{{job="{job}"}}')
    tcp = v(f'node_netstat_Tcp_CurrEstab{{job="{job}"}}')
    l1  = v(f'node_load1{{job="{job}"}}')
    ni  = v(f'sum(irate(node_network_receive_bytes_total{{job="{job}",device!="lo"}}[5m]))*8')
    no_ = v(f'sum(irate(node_network_transmit_bytes_total{{job="{job}",device!="lo"}}[5m]))*8')

    # Service-level (mtail / nginx-exporter)
    http_rps   = v('sum(rate(http_requests_total{job=~"mtail-nginx.*"}[5m]))')
    dns_qps    = v('sum(rate(dns_queries_total{job=~"mtail-dns.*"}[5m]))')
    nginx_conn = v('nginx_connections_active{job=~"nginx-exporter.*"}')

    def _r(x, n=2): return round(x, n) if x is not None else None
    def _i(x):      return int(x)       if x is not None else None

    return {
        "cpu_percent":      _r(cpu),
        "mem_total_gb":     _r(mt / 1e9) if mt else None,
        "mem_used_percent": _r((1 - mf / mt) * 100) if mt and mf else None,
        "disk_total_gb":    _r(dt / 1e9) if dt else None,
        "disk_used_percent":_r((1 - df / dt) * 100) if dt and df else None,
        "uptime_seconds":   upt,
        "load1":            _r(l1),
        "tcp_connections":  _i(tcp),
        "net_in_bps":       _r(ni,  0),
        "net_out_bps":      _r(no_, 0),
        "http_rps":         _r(http_rps),
        "dns_qps":          _r(dns_qps),
        "nginx_active_conn":_i(nginx_conn),
    }


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

def _build_snapshot(device: dict, alive: bool) -> dict:
    """Build complete snapshot cho 1 device từ Prometheus data."""
    snap = {**device}  # copy config fields

    if not alive:
        snap.update(
            status="offline", uptime=None,
            interfaces=[], traffic=[], errors=[],
            server_metrics=None,
        )
        return snap

    job   = device["job"]
    dtype = device["type"]

    if dtype in ("firewall", "router", "switch"):
        ifaces, _ = _fetch_interfaces(job)
        uptime_raw = prom_val(f'sysUpTime{{job="{job}"}}')

        meaningful_down = [
            i for i in ifaces
            if i["status"] == 2
            and i.get("alias", "").strip()
            and i.get("admin_status", 1) == 1
        ]

        snap.update(
            uptime     = uptime_raw / 100 if uptime_raw else None,
            interfaces = ifaces,
            traffic    = _fetch_traffic(job),
            errors     = _fetch_errors(job),
            server_metrics = None,
            status     = "warning" if (meaningful_down or not ifaces) else "up",
        )

    elif dtype == "server":
        sm   = _fetch_server_metrics(job)
        cpu  = sm.get("cpu_percent")  or 0
        mem  = sm.get("mem_used_percent") or 0
        disk = sm.get("disk_used_percent") or 0

        if sm.get("cpu_percent") is None:
            status = "warning"
        elif cpu > 90 or mem > 90 or disk > 90:
            status = "critical"
        elif cpu > 75 or mem > 80 or disk > 80:
            status = "warning"
        else:
            status = "up"

        snap.update(
            uptime         = sm.get("uptime_seconds"),
            interfaces     = [],
            traffic        = [],
            errors         = [],
            server_metrics = sm,
            status         = status,
        )

    return snap


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_all() -> list[dict]:
    """
    Ping song song rồi fetch Prometheus song song cho mọi device.
    Trả về list snapshot đã build.
    """
    devices  = config.DEVICES
    ping_map = _ping_all(devices)
    results  = [None] * len(devices)

    def _worker(idx: int, device: dict):
        alive = ping_map.get(device["ip"], False)
        return idx, _build_snapshot(device, alive)

    with ThreadPoolExecutor(max_workers=min(len(devices), 12)) as pool:
        for future in as_completed(
            {pool.submit(_worker, i, d): i for i, d in enumerate(devices)}
        ):
            try:
                idx, snap = future.result()
                results[idx] = snap
            except Exception as exc:
                print(f"[collector] snapshot error: {exc}")

    return [r for r in results if r is not None]


def collect_charts(job: str, device_type: str, minutes: int = 60) -> dict:
    """Time-series data cho chart rendering."""
    step = "1m" if minutes <= 60 else "5m" if minutes <= 360 else "15m"

    def pts(results):
        if not results:
            return []
        return [[float(v[0]) * 1000, float(v[1])] for v in results[0].get("values", [])]

    charts: dict = {}
    r = prom_range  # shorthand

    if device_type in ("firewall", "router", "switch"):
        charts["traffic_in"]  = pts(r(f'sum(irate(ifHCInOctets{{job="{job}"}}[5m]))*8',  minutes, step))
        charts["traffic_out"] = pts(r(f'sum(irate(ifHCOutOctets{{job="{job}"}}[5m]))*8', minutes, step))
        charts["errors"]      = pts(r(f'sum(irate(ifInErrors{{job="{job}"}}[5m]))',       minutes, step))

    elif device_type == "server":
        charts["cpu"]      = pts(r(f'100-(avg by(instance)(irate(node_cpu_seconds_total{{job="{job}",mode="idle"}}[5m]))*100)', minutes, step))
        charts["mem"]      = pts(r(f'(1-node_memory_MemAvailable_bytes{{job="{job}"}}/node_memory_MemTotal_bytes{{job="{job}"}})*100', minutes, step))
        charts["disk"]     = pts(r(f'(1-node_filesystem_free_bytes{{job="{job}",mountpoint="/"}}/node_filesystem_size_bytes{{job="{job}",mountpoint="/"}})*100', minutes, step))
        charts["net_in"]   = pts(r(f'sum(irate(node_network_receive_bytes_total{{job="{job}",device!="lo"}}[5m]))*8', minutes, step))
        charts["net_out"]  = pts(r(f'sum(irate(node_network_transmit_bytes_total{{job="{job}",device!="lo"}}[5m]))*8', minutes, step))
        charts["load"]     = pts(r(f'node_load1{{job="{job}"}}', minutes, step))
        charts["http_rps"] = pts(r('sum(rate(http_requests_total{job=~"mtail-nginx.*"}[1m]))', minutes, step))
        charts["dns_qps"]  = pts(r('sum(rate(dns_queries_total{job=~"mtail-dns.*"}[1m]))',     minutes, step))

    return charts


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_uptime(seconds) -> str:
    if seconds is None:
        return "N/A"
    s = int(seconds)
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
    if d: return f"{d}d {h}h {m}m"
    if h: return f"{h}h {m}m"
    return f"{m}m"


def fmt_bps(bps) -> str:
    if bps is None:
        return "N/A"
    if bps >= 1e9: return f"{bps / 1e9:.2f} Gbps"
    if bps >= 1e6: return f"{bps / 1e6:.2f} Mbps"
    if bps >= 1e3: return f"{bps / 1e3:.2f} Kbps"
    return f"{bps:.0f} bps"


def build_prometheus_context() -> tuple[str, bool, bool]:
    """
    Build context string từ Prometheus data cho AI chatbot.
    Trả về (context_text, prometheus_alive, has_data).
    """
    if not prometheus_alive():
        return "ERROR: Prometheus is not responding.", False, False

    lines    = [f"LIVE SYSTEM DATA ({__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S})\n"]
    has_data = False

    for device in config.DEVICES:
        name, job, dtype = device["name"], device["job"], device["type"]
        lines.append(f"\n[{name}] type={dtype} ip={device['ip']}")

        if dtype in ("firewall", "router", "switch"):
            uptime = prom_val(f'sysUpTime{{job="{job}"}}')
            if uptime:
                s = int(uptime / 100)
                lines.append(f"  uptime: {s // 86400}d {(s % 86400) // 3600}h")
                has_data = True

            iup   = prom_query(f'ifOperStatus{{job="{job}"}} == 1')
            idown = prom_query(f'ifOperStatus{{job="{job}"}} == 2')
            skip  = _SKIP_IFACES

            if iup or idown:
                has_data = True
                up_names   = [r["metric"].get("ifDescr", "?") for r in iup   if r["metric"].get("ifDescr") not in skip]
                down_names = [r["metric"].get("ifDescr", "?") for r in idown if r["metric"].get("ifDescr") not in skip]
                if up_names:   lines.append(f"  interfaces UP: {', '.join(up_names)}")
                if down_names: lines.append(f"  interfaces DOWN: {', '.join(down_names)} <ALERT>")

            tin  = prom_val(f'sum(irate(ifHCInOctets{{job="{job}"}}[5m]))*8')
            tout = prom_val(f'sum(irate(ifHCOutOctets{{job="{job}"}}[5m]))*8')
            if tin is not None:
                lines.append(f"  traffic: in={fmt_bps(tin)} out={fmt_bps(tout or 0)}")

        elif dtype == "server":
            sm = _fetch_server_metrics(job)
            if sm.get("cpu_percent") is not None:
                has_data = True
                lines.append(f"  cpu={sm['cpu_percent']:.1f}%{' <HIGH>' if sm['cpu_percent'] > 80 else ''}")
                if sm.get("mem_used_percent"):
                    lines.append(f"  ram={sm['mem_used_percent']:.1f}%{' <HIGH>' if sm['mem_used_percent'] > 85 else ''}")
                if sm.get("disk_used_percent"):
                    lines.append(f"  disk={sm['disk_used_percent']:.1f}%{' <HIGH>' if sm['disk_used_percent'] > 85 else ''}")
            else:
                lines.append("  NO DATA — Node Exporter may not be running")

    return "\n".join(lines), True, has_data
