"""Database configuration and session management for EnergyWatch."""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Correction 6: Path resolved relative to project root, not CWD
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = _PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "energywatch.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

# check_same_thread is required for SQLite with multi-threaded FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency for yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables in the database if they do not exist and seed default meter."""
    from datetime import date
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    from backend import models  # ensure models are registered with Base
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        meter = db.query(models.Meter).filter(models.Meter.meter_id == "EW-2847-HH").first()
        if not meter:
            db.add(
                models.Meter(
                    meter_id="EW-2847-HH",
                    name="Main Residential Meter",
                    consumer_name="Dinesh Raj",
                    installation_date=date(2026, 1, 1),
                    meter_type="Smart Single-Phase Bi-directional",
                    sanctioned_load_kw=1.0,
                    status="Active",
                )
            )
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
