"""Router for metrics overview endpoint."""
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Forecast
from backend.schemas import MetricsResponse

router = APIRouter()


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)):
    """Retrieve top-level summary metrics with simulated indicators."""
    tomorrow_forecast = (
        db.query(Forecast)
        .filter(Forecast.forecast_date == date(2026, 9, 9))
        .first()
    )
    tomorrow_kwh = tomorrow_forecast.predicted_kwh if tomorrow_forecast else 37.2

    return MetricsResponse(
        today_kwh=35.4,
        month_kwh=420.0,
        tomorrow_forecast_kwh=tomorrow_kwh,
        estimated_bill_inr=None,  # Correction 4: Kept null in Phase 1 pending APERC tariff verification
        tariff_note="Bill estimation not yet implemented. Configurable AP tariff rules will be added in Phase 4.",
        forecast_is_real_model=False,
        data_source="simulated",
    )
