"""Router for energy consumption forecasting endpoint."""
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Forecast
from backend.schemas import ForecastDay, ForecastResponse
from backend.services.date_utils import (
    get_current_date,
    get_latest_reading_date,
    parse_reference_date,
)
from backend.services.forecasting import (
    get_consumption_series_from_db,
    sync_forecast_to_db,
    train_and_evaluate_forecasting_pipeline,
)

router = APIRouter()


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    model_type: str = Query("arima", description="Forecasting model type: arima or gradient_boosting"),
    horizon: Optional[int] = Query(None, ge=1, le=7, description="Number of future days to forecast"),
    current_date: Optional[str] = Query(None, description="Injectable reference date for testing (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Retrieve multi-step machine-learning consumption forecast evaluated on chronological holdout."""
    today = parse_reference_date(current_date) or get_current_date()
    tomorrow = today + timedelta(days=1)
    req_horizon = horizon if horizon is not None else 3

    try:
        values, dates = get_consumption_series_from_db(db)
        latest_reading_d = get_latest_reading_date(db)

        # Train ML model (ARIMA or Gradient Boosting) targeting tomorrow onwards
        pipe = train_and_evaluate_forecasting_pipeline(
            values=values,
            dates=dates,
            horizon_days=max(req_horizon, 3),
            target_start_date=tomorrow,
            model_type=model_type,
        )

        # Sync generated predictions to SQLite database
        sync_forecast_to_db(db, pipe["forecast_days"], model_name=pipe["model_name"])

        # Construct forecast days list (Target 1: Tomorrow, Target 2: Day after tomorrow, etc.)
        days: List[ForecastDay] = []
        for idx, fd in enumerate(pipe["forecast_days"][:req_horizon]):
            days.append(
                ForecastDay(
                    date=fd["date"],
                    day_name=fd["day_name"],
                    predicted_kwh=fd["predicted_kwh"],
                    lower_bound_kwh=fd["lower_bound_kwh"],
                    upper_bound_kwh=fd["upper_bound_kwh"],
                    is_peak=fd["is_peak"],
                    forecast_date=fd["forecast_date"].strftime("%Y-%m-%d"),
                    status="predicted",
                    is_extrapolated_gap=pipe.get("is_extrapolated_gap", False),
                )
            )

        p1 = pipe["forecast_days"][0]["predicted_kwh"]
        p2 = pipe["forecast_days"][1]["predicted_kwh"]

        if pipe.get("is_extrapolated_gap"):
            # Display historical boundary alongside extrapolated future targets
            chart_labels = [
                dates[-3].strftime("%b %d"),
                dates[-2].strftime("%b %d"),
                f"{dates[-1].strftime('%b %d')} (Latest)",
                f"{pipe['forecast_days'][0]['forecast_date'].strftime('%b %d')} (Tomorrow)",
                pipe["forecast_days"][1]["forecast_date"].strftime("%b %d"),
            ]
            actual_series = [round(float(values[-3]), 1), round(float(values[-2]), 1), round(float(values[-1]), 1), None, None]
            forecast_series = [None, None, None, p1, p2]
        else:
            # Consecutive series
            chart_labels = [
                dates[-3].strftime("%b %d"),
                dates[-2].strftime("%b %d"),
                dates[-1].strftime("%b %d"),
                f"{pipe['forecast_days'][0]['forecast_date'].strftime('%b %d')} (Tomorrow)",
                pipe["forecast_days"][1]["forecast_date"].strftime("%b %d"),
            ]
            actual_series = [round(float(values[-3]), 1), round(float(values[-2]), 1), round(float(values[-1]), 1), None, None]
            forecast_series = [None, None, round(float(values[-1]), 1), p1, p2]

        return ForecastResponse(
            model=pipe.get("model_name", "arima").lower().replace(" ", "_").replace("(", "").replace(")", ""),
            model_name=pipe["model_name"],
            is_real_model=True,
            is_computed=True,
            note=pipe["note"],
            days=days,
            chart_labels=chart_labels,
            actual_series=actual_series,
            forecast_series=forecast_series,
            training_data_points=pipe["training_data_points"],
            train_samples=pipe["train_samples"],
            test_samples=pipe["test_samples"],
            evaluation_split=pipe["evaluation_split"],
            mae=pipe["mae"],
            rmse=pipe["rmse"],
            baseline_model=pipe["baseline_model"],
            baseline_mae=pipe["baseline_mae"],
            baseline_rmse=pipe["baseline_rmse"],
            data_source="simulated",
            limitations=pipe["limitations"],
            current_date=str(today),
            latest_historical_date=str(latest_reading_d or dates[-1]),
            gap_days=pipe.get("gap_days", 0),
            is_extrapolated_gap=pipe.get("is_extrapolated_gap", False),
            forecast_status="extrapolated_forward" if pipe.get("is_extrapolated_gap") else "consecutive",
            forecast_generation_date=str(today),
        )
    except Exception as err:
        # Fallback to safe static baseline if training fails or data is insufficient
        d2 = tomorrow + timedelta(days=1)
        d3 = tomorrow + timedelta(days=2)
        return ForecastResponse(
            model="static_seed_fallback",
            model_name="Static Seed Fallback",
            is_real_model=False,
            is_computed=False,
            note=f"Machine learning pipeline fallback triggered: {err}. Returning static baseline.",
            days=[
                ForecastDay(
                    date=tomorrow.strftime("%A, %b %d"),
                    day_name="Tomorrow",
                    predicted_kwh=35.4,
                    lower_bound_kwh=33.0,
                    upper_bound_kwh=37.5,
                    is_peak=False,
                    forecast_date=tomorrow.strftime("%Y-%m-%d"),
                    status="fallback",
                ),
                ForecastDay(
                    date=d2.strftime("%A, %b %d"),
                    day_name=d2.strftime("%a, %b %d"),
                    predicted_kwh=37.2,
                    lower_bound_kwh=34.5,
                    upper_bound_kwh=39.8,
                    is_peak=False,
                    forecast_date=d2.strftime("%Y-%m-%d"),
                    status="fallback",
                ),
                ForecastDay(
                    date=d3.strftime("%A, %b %d"),
                    day_name=d3.strftime("%a, %b %d"),
                    predicted_kwh=38.1,
                    lower_bound_kwh=35.2,
                    upper_bound_kwh=41.0,
                    is_peak=False,
                    forecast_date=d3.strftime("%Y-%m-%d"),
                    status="fallback",
                ),
            ],
            chart_labels=["Sep 6", "Sep 7", "Sep 8", tomorrow.strftime("%b %d"), d2.strftime("%b %d")],
            actual_series=[33.9, 33.9, 35.4, None, None],
            forecast_series=[None, None, 35.4, 37.2, 38.1],
            current_date=str(today),
            latest_historical_date="2026-09-17",
            gap_days=max(0, (tomorrow - date(2026, 9, 17)).days - 1),
            is_extrapolated_gap=True,
            forecast_status="fallback",
            forecast_generation_date=str(today),
        )
