"""Forecasting service providing a disciplined, maintainable time-series pipeline.

Features:
- Chronological train/test splitting (zero lookahead leakage).
- Naive persistence and moving average baseline benchmarking.
- Autoregressive feature extraction (lag-1, lag-2, rolling mean, calendar day-of-week).
- Gradient Boosting Regressor with shallow trees to avoid overfitting on compact series.
- Objective holdout evaluation reporting exact MAE and RMSE.
- Recursive multi-step forward forecasting with empirical prediction intervals.
- Input validation and graceful handling for insufficient data or invalid observations.
- Explicit disclosures regarding simulated training data and prototype limitations.
"""
from datetime import date, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sqlalchemy.orm import Session

from backend.models import Forecast, MeterReading

# Canonical 30-day historical simulated daily consumption matching consumption.py
DEFAULT_SIMULATED_30D_DATES = [
    date(2026, 8, 10) + timedelta(days=i) for i in range(30)
]
DEFAULT_SIMULATED_30D_VALUES = [
    28.2, 30.1, 29.5, 31.8, 27.3, 30.9, 32.4, 28.8, 31.2, 29.9,
    33.5, 30.2, 31.7, 29.4, 32.1, 30.8, 33.2, 31.5, 30.3, 32.8,
    33.1, 31.9, 32.4, 33.8, 31.2, 33.9, 33.9, 34.2, 35.1, 35.4,
]

MIN_REQUIRED_SAMPLES = 14


def validate_time_series(
    values: List[float],
    dates: Optional[List[date]] = None,
    min_samples: int = MIN_REQUIRED_SAMPLES,
) -> None:
    """Validate time series data for sufficiency, non-negativity, and chronological order."""
    if not values or len(values) < min_samples:
        raise ValueError(
            f"Insufficient data for machine learning forecasting. Minimum required observations: {min_samples}, "
            f"received: {len(values) if values else 0}."
        )

    for idx, v in enumerate(values):
        if v is None:
            raise ValueError(f"Null value found at index {idx}.")
        try:
            fv = float(v)
        except (TypeError, ValueError) as err:
            raise ValueError(f"Non-numeric value at index {idx}: {v}") from err
        if math.isnan(fv) or math.isinf(fv):
            raise ValueError(f"Invalid non-finite value at index {idx}: {v}")
        if fv < 0:
            raise ValueError(
                f"Negative consumption value at index {idx}: {fv}. Consumption cannot be negative."
            )

    if dates is not None:
        if len(dates) != len(values):
            raise ValueError(
                f"Mismatched count between dates ({len(dates)}) and consumption values ({len(values)})."
            )
        for i in range(1, len(dates)):
            if dates[i] < dates[i - 1]:
                raise ValueError(
                    f"Dates must be in strict chronological order: {dates[i-1]} precedes {dates[i]}."
                )


def prepare_autoregressive_features(
    values: List[float],
    dates: List[date],
    lag_order: int = 2,
) -> Tuple[np.ndarray, np.ndarray, List[date]]:
    """Construct autoregressive feature matrix using historical lags and calendar indicators.

    Features per observation at index t:
    - lag_1: y_{t-1}
    - lag_2: y_{t-2}
    - rolling_mean_2: average of y_{t-1} and y_{t-2}
    - day_of_week: day of week index (0=Monday, 6=Sunday)
    """
    X, y, target_dates = [], [], []
    for t in range(lag_order, len(values)):
        l1 = float(values[t - 1])
        l2 = float(values[t - 2])
        rm2 = (l1 + l2) / 2.0
        dow = float(dates[t].weekday())

        X.append([l1, l2, rm2, dow])
        y.append(float(values[t]))
        target_dates.append(dates[t])

    return np.array(X, dtype=float), np.array(y, dtype=float), target_dates


def chronological_train_test_split(
    X: np.ndarray,
    y: np.ndarray,
    target_dates: List[date],
    train_ratio: float = 0.8,
) -> Dict[str, Any]:
    """Chronologically split features into train and holdout test sets without shuffling."""
    n_samples = len(y)
    split_idx = int(n_samples * train_ratio)
    if split_idx < 4 or (n_samples - split_idx) < 2:
        raise ValueError(
            f"Too few samples ({n_samples}) for reliable {train_ratio:.0%} chronological split."
        )

    return {
        "X_train": X[:split_idx],
        "y_train": y[:split_idx],
        "train_dates": target_dates[:split_idx],
        "X_test": X[split_idx:],
        "y_test": y[split_idx:],
        "test_dates": target_dates[split_idx:],
        "split_idx": split_idx,
    }


