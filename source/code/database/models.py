# database/models.py
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime,
    Float, Index, Integer, SmallInteger, String, Text,
)
from sqlalchemy.orm import DeclarativeBase
from services.timezone import now_vn_naive


class Base(DeclarativeBase):
    pass


class Alert(Base):
    __tablename__ = "alerts"

    id            = Column(String(36),  primary_key=True)
    created_at    = Column(DateTime,    nullable=False, default=now_vn_naive)
    device        = Column(String(64),  nullable=False)
    severity      = Column(String(16),  nullable=False)
    category      = Column(String(32),  nullable=False)
    message       = Column(Text,        nullable=False)
    details       = Column(Text,        default="")
    sub_key       = Column(String(128), default="")
    resolved      = Column(Boolean,     nullable=False, default=False)
    resolved_by   = Column(String(64))
    resolved_at   = Column(DateTime)
    resolved_note = Column(Text)
    resolve_mode  = Column(String(16))

    __table_args__ = (
        Index("ix_alert_created",         "created_at"),
        Index("ix_alert_device",          "device"),
        Index("ix_alert_severity",        "severity"),
        Index("ix_alert_resolved",        "resolved"),
        Index("ix_alert_device_resolved", "device", "resolved"),
        Index("ix_alert_sev_created",     "severity", "created_at"),
        Index("ix_alert_subkey",          "sub_key"),
    )

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "timestamp":     self.created_at.isoformat() if self.created_at else "",
            "device":        self.device,
            "severity":      self.severity,
            "category":      self.category,
            "message":       self.message,
            "details":       self.details or "",
            "sub_key":       self.sub_key or "",
            "resolved":      self.resolved,
            "resolved_by":   self.resolved_by,
            "resolved_at":   self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_note": self.resolved_note,
            "resolve_mode":  self.resolve_mode,
        }


class SocEvent(Base):
    __tablename__ = "soc_events"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at  = Column(DateTime,   nullable=False, default=now_vn_naive)
    src_ip       = Column(String(45), nullable=False)
    src_port     = Column(Integer)
    dest_ip      = Column(String(45), nullable=False)
    dest_port    = Column(Integer)
    proto        = Column(String(8))
    severity     = Column(String(16),  nullable=False)
    priority     = Column(SmallInteger)
    sig_id       = Column(Integer)
    signature    = Column(Text)
    category     = Column(String(64))
    raw_category = Column(String(128))
    action       = Column(String(16), default="allowed")
    http_url        = Column(Text)
    http_method     = Column(String(16))
    http_status     = Column(SmallInteger)
    http_host       = Column(String(256))

    # Thông tin interface nguồn — biết alert đến từ vùng mạng nào
    interface_name  = Column(String(32), default="unknown")  # WAN / Web-DMZ / DNS-FTP / LAN / ZT
    zone            = Column(String(32), default="unknown")  # wan / dmz-web / dmz-dns-ftp / lan / zt

    __table_args__ = (
        Index("ix_soc_occurred",   "occurred_at"),
        Index("ix_soc_src_ip",     "src_ip"),
        Index("ix_soc_severity",   "severity"),
        Index("ix_soc_category",   "category"),
        Index("ix_soc_zone",       "zone"),
        Index("ix_soc_iface",      "interface_name"),
        Index("ix_soc_sev_time",   "severity", "occurred_at"),
        Index("ix_soc_src_time",   "src_ip",   "occurred_at"),
        Index("ix_soc_zone_sev",   "zone", "severity"),
    )

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "timestamp":      self.occurred_at.isoformat() if self.occurred_at else "",
            "src_ip":         self.src_ip,
            "src_port":       self.src_port,
            "dest_ip":        self.dest_ip,
            "dest_port":      self.dest_port,
            "proto":          self.proto or "",
            "severity":       self.severity,
            "priority":       self.priority,
            "sig_id":         self.sig_id,
            "signature":      self.signature or "",
            "category":       self.category or "",
            "action":         self.action or "allowed",
            "http_url":       self.http_url or "",
            "http_method":    self.http_method or "",
            "http_status":    self.http_status,
            "interface_name": self.interface_name or "unknown",
            "zone":           self.zone or "unknown",
        }


class ServiceCheck(Base):
    __tablename__ = "service_checks"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    checked_at  = Column(DateTime,  nullable=False, default=now_vn_naive)
    name        = Column(String(64), nullable=False)
    check_type  = Column(String(16))
    target      = Column(String(256))
    status      = Column(String(8),  nullable=False)
    latency_ms  = Column(Float)
    error       = Column(String(256))
    status_code = Column(SmallInteger)

    __table_args__ = (
        Index("ix_svc_name_time", "name", "checked_at"),
        Index("ix_svc_status",    "status"),
    )

    def to_dict(self) -> dict:
        return {
            "checked_at":  self.checked_at.isoformat() if self.checked_at else "",
            "name":        self.name,
            "type":        self.check_type,
            "target":      self.target,
            "status":      self.status,
            "latency_ms":  self.latency_ms,
            "error":       self.error,
            "status_code": self.status_code,
        }