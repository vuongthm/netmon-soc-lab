# =============================================================================
# config.py — Toàn bộ cấu hình tập trung tại một nơi duy nhất.
#
# Nguyên tắc:
#   - Thêm thiết bị mới  → chỉ sửa DEVICES
#   - Thêm thành viên    → chỉ sửa MEMBERS
#   - Thêm service check → chỉ sửa SERVICES
#   - Không sửa bất kỳ file nào khác
# =============================================================================

import os

# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------
APP_HOST  = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT  = int(os.getenv("APP_PORT", "5000"))
DEBUG     = os.getenv("DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

# ---------------------------------------------------------------------------
# Database (PostgreSQL)
# ---------------------------------------------------------------------------
DATABASE_URL     = os.getenv("DATABASE_URL", "postgresql://netmon:netmon@localhost:5432/netmon")
DB_POOL_SIZE     = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW  = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT  = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_ECHO          = os.getenv("DB_ECHO", "false").lower() == "true"  # True để debug SQL

# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------
PROMETHEUS_URL   = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "15"))   # giây
CACHE_TTL        = int(os.getenv("CACHE_TTL", "12"))           # giây

# ---------------------------------------------------------------------------
# Thiết bị được giám sát
# ---------------------------------------------------------------------------
# type  : "firewall" | "router" | "switch" | "server"
# role  : sub-type dùng cho UI và logic metrics
# owner : key trong MEMBERS — ai chịu trách nhiệm thiết bị này
DEVICES = [
    {
        "name":        "pfSense",
        "job":         "snmp-pfsense",
        "ip":          "172.24.0.115",
        "type":        "firewall",
        "role":        "firewall",
        "owner":       "tuan",
        "description": "Firewall / NAT / VPN / Suricata IDS",
    },
    {
        "name":        "Core-Router",
        "job":         "snmp-core-router",
        "ip":          "10.20.0.1",
        "type":        "router",
        "role":        "router",
        "owner":       "vuong",
        "description": "Cisco IOSv — OSPF backbone",
    },
    {
        "name":        "SwL3A",
        "job":         "snmp-swl3a",
        "ip":          "10.20.0.2",
        "type":        "switch",
        "role":        "switch",
        "owner":       "vuong",
        "description": "VLAN10 IT · VLAN20 Sales · DHCP",
    },
    {
        "name":        "SwL3B",
        "job":         "snmp-swl3b",
        "ip":          "10.20.0.3",
        "type":        "switch",
        "role":        "switch",
        "owner":       "tuan",
        "description": "VLAN30 HR · VLAN40 Engineering · DHCP",
    },
    {
        "name":        "Server02",
        "job":         "node-server02",
        "ip":          "10.20.200.10",
        "type":        "server",
        "role":        "web",           
        "owner":       "vuong",
        "description": "Web Server (Nginx) — DMZ1",
    },
    {
        "name":        "Server01",
        "job":         "node-server01",
        "ip":          "10.20.201.10",
        "type":        "server",
        "role":        "dns-ftp",       
        "owner":       "vuong",
        "description": "DNS (BIND9) + FTP (vsftpd) — DMZ2",
    },
]


SERVICES = [
    {
        "name":    "pfSense WebGUI",
        "type":    "https",
        "target":  "https://172.24.0.115",
        "timeout": 5,
        "owner":   "tuan",
    },
    # ── Server02 ───────────────────────────────────────────────────
    {
        "name":    "Web (Nginx)",
        "type":    "http",
        "target":  "http://10.20.200.10",
        "timeout": 5,
        "owner":   "vuong",
    },
    # ── Server01 ───────────────────────────────────────────────────
    {
        "name":    "DNS (BIND9)",
        "type":    "dns",
        "target":  "10.20.201.10",
        "query":   "web.lab.local",
        "timeout": 5,
        "owner":   "vuong",
    },
    {
        "name":    "FTP (vsftpd)",
        "type":    "tcp",
        "target":  "10.20.201.10",
        "port":    21,
        "timeout": 5,
        "owner":   "vuong",
    },
]


# ---------------------------------------------------------------------------
# Ngưỡng cảnh báo
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "interface_down":  True,   # Cảnh báo khi interface down (có alias + adminUp)
    "traffic_mbps":    800,    # Cảnh báo khi traffic > N Mbps
    "error_rate_ps":   10,     # Cảnh báo khi error rate > N/s
    "cpu_percent":     85,     # Cảnh báo khi CPU > N%
    "memory_percent":  90,     # Cảnh báo khi RAM > N%
    "disk_percent":    85,     # Cảnh báo khi Disk > N%
}

# ---------------------------------------------------------------------------
# Alert lifecycle
# ---------------------------------------------------------------------------
PING_FAIL_THRESHOLD       = 3    # Cần fail N lần liên tiếp mới raise alert
AUTO_RESOLVE_GRACE        = 300  # Giây chờ trước khi auto-resolve (5 phút)
REMINDER_INTERVAL_SECONDS = 600  # Nhắc lại mỗi N giây nếu chưa resolve
REOPEN_GRACE_SECONDS      = 120  # Giây tối thiểu sau resolve mới tạo alert mới
MAX_ALERTS                = 5000 # Số alert tối đa lưu trong DB (rolling)

