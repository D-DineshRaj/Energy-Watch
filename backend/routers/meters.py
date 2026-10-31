"""Router for smart meters management endpoints (DBMS Module)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Meter, MeterReading
from backend.schemas import MeterDetailOut, MeterOut

router = APIRouter()


@router.get("/meters", response_model=List[MeterOut])
def list_meters(db: Session = Depends(get_db)):
    """List all registered smart utility meters."""
    return db.query(Meter).order_by(Meter.id.asc()).all()


@router.get("/meters/{meter_id}", response_model=MeterDetailOut)
def get_meter_details(meter_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed metadata and telemetry status for a specific smart meter."""
    meter = db.query(Meter).filter(Meter.meter_id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail=f"Meter '{meter_id}' not found.")

    readings_count = db.query(MeterReading).filter(MeterReading.meter_id == meter_id).count()
    latest_reading = (
        db.query(MeterReading)
        .filter(MeterReading.meter_id == meter_id)
        .order_by(MeterReading.timestamp.desc())
        .first()
    )

    return MeterDetailOut(
        id=meter.id,
        meter_id=meter.meter_id,
        name=meter.name,
        consumer_name=meter.consumer_name,
        installation_date=meter.installation_date,
        meter_type=meter.meter_type,
        sanctioned_load_kw=meter.sanctioned_load_kw,
        status=meter.status,
        created_at=meter.created_at,
        readings_count=readings_count,
        latest_reading_time=latest_reading.timestamp if latest_reading else None,
        latest_reading_kwh=latest_reading.usage_kwh if latest_reading else None,
    )

