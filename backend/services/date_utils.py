"""Authoritative date and timezone management utilities for EnergyWatch.

The designated application timezone is Asia/Kolkata (UTC+05:30).
Supports deterministic testing via injectable dates or the ENERGYWATCH_CURRENT_DATE environment variable.
"""
from datetime import date, datetime, time, timedelta, timezone
import os
from typing import Optional, Union

try:
    from zoneinfo import ZoneInfo
    APP_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    APP_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

from sqlalchemy.orm import Session
from backend.models import MeterReading


def get_current_datetime(override_dt: Optional[datetime] = None) -> datetime:
    """Return the current datetime in Asia/Kolkata timezone.

    Supports environment variable override 'ENERGYWATCH_CURRENT_DATE' (YYYY-MM-DD or ISO)
    for deterministic automated testing.
    """
    if override_dt is not None:
        if override_dt.tzinfo is None:
            return override_dt.replace(tzinfo=APP_TIMEZONE)
        return override_dt.astimezone(APP_TIMEZONE)

    env_val = os.environ.get("ENERGYWATCH_CURRENT_DATE")
    if env_val:
        try:
            val_clean = env_val.strip()
            if len(val_clean) == 10:
                d = date.fromisoformat(val_clean)
                return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=APP_TIMEZONE)
            dt = datetime.fromisoformat(val_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=APP_TIMEZONE)
            return dt.astimezone(APP_TIMEZONE)
        except ValueError:
            pass

    return datetime.now(APP_TIMEZONE)


def get_current_date(override_date: Optional[Union[date, str]] = None) -> date:
    """Return the authoritative current calendar date in Asia/Kolkata."""
    if override_date is not None:
        if isinstance(override_date, str):
            try:
                return date.fromisoformat(override_date.strip())
            except ValueError:
                pass
        elif isinstance(override_date, date):
            return override_date
    return get_current_datetime().date()


def get_latest_reading_date(db: Session, meter_id: Optional[str] = "EW-2847-HH") -> Optional[date]:
    """Query the most recent reading timestamp recorded in the SQLite database."""
    query = db.query(MeterReading.timestamp)
    if meter_id:
        query = query.filter(MeterReading.meter_id == meter_id)
    latest = query.order_by(MeterReading.timestamp.desc()).first()
    if latest and latest[0]:
        return latest[0].date()
    return None


def parse_reference_date(val: Optional[Union[str, date]]) -> Optional[date]:
    """Parse flexible date strings (YYYY-MM-DD) into a date object."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip())
    except (ValueError, TypeError):
        return None
