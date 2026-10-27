"""Comprehensive unit and API test suite for Phase 4 ML forecasting pipeline.

Tests cover:
- Time series input validation (insufficient data, nulls, negatives, non-chronological dates)
- Autoregressive feature extraction (shapes, lag correctness, day-of-week encoding)
- Chronological train/test splitting (no data leakage verification)
- Evaluation metric calculations (MAE, RMSE)
- Full pipeline end-to-end execution and result structure
- Graceful fallback when ML training fails
- FastAPI /api/forecast endpoint contract and response structure
- Regression checks for all existing endpoints
"""
import unittest
from datetime import date, timedelta
from typing import List
from unittest.mock import patch

import numpy as np
from starlette.testclient import TestClient

from backend.main import app
from backend.services.forecasting import (
    DEFAULT_SIMULATED_30D_DATES,
    DEFAULT_SIMULATED_30D_VALUES,
    MIN_REQUIRED_SAMPLES,
    validate_time_series,
    prepare_autoregressive_features,
    chronological_train_test_split,
    compute_evaluation_metrics,
    train_and_evaluate_forecasting_pipeline,
)


class TestTimeSeriesValidation(unittest.TestCase):
    """Tests for validate_time_series input guard."""

    def test_insufficient_data_raises(self):
        """Less than MIN_REQUIRED_SAMPLES data points raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            validate_time_series([1.0, 2.0, 3.0])
        self.assertIn("Insufficient data", str(ctx.exception))

    def test_empty_list_raises(self):
        """Empty list raises ValueError."""
        with self.assertRaises(ValueError):
            validate_time_series([])

    def test_none_value_raises(self):
        """None values in the series raise ValueError."""
        values = [1.0] * 15
        values[7] = None
        with self.assertRaises(ValueError) as ctx:
            validate_time_series(values)
        self.assertIn("Null value", str(ctx.exception))

    def test_negative_value_raises(self):
        """Negative consumption values raise ValueError."""
        values = [1.0] * 15
        values[5] = -3.2
        with self.assertRaises(ValueError) as ctx:
            validate_time_series(values)
        self.assertIn("Negative consumption", str(ctx.exception))

    def test_nan_value_raises(self):
        """NaN values raise ValueError."""
        values = [1.0] * 15
        values[3] = float('nan')
        with self.assertRaises(ValueError):
            validate_time_series(values)

    def test_non_chronological_dates_raise(self):
        """Out-of-order dates raise ValueError."""
        values = [1.0] * 15
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(15)]
        dates[10], dates[11] = dates[11], dates[10]
        with self.assertRaises(ValueError) as ctx:
            validate_time_series(values, dates)
        self.assertIn("chronological", str(ctx.exception))

    def test_mismatched_dates_values_raises(self):
        """Mismatched lengths between values and dates raise ValueError."""
        values = [1.0] * 15
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(10)]
        with self.assertRaises(ValueError):
            validate_time_series(values, dates)

    def test_valid_series_passes(self):
        """A well-formed series of sufficient length passes without error."""
        validate_time_series(
            DEFAULT_SIMULATED_30D_VALUES,
            DEFAULT_SIMULATED_30D_DATES,
        )

    def test_exactly_min_samples_passes(self):
        """Exactly MIN_REQUIRED_SAMPLES points passes."""
        values = [10.0] * MIN_REQUIRED_SAMPLES
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(MIN_REQUIRED_SAMPLES)]
        validate_time_series(values, dates)


class TestFeatureExtraction(unittest.TestCase):
    """Tests for prepare_autoregressive_features."""

    def test_feature_matrix_shape(self):
        """Feature matrix has (n-2) rows and 4 columns for lag_order=2."""
        X, y, td = prepare_autoregressive_features(
            DEFAULT_SIMULATED_30D_VALUES,
            DEFAULT_SIMULATED_30D_DATES,
        )
        self.assertEqual(X.shape, (28, 4))
        self.assertEqual(len(y), 28)
        self.assertEqual(len(td), 28)

    def test_lag_values_correct(self):
        """Lag-1 and lag-2 columns correspond to correct historical observations."""
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(5)]
        X, y, _ = prepare_autoregressive_features(values, dates)
        # Row 0: t=2 -> lag_1=values[1]=20, lag_2=values[0]=10
        self.assertEqual(X[0, 0], 20.0)
        self.assertEqual(X[0, 1], 10.0)
        # Row 0 target = values[2] = 30
        self.assertEqual(y[0], 30.0)

    def test_rolling_mean_correct(self):
        """Rolling mean column is the average of lag-1 and lag-2."""
        values = [10.0, 20.0, 30.0, 40.0]
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(4)]
        X, _, _ = prepare_autoregressive_features(values, dates)
        # Row 0: rolling_mean = (20+10)/2 = 15
        self.assertEqual(X[0, 2], 15.0)

    def test_day_of_week_encoding(self):
        """Day-of-week column reflects Python's weekday() (0=Mon, 6=Sun)."""
        values = [1.0, 2.0, 3.0]
        dates = [date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28)]
        X, _, _ = prepare_autoregressive_features(values, dates)
        # Oct 28, 2026 is a Wednesday -> weekday() = 2
        self.assertEqual(X[0, 3], 2.0)

    def test_target_dates_start_at_lag_order(self):
        """Target dates begin at index 2 (lag_order=2), skipping the first two."""
        X, _, td = prepare_autoregressive_features(
            DEFAULT_SIMULATED_30D_VALUES,
            DEFAULT_SIMULATED_30D_DATES,
        )
        self.assertEqual(td[0], DEFAULT_SIMULATED_30D_DATES[2])


