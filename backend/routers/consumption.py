"""Router for consumption trends endpoints, dynamically queried from SQLite."""
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Alert, MeterReading
from backend.schemas import ConsumptionResponse
from backend.services.date_utils import (
    get_current_date,
    get_latest_reading_date,
    parse_reference_date,
)

router = APIRouter()


class ConsumptionRange(str, Enum):
    seven_days = "7d"
    thirty_days = "30d"
    three_months = "3m"


@router.get("/consumption", response_model=ConsumptionResponse)
def get_consumption(
    time_range: ConsumptionRange = Query(..., alias="range", description="Time range: 7d, 30d, or 3m"),
    meter_id: Optional[str] = Query("EW-2847-HH", description="Smart meter identifier"),
    current_date: Optional[str] = Query(None, description="Injectable reference date for testing (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Retrieve historical consumption series and anomaly flags queried dynamically from SQLite.

    - Dynamic SQLite aggregation by calendar date or week.
    - Honors daily vs hourly reading precedence: hourly readings are summed; if only daily exists, daily reading is used.
    - Accurately associates existing anomaly detection alerts and High status flags with daily data points.
    - Omits legacy static forecast overlay so ML forecasting remains dedicated to the Forecasting section.
    """
    meter = meter_id.strip() if meter_id else "EW-2847-HH"

    # 1. Determine anchor reference date
    ref_date = parse_reference_date(current_date)
    if not ref_date:
        cur = get_current_date()
        latest_d = get_latest_reading_date(db, meter_id=meter)
        if latest_d and cur > latest_d:
            ref_date = latest_d
        else:
            ref_date = cur

    # 2. Gather alert metadata to identify anomalous readings
    alerts = db.query(Alert).all()
    alert_reading_ids = {a.reading_id for a in alerts if a.reading_id is not None}
    alert_dates = {a.triggered_at.date() for a in alerts if a.triggered_at is not None}

    labels: List[str] = []
    actual: List[Optional[float]] = []
    anomalies: List[bool] = []

    if time_range == ConsumptionRange.seven_days:
        num_days = 7
        target_dates = [ref_date - timedelta(days=i) for i in reversed(range(num_days))]
        start_dt = datetime.combine(target_dates[0], time.min)
        end_dt = datetime.combine(target_dates[-1], time.max)

        readings = (
            db.query(MeterReading)
            .filter(
                MeterReading.meter_id == meter,
                MeterReading.timestamp >= start_dt,
                MeterReading.timestamp <= end_dt,
            )
            .all()
        )
        readings_by_day: Dict[date, List[MeterReading]] = {}
        for r in readings:
            readings_by_day.setdefault(r.timestamp.date(), []).append(r)

        for d in target_dates:
            labels.append(f"{d.strftime('%b')} {d.day}")
            day_rs = readings_by_day.get(d, [])
            if day_rs:
                hourly_rs = [r for r in day_rs if r.reading_type == "hourly"]
                if hourly_rs:
                    val = sum(float(r.usage_kwh) for r in hourly_rs)
                else:
                    daily_rs = [r for r in day_rs if r.reading_type == "daily"]
                    val = sum(float(r.usage_kwh) for r in daily_rs) if daily_rs else sum(float(r.usage_kwh) for r in day_rs)
                actual.append(round(val, 2))
                is_anomaly = any(
                    r.status == "High" or r.id in alert_reading_ids or (d in alert_dates)
                    for r in day_rs
                ) or (d in alert_dates)
                anomalies.append(is_anomaly)
            else:
                actual.append(None)
                anomalies.append(False)

    elif time_range == ConsumptionRange.thirty_days:
        num_days = 30
        target_dates = [ref_date - timedelta(days=i) for i in reversed(range(num_days))]
        start_dt = datetime.combine(target_dates[0], time.min)
        end_dt = datetime.combine(target_dates[-1], time.max)

        readings = (
            db.query(MeterReading)
            .filter(
                MeterReading.meter_id == meter,
                MeterReading.timestamp >= start_dt,
                MeterReading.timestamp <= end_dt,
            )
            .all()
        )
        readings_by_day: Dict[date, List[MeterReading]] = {}
        for r in readings:
            readings_by_day.setdefault(r.timestamp.date(), []).append(r)

        for d in target_dates:
            labels.append(f"{d.strftime('%b')} {d.day}")
            day_rs = readings_by_day.get(d, [])
            if day_rs:
                hourly_rs = [r for r in day_rs if r.reading_type == "hourly"]
                if hourly_rs:
                    val = sum(float(r.usage_kwh) for r in hourly_rs)
                else:
                    daily_rs = [r for r in day_rs if r.reading_type == "daily"]
                    val = sum(float(r.usage_kwh) for r in daily_rs) if daily_rs else sum(float(r.usage_kwh) for r in day_rs)
                actual.append(round(val, 2))
                is_anomaly = any(
                    r.status == "High" or r.id in alert_reading_ids or (d in alert_dates)
                    for r in day_rs
                ) or (d in alert_dates)
                anomalies.append(is_anomaly)
            else:
                actual.append(None)
                anomalies.append(False)

    elif time_range == ConsumptionRange.three_months:
        num_weeks = 12
        for i in reversed(range(num_weeks)):
            w_end = ref_date - timedelta(days=i * 7)
            w_start = w_end - timedelta(days=6)
            labels.append(f"{w_end.strftime('%b')} {w_end.day}")

            w_readings = (
                db.query(MeterReading)
                .filter(
                    MeterReading.meter_id == meter,
                    MeterReading.timestamp >= datetime.combine(w_start, time.min),
                    MeterReading.timestamp <= datetime.combine(w_end, time.max),
                )
                .all()
            )
            by_day: Dict[date, List[MeterReading]] = {}
            for r in w_readings:
                by_day.setdefault(r.timestamp.date(), []).append(r)

            day_totals: List[float] = []
            week_anomalies: List[bool] = []
            for d, day_rs in by_day.items():
                hourly_rs = [r for r in day_rs if r.reading_type == "hourly"]
                if hourly_rs:
                    d_val = sum(float(r.usage_kwh) for r in hourly_rs)
                else:
                    daily_rs = [r for r in day_rs if r.reading_type == "daily"]
                    d_val = sum(float(r.usage_kwh) for r in daily_rs) if daily_rs else sum(float(r.usage_kwh) for r in day_rs)
                day_totals.append(d_val)
                is_ano = any(
                    r.status == "High" or r.id in alert_reading_ids or (d in alert_dates)
                    for r in day_rs
                ) or (d in alert_dates)
                week_anomalies.append(is_ano)

            if day_totals:
                actual.append(round(sum(day_totals) / len(day_totals), 2))
                anomalies.append(any(week_anomalies))
            else:
                actual.append(None)
                anomalies.append(False)

    return ConsumptionResponse(
        range=time_range.value,
        labels=labels,
        actual=actual,
        forecast=[],
        unit="kWh",
        source="sqlite",
        anomalies=anomalies,
    )
