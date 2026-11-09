#!/usr/bin/env python3
# scripts/rollback_interface_cols.py

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
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

import config
from sqlalchemy import create_engine, text

engine = create_engine(config.DATABASE_URL)

ROLLBACK_SQL = [
    "DROP INDEX IF EXISTS ix_soc_zone_sev;",
    "DROP INDEX IF EXISTS ix_soc_iface;",
    "DROP INDEX IF EXISTS ix_soc_zone;",
    """
    ALTER TABLE soc_events
    DROP COLUMN IF EXISTS interface_name;
    """,
    """
    ALTER TABLE soc_events
    DROP COLUMN IF EXISTS zone;
    """
]

print("=" * 50)
print(" Rollback migration: remove interface_name + zone")
print("=" * 50)

try:
    with engine.begin() as conn:
        for sql in ROLLBACK_SQL:
            conn.execute(text(sql))
            print(f"✅ Done: {sql.strip()[:60]}...")

    print("\n✅ Rollback hoàn tất!")

except Exception as exc:
    print(f"\n❌ Rollback lỗi: {exc}")
    sys.exit(1)
