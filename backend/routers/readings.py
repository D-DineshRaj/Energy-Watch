"""Router for meter readings endpoints."""
from enum import Enum
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import MeterReading
from backend.schemas import CSVImportResponse, MeterReadingOut
from backend.services.csv_import import parse_and_validate_csv

router = APIRouter()


class ReadingFilter(str, Enum):
    today = "today"
    yesterday = "yesterday"
    week = "week"
    all = "all"


@router.get("/readings", response_model=List[MeterReadingOut])
def get_readings(
    filter: ReadingFilter = Query(..., description="Filter period: today, yesterday, week, or all"),
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
    elif filter == ReadingFilter.week:
        readings = (
            db.query(MeterReading)
            .filter(MeterReading.reading_type == "daily")
            .order_by(MeterReading.timestamp.asc())
            .all()
        )
    else:  # ReadingFilter.all
        readings = (
            db.query(MeterReading)
            .order_by(MeterReading.timestamp.desc())
            .limit(50)
            .all()
        )

    return readings


@router.post("/readings/upload-csv", response_model=CSVImportResponse)
async def upload_csv_readings(
    request: Request,
    file: Optional[UploadFile] = File(None),
    strict: bool = Query(False, description="If True, reject the entire batch if any row has validation errors"),
    db: Session = Depends(get_db),
):
    """Upload a CSV file containing meter readings, validate columns and values, and insert into SQLite."""
    filename = "meter_readings.csv"
    content = ""

    if file is not None:
        filename = file.filename or filename
        raw_bytes = await file.read()
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw_bytes.decode("latin-1")
            except Exception:
                raise HTTPException(status_code=400, detail="Unable to decode file. Please provide a valid UTF-8 CSV.")
    else:
        # Fallback to direct raw request body if not multipart
        raw_bytes = await request.body()
        if raw_bytes:
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="Unable to decode request body. Please provide valid UTF-8 text.")

    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty or contains no records.")

    try:
        result = parse_and_validate_csv(
            csv_content=content,
            db=db,
            filename=filename,
            strict=strict,
        )
        return CSVImportResponse(**result)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during CSV import: {err}")
