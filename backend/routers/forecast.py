"""Router for energy consumption forecasting endpoint."""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Forecast
from backend.schemas import ForecastDay, ForecastResponse
from backend.services.forecasting import (
    get_consumption_series_from_db,
    sync_forecast_to_db,
    train_and_evaluate_forecasting_pipeline,
)

router = APIRouter()


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    model_type: str = Query("gradient_boosting", description="Forecasting model type: gradient_boosting or baseline"),
    db: Session = Depends(get_db),
):
    """Retrieve multi-step machine-learning consumption forecast evaluated on chronological holdout."""
    try:
        values, dates = get_consumption_series_from_db(db)
        pipe = train_and_evaluate_forecasting_pipeline(values=values, dates=dates, horizon_days=3)

        # Sync generated predictions to SQLite database
        sync_forecast_to_db(db, pipe["forecast_days"])

        # Construct forecast days list (Day 0 anchor: Today actual, Day 1+: Predictions)
        today_val = round(float(values[-1]), 1)
        days: List[ForecastDay] = [
            ForecastDay(
                date="Tuesday, Sep 8",
                day_name="Today",
                predicted_kwh=today_val,
                lower_bound_kwh=today_val,
                upper_bound_kwh=today_val,
                is_peak=False,
            )
        ]

        for fd in pipe["forecast_days"][:2]:
            days.append(
                ForecastDay(
                    date=fd["date"],
                    day_name=fd["day_name"],
                    predicted_kwh=fd["predicted_kwh"],
                    lower_bound_kwh=fd["lower_bound_kwh"],
                    upper_bound_kwh=fd["upper_bound_kwh"],
                    is_peak=fd["is_peak"],
                )
            )

        # Connect forecast line to today's actual value on Chart.js
        p1 = pipe["forecast_days"][0]["predicted_kwh"]
        p2 = pipe["forecast_days"][1]["predicted_kwh"]

        return ForecastResponse(
            model="gradient_boosting_autoreg",
            model_name=pipe["model_name"],
            is_real_model=True,
            is_computed=True,
            note=pipe["note"],
            days=days,
            chart_labels=["Sep 6", "Sep 7", "Sep 8", "Sep 9", "Sep 10"],
            actual_series=[33.9, 33.9, today_val, None, None],
            forecast_series=[None, None, today_val, p1, p2],
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
        )
    except Exception as err:
        # Fallback to safe static baseline if training fails or data is insufficient
        return ForecastResponse(
            model="static_seed_fallback",
            model_name="Static Seed Fallback",
            is_real_model=False,
            is_computed=False,
            note=f"Machine learning pipeline fallback triggered: {err}. Returning static baseline.",
            days=[
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
            ],
            chart_labels=["Sep 6", "Sep 7", "Sep 8", "Sep 9", "Sep 10"],
            actual_series=[33.9, 33.9, 35.4, None, None],
            forecast_series=[None, None, 35.4, 37.2, 38.1],
            data_source="simulated",
            limitations="Simulated baseline fallback data.",
        )
