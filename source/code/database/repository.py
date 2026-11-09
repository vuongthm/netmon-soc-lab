# database/repository.py
# Tất cả DB query tập trung. Dùng now_vn_naive() cho mọi thời gian.

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, func

from database import get_db
from database.models import Alert, ServiceCheck, SocEvent
from services.timezone import now_vn_naive, cutoff_vn


class AlertRepository:

    def save(self, data: dict) -> str:
        if not data.get("id"):
            data["id"] = str(uuid.uuid4())
        if isinstance(data.get("created_at"), str):
            try:
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            except ValueError:
                data["created_at"] = now_vn_naive()
        elif "created_at" not in data:
            data["created_at"] = now_vn_naive()

        with get_db() as db:
            db.add(Alert(**data))
        return data["id"]

    def resolve(self, alert_id: str, resolved_by: str, note: str = "", mode: str = "human") -> bool:
        with get_db() as db:
            row = db.query(Alert).filter(Alert.id == alert_id).first()
            if not row:
                return False
            row.resolved      = True
            row.resolved_by   = resolved_by
            row.resolved_at   = now_vn_naive()
            row.resolved_note = note
            row.resolve_mode  = mode
        return True

    def resolve_by_subkey(self, sub_key: str, mode: str = "auto") -> list[dict]:
        resolved = []
        with get_db() as db:
            rows = (
                db.query(Alert)
                .filter(Alert.sub_key == sub_key, Alert.resolved == False)
                .all()
            )
            now = now_vn_naive()
            for row in rows:
                row.resolved      = True
                row.resolved_at   = now
                row.resolve_mode  = mode
                row.resolved_by   = "system"
                row.resolved_note = "Condition cleared automatically"
                resolved.append(row.to_dict())
        return resolved

    def delete_all(self) -> int:
        with get_db() as db:
            return db.query(Alert).delete()

    def get_many(
        self,
        limit:    int = 300,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        resolved: Optional[bool] = None,
        device:   Optional[str] = None,
        from_dt:  Optional[datetime] = None,
        to_dt:    Optional[datetime] = None,
    ) -> list[dict]:
        with get_db() as db:
            q = db.query(Alert).order_by(desc(Alert.created_at))
            if severity is not None: q = q.filter(Alert.severity == severity)
            if category is not None: q = q.filter(Alert.category == category)
            if device   is not None: q = q.filter(Alert.device   == device)
            if resolved is not None: q = q.filter(Alert.resolved == resolved)
            if from_dt  is not None: q = q.filter(Alert.created_at >= from_dt)
            if to_dt    is not None: q = q.filter(Alert.created_at <= to_dt)
            return [row.to_dict() for row in q.limit(limit)]

    def get_by_id(self, alert_id: str) -> Optional[dict]:
        with get_db() as db:
            row = db.query(Alert).filter(Alert.id == alert_id).first()
            return row.to_dict() if row else None

    def get_active_by_subkey(self, sub_key: str) -> Optional[dict]:
        with get_db() as db:
            row = (
                db.query(Alert)
                .filter(Alert.sub_key == sub_key, Alert.resolved == False)
                .order_by(desc(Alert.created_at))
                .first()
            )
            return row.to_dict() if row else None

    def get_stats(self) -> dict:
        with get_db() as db:
            total      = db.query(func.count(Alert.id)).scalar() or 0
            critical   = db.query(func.count(Alert.id)).filter(Alert.severity == "critical").scalar() or 0
            warning    = db.query(func.count(Alert.id)).filter(Alert.severity == "warning").scalar()  or 0
            ai_count   = db.query(func.count(Alert.id)).filter(Alert.category == "ai-anomaly").scalar() or 0
            unresolved = db.query(func.count(Alert.id)).filter(Alert.resolved == False).scalar() or 0
        return {"total": total, "critical": critical, "warning": warning,
                "ai": ai_count, "unresolved": unresolved}

    def get_timeline(self, from_dt: datetime, to_dt: datetime, bucket: str = "day") -> list[dict]:
        trunc_map = {"hour": "hour", "day": "day", "week": "week", "month": "month"}
        trunc = trunc_map.get(bucket, "day")
        with get_db() as db:
            rows = (
                db.query(
                    func.date_trunc(trunc, Alert.created_at).label("bucket"),
                    Alert.severity,
                    func.count(Alert.id).label("cnt"),
                )
                .filter(Alert.created_at.between(from_dt, to_dt))
                .group_by("bucket", Alert.severity)
                .order_by("bucket")
                .all()
            )
        buckets: dict = {}
        for row in rows:
            label = str(row.bucket)[:16]
            if label not in buckets:
                buckets[label] = {"label": label, "critical": 0, "warning": 0, "total": 0}
            buckets[label][row.severity] = buckets[label].get(row.severity, 0) + row.cnt
            buckets[label]["total"] += row.cnt
        return list(buckets.values())


