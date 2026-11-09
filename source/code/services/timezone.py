# services/timezone.py
# =============================================================================
# Timezone helper — nguồn duy nhất cho thời gian trong toàn project.
#
# Vấn đề:
#   - datetime.utcnow() → giờ UTC → lệch 7 tiếng so với Việt Nam
#   - datetime.now()    → giờ máy local (đúng nếu máy set timezone VN)
#
# Giải pháp: dùng timezone-aware datetime với Asia/Ho_Chi_Minh.
# Lợi ích:
#   - Hiển thị đúng giờ VN trên dashboard
#   - Lưu vào PostgreSQL kèm timezone info → không bao giờ nhầm
#   - Khi query cutoff (timedelta) vẫn chính xác
# =============================================================================

from datetime import datetime, timezone, timedelta

# UTC+7 — Việt Nam không có daylight saving, offset cố định
_VN_TZ = timezone(timedelta(hours=7))


def now_vn() -> datetime:
    """
    Trả về datetime hiện tại theo giờ Việt Nam (UTC+7), có timezone info.

    Dùng thay cho datetime.utcnow() và datetime.now() ở mọi nơi trong project.

    Ví dụ:
        from services.timezone import now_vn
        ts = now_vn()
        # → datetime(2025, 4, 27, 13, 20, 0, tzinfo=timezone(timedelta(hours=7)))
    """
    return datetime.now(tz=_VN_TZ)


def now_vn_naive() -> datetime:
    """
    Trả về datetime giờ VN KHÔNG có timezone info (naive).

    Dùng khi lưu vào PostgreSQL column loại TIMESTAMP WITHOUT TIME ZONE
    (SQLAlchemy Column(DateTime) mặc định là without timezone).
    Giá trị lưu vào DB là giờ VN thực tế, không phải UTC.

    Ví dụ:
        created_at = now_vn_naive()
        # → datetime(2025, 4, 27, 13, 20, 0)   ← không có tzinfo
    """
    return datetime.now(tz=_VN_TZ).replace(tzinfo=None)


def cutoff_vn(hours: int = 24) -> datetime:
    """
    Trả về datetime N giờ trước theo giờ VN (naive).
    Dùng để filter DB: WHERE created_at >= cutoff_vn(24).
    """
    return now_vn_naive() - timedelta(hours=hours)


def fmt_vn(dt: datetime | None) -> str:
    """
    Format datetime thành chuỗi hiển thị kiểu Việt Nam.
    Trả về chuỗi rỗng nếu dt là None.

    Ví dụ: "27/04/2025 13:20:05"
    """
    if dt is None:
        return ""
    return dt.strftime("%d/%m/%Y %H:%M:%S")
