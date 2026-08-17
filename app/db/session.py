from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from app.core.config import settings
from app.db.models import Base

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # detect stale connections
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def create_tables():
    Base.metadata.create_all(bind=engine)

# ── For FastAPI dependency injection (request-scoped) ──
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── For background tasks (creates its own session) ──
# This is the FIX for Phase 3's bug where the request session
# was passed to a background task and closed prematurely.
@contextmanager
def get_background_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