class TestChronologicalSplit(unittest.TestCase):
    """Tests for chronological_train_test_split."""

    def test_no_data_leakage(self):
        """Every training date strictly precedes every test date."""
        X, y, td = prepare_autoregressive_features(
            DEFAULT_SIMULATED_30D_VALUES,
            DEFAULT_SIMULATED_30D_DATES,
        )
        split = chronological_train_test_split(X, y, td)
        max_train_date = split["train_dates"][-1]
        min_test_date = split["test_dates"][0]
        self.assertLess(max_train_date, min_test_date)

    def test_split_proportions(self):
        """80/20 split yields approximately 80% train samples."""
        X, y, td = prepare_autoregressive_features(
            DEFAULT_SIMULATED_30D_VALUES,
            DEFAULT_SIMULATED_30D_DATES,
        )
        split = chronological_train_test_split(X, y, td, train_ratio=0.8)
        total = len(y)
        expected_train = int(total * 0.8)
        self.assertEqual(len(split["y_train"]), expected_train)
        self.assertEqual(len(split["y_test"]), total - expected_train)

    def test_too_few_samples_raises(self):
        """Very small datasets that can't be split meaningfully raise ValueError."""
        X = np.array([[1, 2, 3, 4], [5, 6, 7, 8]])
        y = np.array([1.0, 2.0])
        td = [date(2026, 1, 1), date(2026, 1, 2)]
        with self.assertRaises(ValueError):
            chronological_train_test_split(X, y, td, train_ratio=0.8)


class TestEvaluationMetrics(unittest.TestCase):
    """Tests for compute_evaluation_metrics."""

    def test_perfect_predictions(self):
        """Identical predictions yield MAE=0 and RMSE=0."""
        y = np.array([10.0, 20.0, 30.0])
        metrics = compute_evaluation_metrics(y, y)
        self.assertEqual(metrics["mae"], 0.0)
        self.assertEqual(metrics["rmse"], 0.0)

    def test_known_error(self):
        """Known constant error yields expected MAE and RMSE."""
        y_true = np.array([10.0, 20.0, 30.0])
        y_pred = np.array([12.0, 22.0, 32.0])
        metrics = compute_evaluation_metrics(y_true, y_pred)
        self.assertAlmostEqual(metrics["mae"], 2.0, places=3)
        self.assertAlmostEqual(metrics["rmse"], 2.0, places=3)


