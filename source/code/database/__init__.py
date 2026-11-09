# database/__init__.py
# =============================================================================
# Khởi tạo database engine và session factory.
# Import từ file này ở mọi nơi trong project.
# =============================================================================

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import config
from .models import Base


engine = create_engine(
    config.DATABASE_URL,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_timeout=config.DB_POOL_TIMEOUT,
    pool_pre_ping=True,   # tự reconnect nếu DB restart
    echo=config.DB_ECHO,
)

_SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """
    Tạo tất cả bảng nếu chưa tồn tại. Idempotent — gọi nhiều lần vẫn an toàn.
    Gọi 1 lần duy nhất khi app khởi động.
    """
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version()")).scalar()
        print(f"[db] ready — {str(ver)[:60]}")


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager cấp phát session cho 1 unit-of-work.

    Cách dùng:
        with get_db() as db:
            db.add(obj)
        # commit + close tự động

    Nếu có exception → rollback tự động, session vẫn được đóng.
    """
    db = _SessionFactory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
