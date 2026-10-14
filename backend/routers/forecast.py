"""Router for energy consumption forecasting endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Forecast
from backend.schemas import ForecastDay, ForecastResponse

router = APIRouter()


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(db: Session = Depends(get_db)):
    """Retrieve sample forecast data explicitly labelled as static simulation."""
    # Query seeded static forecast records if present
    db_forecasts = db.query(Forecast).order_by(Forecast.forecast_date.asc()).all()

    days = [
        ForecastDay(
            date="Tuesday, Sep 8",
            day_name="Today",
            predicted_kwh=35.4,
            lower_bound_kwh=33.0,
            upper_bound_kwh=37.5,
            is_peak=False,
        ),
        ForecastDay(
            date="Wednesday, Sep 9",
            day_name="Tomorrow",
            predicted_kwh=37.2,
            lower_bound_kwh=34.5,
            upper_bound_kwh=39.8,
            is_peak=False,
        ),
        ForecastDay(
            date="Thursday, Sep 10",
            day_name="Sep 10",
            predicted_kwh=38.1,
            lower_bound_kwh=35.2,
            upper_bound_kwh=41.0,
            is_peak=True,
        ),
    ]

    return ForecastResponse(
        model="static_seed",
        is_real_model=False,
        is_computed=False,
        note=(
            "Forecast values are static sample data seeded from the original mock dashboard. "
            "No forecasting computation has been performed."
        ),
        days=days,
        chart_labels=["Sep 6", "Sep 7", "Sep 8", "Sep 9", "Sep 10"],
        actual_series=[33.9, 33.9, 35.4, None, None],
        forecast_series=[None, None, 35.4, 37.2, 38.1],
    )