class SocEventRepository:

    def save_many(self, events: list[dict]) -> int:
        if not events:
            return 0
        rows = []
        for ev in events:
            ts = ev.get("timestamp", "")
            if isinstance(ts, str):
                try:
                    # Suricata timestamp có dạng "2025-04-27T13:20:00.123456+0700"
                    # Chuyển thành naive VN time
                    ts_aware = datetime.fromisoformat(ts.replace("+0700", "+07:00"))
                    ts = ts_aware.replace(tzinfo=None)  # bỏ tzinfo, giữ giờ VN
                except Exception:
                    ts = now_vn_naive()
            rows.append(SocEvent(
                occurred_at    = ts,
                src_ip         = ev.get("src_ip", ""),
                src_port       = ev.get("src_port"),
                dest_ip        = ev.get("dest_ip", ""),
                dest_port      = ev.get("dest_port"),
                proto          = ev.get("proto", ""),
                severity       = ev.get("severity", "info"),
                priority       = ev.get("priority", 3),
                sig_id         = ev.get("sig_id"),
                signature      = ev.get("signature", ""),
                category       = ev.get("category", ""),
                raw_category   = ev.get("raw_category", ""),
                action         = ev.get("action", "allowed"),
                http_url       = ev.get("http_url", ""),
                http_method    = ev.get("http_method", ""),
                http_status    = ev.get("http_status"),
                http_host      = ev.get("http_host", ""),
                interface_name = ev.get("interface_name", "unknown"),
                zone           = ev.get("zone", "unknown"),
            ))
        with get_db() as db:
            db.bulk_save_objects(rows)
        return len(rows)

    def get_latest_timestamp(self) -> Optional[datetime]:
        with get_db() as db:
            return db.query(func.max(SocEvent.occurred_at)).scalar()

    def get_many(
        self,
        limit:          int = 100,
        severity:       Optional[str] = None,
        category:       Optional[str] = None,
        src_ip:         Optional[str] = None,
        zone:           Optional[str] = None,
        interface_name: Optional[str] = None,
        hours:          int = 24,
    ) -> list[dict]:
        cutoff = cutoff_vn(hours)
        with get_db() as db:
            q = (
                db.query(SocEvent)
                .filter(SocEvent.occurred_at >= cutoff)
                .order_by(desc(SocEvent.occurred_at))
            )
            if severity:       q = q.filter(SocEvent.severity       == severity)
            if category:       q = q.filter(SocEvent.category       == category)
            if src_ip:         q = q.filter(SocEvent.src_ip         == src_ip)
            if zone:           q = q.filter(SocEvent.zone           == zone)
            if interface_name: q = q.filter(SocEvent.interface_name == interface_name)
            return [row.to_dict() for row in q.limit(limit)]

    def get_stats(self, hours: int = 24) -> dict:
        cutoff = cutoff_vn(hours)
        with get_db() as db:
            sev_rows = (
                db.query(SocEvent.severity, func.count(SocEvent.id).label("cnt"))
                .filter(SocEvent.occurred_at >= cutoff)
                .group_by(SocEvent.severity).all()
            )
            sev_map = {r.severity: r.cnt for r in sev_rows}

            def _top5(col):
                return (
                    db.query(col, func.count(SocEvent.id).label("cnt"))
                    .filter(SocEvent.occurred_at >= cutoff)
                    .group_by(col).order_by(desc("cnt")).limit(5).all()
                )

            top_attackers  = _top5(SocEvent.src_ip)
            top_sigs       = _top5(SocEvent.signature)
            top_cats       = _top5(SocEvent.category)
            hour_count     = (
                db.query(func.count(SocEvent.id))
                .filter(SocEvent.occurred_at >= cutoff_vn(1))
                .scalar() or 0
            )

            # Thống kê theo zone / interface
            zone_rows = (
                db.query(
                    SocEvent.interface_name,
                    SocEvent.zone,
                    func.count(SocEvent.id).label("cnt")
                )
                .filter(SocEvent.occurred_at >= cutoff)
                .group_by(SocEvent.interface_name, SocEvent.zone)
                .order_by(desc("cnt"))
                .all()
            )

        return {
            "total":            sum(sev_map.values()),
            "critical":         sev_map.get("critical", 0),
            "warning":          sev_map.get("warning",  0),
            "info":             sev_map.get("info",     0),
            "events_last_hour": hour_count,
            "top_attackers":    [{"key": r[0], "count": r[1]} for r in top_attackers],
            "top_signatures":   [{"key": r[0], "count": r[1]} for r in top_sigs],
            "top_categories":   [{"key": r[0], "count": r[1]} for r in top_cats],
            "by_interface":     [
                {"interface": r[0], "zone": r[1], "count": r[2]}
                for r in zone_rows
            ],
        }

    def get_timeline(self, hours: int = 24, bucket_minutes: int = 60) -> list[dict]:
        cutoff = cutoff_vn(hours)
        trunc  = "hour" if bucket_minutes >= 60 else "minute"
        with get_db() as db:
            rows = (
                db.query(
                    func.date_trunc(trunc, SocEvent.occurred_at).label("bucket"),
                    SocEvent.severity,
                    func.count(SocEvent.id).label("cnt"),
                )
                .filter(SocEvent.occurred_at >= cutoff)
                .group_by("bucket", SocEvent.severity)
                .order_by("bucket").all()
            )
        buckets: dict = {}
        for row in rows:
            label = str(row.bucket)[:16]
            if label not in buckets:
                buckets[label] = {"label": label, "critical": 0, "warning": 0, "info": 0, "total": 0}
            sev = row.severity if row.severity in ("critical", "warning", "info") else "info"
            buckets[label][sev]     += row.cnt
            buckets[label]["total"] += row.cnt
        return list(buckets.values())

    def get_attacker_detail(self, src_ip: str) -> dict:
        with get_db() as db:
            total      = db.query(func.count(SocEvent.id)).filter(SocEvent.src_ip == src_ip).scalar() or 0
            first_seen = db.query(func.min(SocEvent.occurred_at)).filter(SocEvent.src_ip == src_ip).scalar()
            last_seen  = db.query(func.max(SocEvent.occurred_at)).filter(SocEvent.src_ip == src_ip).scalar()

            def _top5(col):
                return (
                    db.query(col, func.count(SocEvent.id).label("cnt"))
                    .filter(SocEvent.src_ip == src_ip)
                    .group_by(col).order_by(desc("cnt")).limit(5).all()
                )

            top_sigs  = _top5(SocEvent.signature)
            top_ports = _top5(SocEvent.dest_port)

            recent = (
                db.query(SocEvent)
                .filter(SocEvent.src_ip == src_ip)
                .order_by(desc(SocEvent.occurred_at))
                .limit(20).all()
            )

            # Serialize bên trong session còn mở — tránh lazy-load error
            return {
                "src_ip":         src_ip,
                "total_events":   total,
                "first_seen":     first_seen.isoformat() if first_seen else None,
                "last_seen":      last_seen.isoformat()  if last_seen  else None,
                "top_signatures": [{"sig": r[0], "count": r[1]} for r in top_sigs],
                "target_ports":   [{"port": r[0], "count": r[1]} for r in top_ports],
                "recent_events":  [r.to_dict() for r in recent],
            }


