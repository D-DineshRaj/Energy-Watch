"""Tests for Machine Learning Module: ARIMA forecasting, holdout benchmarking, and simulation."""
from datetime import date, timedelta
import unittest
from starlette.testclient import TestClient

from backend.main import app
from backend.services.forecasting import (
    DEFAULT_SIMULATED_30D_DATES,
    DEFAULT_SIMULATED_30D_VALUES,
    fit_and_forecast_arima,
    train_and_evaluate_forecasting_pipeline,
)
from backend.services.october_simulation import seed_october_simulation
from backend.database import SessionLocal
from backend.models import MeterReading


class TestARIMAForecasting(unittest.TestCase):
    """Test suite for ARIMA forecasting and baseline evaluation."""

    def setUp(self):
        self.client = TestClient(app)

    def test_arima_pipeline_structure_and_metrics(self):
        """ARIMA pipeline returns valid holdout metrics and baseline comparison."""
        result = fit_and_forecast_arima(
            values=DEFAULT_SIMULATED_30D_VALUES,
            dates=DEFAULT_SIMULATED_30D_DATES,
            horizon_days=3,
            train_ratio=0.8,
            target_start_date=date(2026, 11, 1),
        )

        self.assertIn("ARIMA", result["model_name"])
        self.assertTrue(result["is_real_model"])
        self.assertTrue(result["is_computed"])
        self.assertGreater(result["mae"], 0.0)
        self.assertGreater(result["rmse"], 0.0)
        self.assertIn("baseline_mae", result)
        self.assertIn("baseline_rmse", result)
        self.assertIn("Naive Persistence", result["baseline_model"])

        # Horizon predictions
        self.assertEqual(len(result["forecast_days"]), 3)
        for fd in result["forecast_days"]:
            self.assertGreater(fd["predicted_kwh"], 0.0)
            self.assertGreaterEqual(fd["upper_bound_kwh"], fd["lower_bound_kwh"])
            self.assertGreaterEqual(fd["lower_bound_kwh"], 0.0)

    def test_train_and_evaluate_pipeline_model_type_selection(self):
        """Pipeline respects model_type='arima' and model_type='gradient_boosting'."""
        arima_res = train_and_evaluate_forecasting_pipeline(
            values=DEFAULT_SIMULATED_30D_VALUES,
            dates=DEFAULT_SIMULATED_30D_DATES,
            horizon_days=2,
            model_type="arima",
        )
        self.assertIn("ARIMA", arima_res["model_name"])

        gb_res = train_and_evaluate_forecasting_pipeline(
            values=DEFAULT_SIMULATED_30D_VALUES,
            dates=DEFAULT_SIMULATED_30D_DATES,
            horizon_days=2,
            model_type="gradient_boosting",
        )
        self.assertIn("Gradient Boosting", gb_res["model_name"])

    def test_forecast_endpoint_with_arima_model_type(self):
        """GET /api/forecast?model_type=arima returns HTTP 200 with ARIMA predictions."""
        resp = self.client.get("/api/forecast?model_type=arima&horizon=3&current_date=2026-10-31")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("ARIMA", data["model_name"])
        self.assertEqual(len(data["days"]), 3)
        self.assertEqual(data["days"][0]["day_name"], "Tomorrow")
        self.assertEqual(data["days"][0]["forecast_date"], "2026-11-01")

    def test_october_simulation_idempotency(self):
        """Running seed_october_simulation multiple times does NOT create duplicate records."""
        db = SessionLocal()
        try:
            initial_count = db.query(MeterReading).filter(
                MeterReading.meter_id == "EW-2847-HH",
                MeterReading.timestamp >= "2026-10-01",
                MeterReading.timestamp <= "2026-10-31 23:59:59",
            ).count()

            # Run simulation seed again
            second_res = seed_october_simulation(db)
            self.assertEqual(second_res["status"], "already_seeded")
            self.assertEqual(second_res["inserted_count"], 0)

            post_count = db.query(MeterReading).filter(
                MeterReading.meter_id == "EW-2847-HH",
                MeterReading.timestamp >= "2026-10-01",
                MeterReading.timestamp <= "2026-10-31 23:59:59",
            ).count()

            self.assertEqual(initial_count, post_count)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

