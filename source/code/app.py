# app.py
# =============================================================================
# Entry point của ứng dụng NetMon SOC.
#
# Background threads:
#   _metrics_worker  : Thu thập Prometheus + check alerts (mỗi 15s)
#   _suricata_worker : Pull Suricata events từ pfSense (mỗi 10s)
#   _checker_worker  : Kiểm tra endpoint services (mỗi 30s)
#   _daily_worker    : Gửi báo cáo tổng kết 8:00 sáng
# =============================================================================

import os
import threading
import time
import datetime as dt

# =============================================================================
# PHẢI load .env TRƯỚC KHI import bất cứ thứ gì khác.
# Lý do: config.py dùng os.getenv() ngay lúc import — nếu .env chưa được load
# thì tất cả biến sẽ là None hoặc giá trị mặc định, kể cả DATABASE_URL.
#
# Tìm .env theo vị trí của app.py (không phải thư mục hiện tại khi chạy lệnh)
# → Có thể chạy từ bất kỳ đâu: python /opt/netmon/app.py đều hoạt động đúng.
# =============================================================================

# Thư mục chứa app.py — dùng làm gốc cho mọi đường dẫn tương đối
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env() -> None:
    """
    Load file .env vào os.environ trước khi import config.
    Tìm file .env trong cùng thư mục với app.py.
    Không ghi đè biến đã có trong environment hệ thống.
    """
    env_path = os.path.join(_BASE_DIR, ".env")

    if not os.path.exists(env_path):
        print(f"[env]  Không tìm thấy {env_path}")
        print(f"[env]    Tạo file .env từ mẫu: cp .env.example .env")
        return

    loaded = 0
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            # Bỏ qua dòng trống, comment, dòng không có dấu =
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            # Bỏ dấu nháy đơn/kép bao quanh value nếu có
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            # Không ghi đè biến đã được set bởi hệ thống hoặc systemd
            if key and key not in os.environ:
                os.environ[key] = value
                loaded += 1

    print(f"[env] Đã load {loaded} biến từ {env_path}")


_load_env()   # ← Chạy TRƯỚC MỌI import khác

# Đổi working directory về thư mục chứa app.py
# → Đảm bảo các path tương đối trong code (data/, models/) luôn đúng
os.chdir(_BASE_DIR)

from flask import Flask, render_template

# Tạo thư mục cần thiết
os.makedirs("data",   exist_ok=True)
os.makedirs("models", exist_ok=True)

import config
from database import init_db

# Khởi tạo database tables ngay khi start
init_db()

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ---------------------------------------------------------------------------
# Đăng ký blueprints
# ---------------------------------------------------------------------------
from routes.dashboard import bp as dashboard_bp
from routes.alerts    import bp as alerts_bp
from routes.ai_agent  import bp as ai_bp
from routes.soc       import bp as soc_bp

app.register_blueprint(dashboard_bp)
app.register_blueprint(alerts_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(soc_bp)


@app.route("/")
def landing():
    return render_template("index.html", members=config.MEMBERS, devices=config.DEVICES)


# ---------------------------------------------------------------------------
# Background Workers
# ---------------------------------------------------------------------------

def _metrics_worker():
    """Thu thập metrics và kiểm tra ngưỡng cảnh báo mỗi REFRESH_INTERVAL giây."""
    from services.collector import collect_all
    from services.alerting  import check_and_fire

    time.sleep(8)  # grace period — cho Prometheus khởi động xong
    print("[worker:metrics] started")

    while True:
        try:
            snapshots = collect_all()
            check_and_fire(snapshots)
        except Exception as exc:
            print(f"[worker:metrics] error: {exc}")
        time.sleep(config.REFRESH_INTERVAL)


def _suricata_worker():
    """Pull Suricata IDS events mỗi 10 giây."""
    if not config.SURICATA_ENABLED:
        print("[worker:suricata] disabled")
        return

    from services.suricata import update_events

    time.sleep(15)
    print("[worker:suricata] started")

    while True:
        try:
            added = update_events()
            if added > 0:
                print(f"[worker:suricata] +{added} events")
        except Exception as exc:
            print(f"[worker:suricata] error: {exc}")
        time.sleep(10)


def _checker_worker():
    """Kiểm tra endpoint services mỗi 30 giây."""
    from services.checker import check_all

    time.sleep(20)
    print("[worker:checker] started")

    while True:
        try:
            check_all()
        except Exception as exc:
            print(f"[worker:checker] error: {exc}")
        time.sleep(30)


def _daily_worker():
    """Gửi báo cáo tổng kết hàng ngày lúc cấu hình trong config."""
    from services.notifications import notifier
    from services.alerting      import get_stats
    from services.collector     import collect_all
    from services.checker       import get_latest
    from services.suricata      import get_stats as soc_stats

    while True:
        now      = dt.datetime.now()
        next_run = now.replace(
            hour=config.DAILY_SUMMARY_HOUR,
            minute=config.DAILY_SUMMARY_MINUTE,
            second=0, microsecond=0,
        )
        if now >= next_run:
            next_run += dt.timedelta(days=1)

        sleep_secs = (next_run - now).total_seconds()
        print(f"[worker:daily] next run in {sleep_secs / 3600:.1f}h")
        time.sleep(sleep_secs)

        try:
            snapshots = collect_all()
            stats     = get_stats()
            svcs      = get_latest()
            soc       = soc_stats()

            notifier.send_daily_summary({
                "total":          len(snapshots),
                "up":             sum(1 for s in snapshots if s["status"] == "up"),
                "critical_count": stats["critical"],
                "warning_count":  stats["warning"],
                "svc_down":       sum(1 for s in svcs if s.get("status") != "up"),
                "soc_total":      soc.get("total", 0),
                "soc_critical":   soc.get("critical", 0),
            })
        except Exception as exc:
            print(f"[worker:daily] error: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for target in (_metrics_worker, _suricata_worker, _checker_worker, _daily_worker):
        threading.Thread(target=target, daemon=True).start()

    print(f"[netmon-soc] http://{config.APP_HOST}:{config.APP_PORT}")
    app.run(host=config.APP_HOST, port=config.APP_PORT, debug=config.DEBUG)
