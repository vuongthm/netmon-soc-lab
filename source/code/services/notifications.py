# services/notifications.py
# =============================================================================
# Hệ thống thông báo có thể mở rộng.
#
# Kiến trúc:
#   NotificationChannel (abstract)
#       ├── TelegramChannel
#       ├── EmailChannel      (placeholder, thêm sau)
#       └── SlackChannel      (placeholder, thêm sau)
#
#   NotificationRouter
#       - Nhận alert/event
#       - Tìm thành viên liên quan
#       - Gửi qua đúng channel của từng người
#
# Cách thêm channel mới (ví dụ Email):
#   1. Tạo class EmailChannel(NotificationChannel)
#   2. Implement method send()
#   3. Thêm vào _CHANNEL_REGISTRY
#   Không cần sửa bất kỳ code nào khác.
# =============================================================================

import threading
from abc import ABC, abstractmethod
from typing import Optional

import requests

import config


# =============================================================================
# Abstract base — interface chung cho mọi channel
# =============================================================================

class NotificationChannel(ABC):
    """Mọi notification channel phải implement interface này."""

    @abstractmethod
    def send(self, recipient_config: dict, message: str) -> bool:
        """
        Gửi message đến 1 recipient.

        Args:
            recipient_config: thông tin kết nối của người nhận
                              (ví dụ: {"chat_id": "123"} cho Telegram)
            message: nội dung đã được format sẵn (HTML hoặc plain text)

        Returns:
            True nếu gửi thành công, False nếu thất bại
        """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Tên channel — phải khớp với key trong MEMBERS[x]["channels"]."""


# =============================================================================
# Telegram Channel
# =============================================================================

class TelegramChannel(NotificationChannel):

    channel_name = "telegram"

    def send(self, recipient_config: dict, message: str) -> bool:
        token   = config.TELEGRAM_BOT_TOKEN
        chat_id = recipient_config.get("chat_id", "")

        if not token or not chat_id or "CHAT_ID" in chat_id:
            return False

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as exc:
            print(f"[telegram] send error: {exc}")
            return False


# =============================================================================
# Email Channel (placeholder — thêm logic khi cần)
# =============================================================================

class EmailChannel(NotificationChannel):

    channel_name = "email"

    def send(self, recipient_config: dict, message: str) -> bool:
        if not config.EMAIL_ENABLED:
            return False
        # TODO: implement SMTP send
        # import smtplib
        # from email.mime.text import MIMEText
        # ...
        print(f"[email] not implemented yet — would send to {recipient_config.get('address')}")
        return False


# =============================================================================
# Slack Channel (placeholder)
# =============================================================================

class SlackChannel(NotificationChannel):

    channel_name = "slack"

    def send(self, recipient_config: dict, message: str) -> bool:
        webhook = recipient_config.get("webhook_url", "")
        if not webhook:
            return False
        # TODO: implement Slack webhook
        # requests.post(webhook, json={"text": message})
        print(f"[slack] not implemented yet")
        return False


# =============================================================================
# Registry — map channel_name → instance
# =============================================================================

_CHANNEL_REGISTRY: dict[str, NotificationChannel] = {
    ch.channel_name: ch()
    for ch in [TelegramChannel, EmailChannel, SlackChannel]
}


# =============================================================================
# Message builders — format thông điệp
# =============================================================================

_SEV_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵", "suricata": "🛡️"}
_SEV_LABEL = {"critical": "CRITICAL", "warning": "WARNING", "info": "INFO"}


def _fmt_alert(alert: dict, for_leader: bool = False, responsible_name: str = "") -> str:
    sev    = alert.get("severity", "info")
    emoji  = _SEV_EMOJI.get(sev, "⚪")
    label  = _SEV_LABEL.get(sev, sev.upper())
    ts     = alert.get("timestamp", "")[:19].replace("T", " ")
    device = alert.get("device", "")
    msg    = alert.get("message", "")

    lines = [f"{emoji} <b>[{label}] {device}</b>", msg, f"🕐 {ts}"]
    if for_leader and responsible_name:
        lines.append(f"👤 Responsible: {responsible_name}")
    return "\n".join(lines)


def _fmt_reminder(alert: dict) -> str:
    sev    = alert.get("severity", "info")
    emoji  = _SEV_EMOJI.get(sev, "⚪")
    return (
        f"⏰ <b>[REMINDER] {alert.get('device')}</b>\n"
        f"{alert.get('message')}\n"
        f"<i>Vấn đề chưa được xử lý. Vui lòng kiểm tra.</i>"
    )


def _fmt_resolved(alert: dict, resolved_by: str, note: str = "") -> str:
    from services.timezone import now_vn_naive; ts = now_vn_naive().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f" <b>[RESOLVED] {alert.get('device')}</b>",
        alert.get("message", ""),
        f"👤 Resolved by: <b>{resolved_by}</b>",
    ]
    if note:
        lines.append(f"📝 {note}")
    lines.append(f"🕐 {ts}")
    return "\n".join(lines)


def _fmt_suricata(event: dict) -> str:
    emoji = "🛡️" if event.get("severity") == "critical" else "⚠️"
    return (
        f"{emoji} <b>[IDS ALERT] Suricata</b>\n"
        f"{event.get('signature', '')}\n"
        f"📍 {event.get('src_ip')}:{event.get('src_port')} → "
        f"{event.get('dest_ip')}:{event.get('dest_port')} ({event.get('proto')})\n"
        f"📂 {event.get('category', '')}"
    )


def _fmt_daily(summary: dict) -> str:
    from services.timezone import now_vn_naive; ts = now_vn_naive().strftime("%d/%m/%Y %H:%M")
    return (
        f"📊 <b>[DAILY REPORT] NetMon SOC</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥️  Devices: {summary.get('up', 0)}/{summary.get('total', 0)} online\n"
        f"🔴 Critical alerts: {summary.get('critical_count', 0)}\n"
        f"🟡 Warning alerts:  {summary.get('warning_count', 0)}\n"
        f"🛡️  SOC events: {summary.get('soc_total', 0)} ({summary.get('soc_critical', 0)} critical)\n"
        f"🔌 Services down: {summary.get('svc_down', 0)}\n"
        f"🕐 {ts}"
    )


# =============================================================================
# NotificationRouter — gửi đúng người, đúng channel
# =============================================================================

class NotificationRouter:
    """
    Orchestrator gửi thông báo.
    Biết ai cần nhận gì, không biết chi tiết cách gửi (đó là việc của channel).
    """

    def _get_leader(self) -> Optional[dict]:
        for m in config.MEMBERS.values():
            if m["role"] == "leader":
                return m
        return None

    def _get_owner(self, device_name: str) -> Optional[dict]:
        """Tìm member phụ trách device."""
        for key, device in {d["name"]: d for d in config.DEVICES}.items():
            if key == device_name:
                owner_key = device.get("owner", "")
                return config.MEMBERS.get(owner_key)
        return None

    def _is_subscribed(self, member: dict, category: str, severity: str) -> bool:
        notify = member.get("notify", [])
        return category in notify or severity in notify

    def _send_async(self, member: dict, message: str) -> None:
        """Gửi qua tất cả channels của member trong background thread."""
        def _worker():
            for ch_name, ch_cfg in member.get("channels", {}).items():
                channel = _CHANNEL_REGISTRY.get(ch_name)
                if channel:
                    channel.send(ch_cfg, message)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Public send methods
    # ------------------------------------------------------------------

    def send_alert(self, alert: dict, notify_leader: bool = True) -> None:
        """Gửi alert đến leader và/hoặc owner của device."""
        device   = alert.get("device", "")
        category = alert.get("category", "")
        severity = alert.get("severity", "info")

        owner      = self._get_owner(device)
        owner_name = owner["name"] if owner else "—"

        # Gửi leader
        if notify_leader:
            leader = self._get_leader()
            if leader and self._is_subscribed(leader, category, severity):
                self._send_async(leader, _fmt_alert(alert, for_leader=True,
                                                     responsible_name=owner_name))

        # Gửi owner (nếu khác leader)
        if owner and owner.get("role") != "leader":
            if self._is_subscribed(owner, category, severity):
                self._send_async(owner, _fmt_alert(alert))

    def send_reminder(self, alert: dict) -> None:
        """Nhắc lại owner của device chưa xử lý."""
        owner = self._get_owner(alert.get("device", ""))
        if owner and self._is_subscribed(owner, alert.get("category", ""), alert.get("severity", "")):
            self._send_async(owner, _fmt_reminder(alert))

    def send_resolved(self, alert: dict, resolved_by: str, note: str = "") -> None:
        """Thông báo đã resolve — chỉ gửi leader."""
        leader = self._get_leader()
        if leader and "resolved" in leader.get("notify", []):
            self._send_async(leader, _fmt_resolved(alert, resolved_by, note))

    def send_suricata_alert(self, event: dict) -> None:
        """Gửi Suricata IDS alert đến những ai subscribe 'suricata'."""
        msg = _fmt_suricata(event)
        for member in config.MEMBERS.values():
            if "suricata" in member.get("notify", []):
                self._send_async(member, msg)

    def send_daily_summary(self, summary: dict) -> None:
        """Gửi báo cáo ngày cho leader."""
        leader = self._get_leader()
        if leader and "daily-summary" in leader.get("notify", []):
            self._send_async(leader, _fmt_daily(summary))


# Singleton — import từ đây
notifier = NotificationRouter()