# ---------------------------------------------------------------------------
# Suricata IDS
# ---------------------------------------------------------------------------
SURICATA_ENABLED   = os.getenv("SURICATA_ENABLED", "true").lower() == "true"
SURICATA_EVE_PATH  = os.getenv("SURICATA_EVE_PATH", "/var/log/suricata/suricata_vtnet125952/eve.json")
SURICATA_SSH_HOST  = os.getenv("SURICATA_SSH_HOST", "172.24.0.115")
SURICATA_SSH_USER  = os.getenv("SURICATA_SSH_USER", "admin")
SURICATA_SSH_KEY   = os.getenv("SURICATA_SSH_KEY",  "/home/minhvuong/.ssh/id_rsa")
SURICATA_PULL_ROWS = int(os.getenv("SURICATA_PULL_ROWS", "500"))


# Danh sách interface Suricata giám sát trên pfSense.
# Mỗi entry:
#   name     : tên hiển thị trên SOC dashboard
#   eve_path : đường dẫn eve.json trên pfSense
#              pfSense lưu theo thư mục riêng từng interface.
#              Tìm đường dẫn: find /var/log/suricata -name 'eve.json'
#   zone     : vùng mạng (wan / dmz-web / dmz-dns-ftp / lan / zt)
#   enabled  : bật/tắt từng interface riêng lẻ
#
# Thêm interface mới chỉ cần append entry vào list, không sửa code nào khác.
SURICATA_INTERFACES = [
    {
        "name":     "WAN",
        "eve_path": "/var/log/suricata/suricata_vtnet125952/eve.json",
        "zone":     "wan",
        "enabled":  True,
    },
    {
        "name":     "Web-DMZ",
        "eve_path": "/var/log/suricata/suricata_vtnet33887/eve.json",
        "zone":     "dmz-web",
        "enabled":  True,
    },
    {
        "name":     "DNS-FTP",
        "eve_path": "/var/log/suricata/suricata_vtnet450526/eve.json",
        "zone":     "dmz-dns-ftp",
        "enabled":  True,
    },
    {
        "name":     "LAN",
        "eve_path": "/var/log/suricata/suricata_vtnet210674/eve.json",
        "zone":     "lan",
        "enabled":  True,
    },
    {
        "name":     "ZeroTier",
        "eve_path": "/var/log/suricata/suricata_vtnet062106/eve.json",
        "zone":     "zt",
        "enabled":  True,
    },
]
 
# Suricata priority (1=cao nhất) → severity nội bộ
SURICATA_SEVERITY_MAP = {1: "critical", 2: "warning", 3: "info", 4: "info"}
 

# ---------------------------------------------------------------------------
# Thành viên nhóm
# ---------------------------------------------------------------------------
# role     : "leader" nhận tất cả | "member" nhận alert thiết bị mình phụ trách
# notify   : danh sách category/severity muốn nhận thông báo
# channels : kênh nhận thông báo — mở rộng sau (telegram, email, slack)
MEMBERS = {
    "vuong": {
        "name":     "Vuong",
        "role":     "leader",
        "channels": {
            "telegram": {"chat_id": os.getenv("TELEGRAM_VUONG_ID", "")},
        },
        "notify": ["critical", "warning", "ai-anomaly", "suricata",
                   "resolved", "daily-summary", "service-down"],
    },
    "tuan": {
        "name":     "Tuan",
        "role":     "member",
        "channels": {
            "telegram": {"chat_id": os.getenv("TELEGRAM_TUAN_ID", "")},
        },
        "notify": ["critical", "warning", "service-down", "suricata"],
    },
}

# ---------------------------------------------------------------------------
# Notification channels — mở rộng thêm Email/Slack ở đây
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Email (chưa implement — placeholder để sau thêm)
EMAIL_ENABLED  = False
EMAIL_SMTP     = os.getenv("EMAIL_SMTP", "smtp.gmail.com")
EMAIL_PORT     = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER     = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# ---------------------------------------------------------------------------
# AI / Groq
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_ENABLED = bool(GROQ_API_KEY)

# Isolation Forest sensitivity
MIN_TRAFFIC_BPS = 1_000_000
MIN_CPU_PCT     = 5.0
SCORE_WARNING   = -0.30
SCORE_CRITICAL  = -0.55
MODELS_DIR      = "models"

# ---------------------------------------------------------------------------
# Daily summary time
# ---------------------------------------------------------------------------
DAILY_SUMMARY_HOUR   = int(os.getenv("DAILY_SUMMARY_HOUR", "8"))
DAILY_SUMMARY_MINUTE = int(os.getenv("DAILY_SUMMARY_MINUTE", "0"))