class TestFullPipeline(unittest.TestCase):
    """Tests for the end-to-end train_and_evaluate_forecasting_pipeline."""

    def test_pipeline_returns_required_keys(self):
        """Pipeline output contains all expected fields."""
        result = train_and_evaluate_forecasting_pipeline()
        required_keys = [
            "model_name", "is_real_model", "is_computed", "data_source",
            "training_data_points", "train_samples", "test_samples",
            "train_window", "test_window", "mae", "rmse",
            "baseline_model", "baseline_mae", "baseline_rmse",
            "evaluation_split", "forecast_days", "note", "limitations",
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_pipeline_produces_3_forecast_days(self):
        """Default 3-day horizon returns exactly 3 forecast days."""
        result = train_and_evaluate_forecasting_pipeline()
        self.assertEqual(len(result["forecast_days"]), 3)

    def test_forecast_days_have_required_fields(self):
        """Each forecast day contains date, predicted_kwh, and bounds."""
        result = train_and_evaluate_forecasting_pipeline()
        for fd in result["forecast_days"]:
            self.assertIn("date", fd)
            self.assertIn("predicted_kwh", fd)
            self.assertIn("lower_bound_kwh", fd)
            self.assertIn("upper_bound_kwh", fd)
            self.assertIsInstance(fd["predicted_kwh"], float)
            self.assertGreater(fd["predicted_kwh"], 0)
            self.assertLessEqual(fd["lower_bound_kwh"], fd["predicted_kwh"])
            self.assertGreaterEqual(fd["upper_bound_kwh"], fd["predicted_kwh"])

    def test_pipeline_metrics_are_positive(self):
        """MAE and RMSE are non-negative."""
        result = train_and_evaluate_forecasting_pipeline()
        self.assertGreaterEqual(result["mae"], 0)
        self.assertGreaterEqual(result["rmse"], 0)
        self.assertGreaterEqual(result["baseline_mae"], 0)
        self.assertGreaterEqual(result["baseline_rmse"], 0)

    def test_pipeline_is_marked_computed(self):
        """Successful pipeline is flagged is_real_model=True and is_computed=True."""
        result = train_and_evaluate_forecasting_pipeline()
        self.assertTrue(result["is_real_model"])
        self.assertTrue(result["is_computed"])

    def test_pipeline_simulated_data_source(self):
        """Data source is labelled as simulated."""
        result = train_and_evaluate_forecasting_pipeline()
        self.assertEqual(result["data_source"], "simulated")

    def test_insufficient_data_raises_pipeline(self):
        """Pipeline raises ValueError for tiny datasets."""
        with self.assertRaises(ValueError):
            train_and_evaluate_forecasting_pipeline(values=[1.0, 2.0, 3.0])

    def test_custom_horizon(self):
        """Pipeline respects custom horizon_days parameter."""
        result = train_and_evaluate_forecasting_pipeline(horizon_days=5)
        self.assertEqual(len(result["forecast_days"]), 5)

    def test_forecast_dates_are_sequential(self):
        """Forecast dates are consecutive and after the last historical date."""
        result = train_and_evaluate_forecasting_pipeline()
        last_hist = DEFAULT_SIMULATED_30D_DATES[-1]
        for i, fd in enumerate(result["forecast_days"]):
            expected = last_hist + timedelta(days=i + 1)
            self.assertEqual(fd["forecast_date"], expected)

    def test_limitations_approximate_interval_disclaimer(self):
        """Limitations explicitly disclaim guaranteed confidence intervals."""
        result = train_and_evaluate_forecasting_pipeline()
        limitations = result.get("limitations", "")
        self.assertIn("approximate experimental prediction intervals", limitations)
        self.assertIn("not guaranteed confidence intervals", limitations)


class TestForecastAPI(unittest.TestCase):
    """Integration tests for the /api/forecast endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_forecast_endpoint_200(self):
        """GET /api/forecast returns 200."""
        res = self.client.get("/api/forecast")
        self.assertEqual(res.status_code, 200)

    def test_forecast_response_contract(self):
        """Response contains all ForecastResponse schema fields."""
        res = self.client.get("/api/forecast")
        data = res.json()
        self.assertIn("model", data)
        self.assertIn("days", data)
        self.assertIn("chart_labels", data)
        self.assertIn("actual_series", data)
        self.assertIn("forecast_series", data)
        self.assertIn("is_real_model", data)
        self.assertIn("is_computed", data)
        self.assertIn("note", data)
        self.assertIsInstance(data["days"], list)
        self.assertGreater(len(data["days"]), 0)

    def test_forecast_includes_ml_metrics(self):
        """ML-computed response includes MAE, RMSE, and baseline comparison."""
        res = self.client.get("/api/forecast")
        data = res.json()
        if data.get("is_computed"):
            self.assertIsNotNone(data.get("mae"))
            self.assertIsNotNone(data.get("rmse"))
            self.assertIsNotNone(data.get("baseline_mae"))
            self.assertIsNotNone(data.get("evaluation_split"))

    def test_forecast_chart_data_structure(self):
        """Chart labels, actual_series, and forecast_series have matching lengths."""
        res = self.client.get("/api/forecast")
        data = res.json()
        n_labels = len(data["chart_labels"])
        self.assertEqual(len(data["actual_series"]), n_labels)
        self.assertEqual(len(data["forecast_series"]), n_labels)

    @patch("backend.routers.forecast.train_and_evaluate_forecasting_pipeline")
    def test_forecast_fallback_on_pipeline_error(self, mock_pipe):
        """Pipeline failure safely triggers static baseline fallback without claiming ML success."""
        mock_pipe.side_effect = ValueError("Synthetic insufficient data simulation error")
        res = self.client.get("/api/forecast")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["is_real_model"], "Fallback must not claim to be a real ML model")
        self.assertFalse(data["is_computed"], "Fallback must not claim to be computed")
        self.assertEqual(data["model"], "static_seed_fallback")
        self.assertIn("fallback", data["note"].lower())
        self.assertEqual(len(data["days"]), 3)


class TestRegressionExistingEndpoints(unittest.TestCase):
    """Regression tests to ensure existing endpoints are not broken."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        """GET /health returns 200."""
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_metrics_endpoint(self):
        """GET /api/metrics returns 200 with expected fields."""
        res = self.client.get("/api/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("today_kwh", data)
        self.assertIn("month_kwh", data)
        self.assertIn("estimated_bill_inr", data)

    def test_consumption_7d(self):
        """GET /api/consumption?range=7d returns 200."""
        self.assertEqual(self.client.get("/api/consumption?range=7d").status_code, 200)

    def test_consumption_30d(self):
        """GET /api/consumption?range=30d returns 200."""
        self.assertEqual(self.client.get("/api/consumption?range=30d").status_code, 200)

    def test_readings_today(self):
        """GET /api/readings?filter=today returns 200."""
        self.assertEqual(self.client.get("/api/readings?filter=today").status_code, 200)

    def test_readings_week(self):
        """GET /api/readings?filter=week returns 200."""
        self.assertEqual(self.client.get("/api/readings?filter=week").status_code, 200)

    def test_alerts_endpoint(self):
        """GET /api/alerts returns 200."""
        self.assertEqual(self.client.get("/api/alerts").status_code, 200)

    def test_bill_estimate_default(self):
        """GET /api/bill-estimate defaults to 420 kWh and returns 200."""
        res = self.client.get("/api/bill-estimate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["consumption_kwh"], 420.0)
        self.assertEqual(data["estimated_total_rounded_inr"], 2778)

    def test_bill_estimate_negative_422(self):
        """GET /api/bill-estimate with negative consumption returns 422."""
        self.assertEqual(self.client.get("/api/bill-estimate?consumption_kwh=-5").status_code, 422)


if __name__ == "__main__":
    unittest.main()
