"""Router for meter readings endpoints."""
from enum import Enum
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import MeterReading
from backend.schemas import MeterReadingOut

router = APIRouter()


class ReadingFilter(str, Enum):
    today = "today"
    yesterday = "yesterday"
    week = "week"


@router.get("/readings", response_model=List[MeterReadingOut])
def get_readings(
    filter: ReadingFilter = Query(..., description="Filter period: today, yesterday, or week"),
    db: Session = Depends(get_db),
):
    """Retrieve simulated meter readings by period filter."""
    if filter == ReadingFilter.today:
        readings = (
            db.query(MeterReading)
            .filter(
                MeterReading.reading_type == "hourly",
                func.date(MeterReading.timestamp) == "2026-09-08",
            )
            .order_by(MeterReading.timestamp.asc())
            .all()
        )
    elif filter == ReadingFilter.yesterday:
        readings = (
            db.query(MeterReading)
            .filter(
                MeterReading.reading_type == "hourly",
                func.date(MeterReading.timestamp) == "2026-09-07",
            )
            .order_by(MeterReading.timestamp.asc())
            .all()
        )
    else:  # ReadingFilter.week
        readings = (
            db.query(MeterReading)
            .filter(MeterReading.reading_type == "daily")
            .order_by(MeterReading.timestamp.asc())
            .all()
        )

    return readings