class ServiceCheckRepository:

    def save(self, result: dict) -> None:
        with get_db() as db:
            db.add(ServiceCheck(
                name        = result["name"],
                check_type  = result.get("type", ""),
                target      = result.get("target", ""),
                status      = result.get("status", "unknown"),
                latency_ms  = result.get("latency_ms"),
                error       = result.get("error", ""),
                status_code = result.get("status_code"),
            ))

    def get_latest(self) -> list[dict]:
        with get_db() as db:
            rows = (
                db.query(ServiceCheck)
                .distinct(ServiceCheck.name)
                .order_by(ServiceCheck.name, desc(ServiceCheck.checked_at))
                .all()
            )
            return [r.to_dict() for r in rows]

    def get_uptime_pct(self, name: str, hours: int = 24) -> float:
        cutoff = cutoff_vn(hours)
        with get_db() as db:
            total = db.query(func.count(ServiceCheck.id)).filter(
                ServiceCheck.name == name, ServiceCheck.checked_at >= cutoff
            ).scalar() or 0
            up = db.query(func.count(ServiceCheck.id)).filter(
                ServiceCheck.name == name,
                ServiceCheck.checked_at >= cutoff,
                ServiceCheck.status == "up",
            ).scalar() or 0
        return round(up / total * 100, 2) if total else 0.0


alert_repo   = AlertRepository()
soc_repo     = SocEventRepository()
service_repo = ServiceCheckRepository()