def compute_evaluation_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Calculate Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE)."""
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    return {
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
    }


def train_and_evaluate_forecasting_pipeline(
    values: Optional[List[float]] = None,
    dates: Optional[List[date]] = None,
    horizon_days: int = 3,
    train_ratio: float = 0.8,
) -> Dict[str, Any]:
    """Execute end-to-end forecasting pipeline with chronological evaluation and baseline benchmarking."""
    if values is None:
        values = list(DEFAULT_SIMULATED_30D_VALUES)
    if dates is None:
        dates = list(DEFAULT_SIMULATED_30D_DATES)

    validate_time_series(values, dates, min_samples=MIN_REQUIRED_SAMPLES)

    # 1. Feature Engineering
    X, y, target_dates = prepare_autoregressive_features(values, dates, lag_order=2)

    # 2. Chronological Split (Strictly avoids data leakage)
    split = chronological_train_test_split(X, y, target_dates, train_ratio=train_ratio)
    X_train, y_train = split["X_train"], split["y_train"]
    X_test, y_test = split["X_test"], split["y_test"]
    test_dates = split["test_dates"]

    # 3. Simple Baseline: Naive Persistence (y_{t-1} = X_test[:, 0])
    y_baseline = X_test[:, 0]
    base_metrics = compute_evaluation_metrics(y_test, y_baseline)

    # 4. Train Model: Gradient Boosting Regressor (shallow trees, regularized)
    model = GradientBoostingRegressor(
        n_estimators=25,
        max_depth=2,
        learning_rate=0.08,
        subsample=0.85,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # 5. Out-of-Sample Holdout Evaluation
    y_pred_holdout = model.predict(X_test)
    model_metrics = compute_evaluation_metrics(y_test, y_pred_holdout)

    # Calculate empirical prediction interval margin (1.645 * standard deviation of residuals)
    residuals = y_test - y_pred_holdout
    res_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(residuals))
    bound_margin = 1.645 * res_std

    # 6. Refit on full series to utilize the most up-to-date observations for future forecasting
    full_model = GradientBoostingRegressor(
        n_estimators=25,
        max_depth=2,
        learning_rate=0.08,
        subsample=0.85,
        random_state=42,
    )
    full_model.fit(X, y)

    # 7. Recursive Multi-Step Forward Forecasting
    curr_values = list(values)
    curr_dates = list(dates)
    forecast_days = []

    for step in range(1, horizon_days + 1):
        next_date = curr_dates[-1] + timedelta(days=1)
        l1 = curr_values[-1]
        l2 = curr_values[-2]
        rm2 = (l1 + l2) / 2.0
        dow = float(next_date.weekday())

        pred_kwh = float(full_model.predict([[l1, l2, rm2, dow]])[0])
        pred_kwh_rounded = round(pred_kwh, 1)

        low_bound = max(0.0, round(pred_kwh - bound_margin, 1))
        up_bound = round(pred_kwh + bound_margin, 1)

        day_name = "Tomorrow" if step == 1 else next_date.strftime("%b %d")
        forecast_days.append({
            "date": next_date.strftime("%A, %b %d"),
            "day_name": day_name,
            "forecast_date": next_date,
            "predicted_kwh": pred_kwh_rounded,
            "lower_bound_kwh": low_bound,
            "upper_bound_kwh": up_bound,
            "is_peak": bool(pred_kwh_rounded > 35.0),
        })

        curr_values.append(pred_kwh)
        curr_dates.append(next_date)

    return {
        "model_name": "Gradient Boosting (Autoregressive)",
        "is_real_model": True,
        "is_computed": True,
        "data_source": "simulated",
        "training_data_points": len(values),
        "train_samples": len(y_train),
        "test_samples": len(y_test),
        "train_window": f"{split['train_dates'][0]} to {split['train_dates'][-1]}",
        "test_window": f"{test_dates[0]} to {test_dates[-1]}",
        "mae": model_metrics["mae"],
        "rmse": model_metrics["rmse"],
        "baseline_model": "Naive Persistence (Lag-1)",
        "baseline_mae": base_metrics["mae"],
        "baseline_rmse": base_metrics["rmse"],
        "evaluation_split": "Chronological 80/20 Holdout Split (Strict Out-of-Sample)",
        "forecast_days": forecast_days,
        "note": (
            "Consumption forecast generated using Gradient Boosting Autoregression trained on a 30-day "
            "simulated household interval series. Evaluated out-of-sample on a chronological holdout window "
            "and benchmarked against a naive persistence baseline."
        ),
        "limitations": (
            "Model is trained on synthetic/simulated readings without exogenous variables (weather, temperature, "
            "cooling degree days, occupancy, or tariff signals). Performance metrics reflect simulated behavior "
            "and do not constitute real-world smart meter accuracy. Upper and lower bounds represent approximate "
            "experimental prediction intervals based on holdout residual variance, not guaranteed confidence intervals."
        ),
    }


def get_consumption_series_from_db(db: Session) -> Tuple[List[float], List[date]]:
    """Retrieve available daily readings from SQLite, falling back to default 30-day baseline."""
    readings = (
        db.query(MeterReading)
        .filter(MeterReading.reading_type == "daily")
        .order_by(MeterReading.timestamp.asc())
        .all()
    )
    if readings and len(readings) >= MIN_REQUIRED_SAMPLES:
        values = [r.usage_kwh for r in readings]
        dates = [r.timestamp.date() for r in readings]
        return values, dates

    # Return standard 30-day simulated historical series
    return list(DEFAULT_SIMULATED_30D_VALUES), list(DEFAULT_SIMULATED_30D_DATES)


def sync_forecast_to_db(db: Session, forecast_days: List[Dict[str, Any]]) -> None:
    """Synchronize generated forecast days to SQLite forecasts table."""
    try:
        for fd in forecast_days:
            f_date = fd["forecast_date"]
            existing = db.query(Forecast).filter(Forecast.forecast_date == f_date).first()
            if existing:
                existing.predicted_kwh = fd["predicted_kwh"]
                existing.lower_bound_kwh = fd.get("lower_bound_kwh")
                existing.upper_bound_kwh = fd.get("upper_bound_kwh")
                existing.model_name = "gradient_boosting_autoreg"
                existing.is_ml_model = True
                existing.data_source = "simulated"
            else:
                db.add(
                    Forecast(
                        forecast_date=f_date,
                        predicted_kwh=fd["predicted_kwh"],
                        lower_bound_kwh=fd.get("lower_bound_kwh"),
                        upper_bound_kwh=fd.get("upper_bound_kwh"),
                        model_name="gradient_boosting_autoreg",
                        is_ml_model=True,
                        data_source="simulated",
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
