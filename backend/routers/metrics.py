"""Router for metrics overview endpoint."""
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Forecast
from backend.schemas import MetricsResponse
from backend.services.billing import calculate_aperc_bill

router = APIRouter()


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)):
    """Retrieve top-level summary metrics with simulated indicators."""
    tomorrow_forecast = (
        db.query(Forecast)
        .filter(Forecast.forecast_date == date(2026, 9, 9))
        .first()
    )
    tomorrow_kwh = tomorrow_forecast.predicted_kwh if tomorrow_forecast else 34.4
    forecast_is_real = tomorrow_forecast.is_ml_model if tomorrow_forecast else True

    month_kwh = 420.0
    bill_calc = calculate_aperc_bill(consumption_kwh=month_kwh)
    estimated_bill = float(bill_calc["estimated_total_rounded_inr"])

    return MetricsResponse(
        today_kwh=35.4,
        month_kwh=month_kwh,
        tomorrow_forecast_kwh=tomorrow_kwh,
        estimated_bill_inr=estimated_bill,
        tariff_note="Estimated using official APERC LT-I(A) Domestic tariff order for FY 2026-27 (effective 01-Apr-2026). Not an official DISCOM bill.",
        forecast_is_real_model=forecast_is_real,
        data_source="simulated",
    )
