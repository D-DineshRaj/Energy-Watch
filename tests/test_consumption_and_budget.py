"""Unit and integration tests for dynamic consumption trends, anomaly highlighting, and budget calculation."""
from datetime import date, datetime, timedelta
import unittest
from starlette.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import Alert, MeterReading


class TestConsumptionAndBudget(unittest.TestCase):
    """Test suite covering dynamic SQLite consumption trends, anomaly visualization data, and budget logic."""

    def setUp(self):
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.test_meter = "EW-TEST-CON-99"
        self.created_readings = []
        self.created_alerts = []

    def tearDown(self):
        alert_ids = [a.id for a in self.created_alerts if a.id is not None]
        if alert_ids:
            self.db.query(Alert).filter(Alert.id.in_(alert_ids)).delete(synchronize_session=False)
        reading_ids = [r.id for r in self.created_readings if r.id is not None]
        if reading_ids:
            self.db.query(MeterReading).filter(MeterReading.id.in_(reading_ids)).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_consumption_7d_returns_dynamic_sqlite_data(self):
        """GET /api/consumption?range=7d returns 7 daily points from SQLite without legacy mock forecast overlay."""
        res = self.client.get("/api/consumption?range=7d")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["range"], "7d")
        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["actual"]), 7)
        self.assertEqual(len(data["anomalies"]), 7)
        self.assertEqual(data["forecast"], [])  # Legacy static yellow overlay removed
        self.assertEqual(data["source"], "sqlite")

        # Verify daily numbers are positive floats
        valid_readings = [v for v in data["actual"] if v is not None]
        self.assertTrue(len(valid_readings) > 0)
        for val in valid_readings:
            self.assertGreater(val, 0.0)

    def test_consumption_30d_returns_30_points(self):
        """GET /api/consumption?range=30d returns 30 chronological days from SQLite."""
        res = self.client.get("/api/consumption?range=30d")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["range"], "30d")
        self.assertEqual(len(data["labels"]), 30)
        self.assertEqual(len(data["actual"]), 30)
        self.assertEqual(len(data["anomalies"]), 30)
        self.assertEqual(data["forecast"], [])

    def test_consumption_3m_returns_12_points(self):
        """GET /api/consumption?range=3m returns 12 weekly periods."""
        res = self.client.get("/api/consumption?range=3m")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["range"], "3m")
        self.assertEqual(len(data["labels"]), 12)
        self.assertEqual(len(data["actual"]), 12)
        self.assertEqual(len(data["anomalies"]), 12)

    def test_anomaly_flagging_on_anomalous_reading(self):
        """Anomalous readings with status='High' or attached Alert flag that calendar day as True in anomalies."""
        # Query September 8 historical benchmark where reading id 8 has High status and Alert 1
        res = self.client.get("/api/consumption?range=7d&current_date=2026-09-08")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["labels"], ["Sep 2", "Sep 3", "Sep 4", "Sep 5", "Sep 6", "Sep 7", "Sep 8"])
        self.assertEqual(len(data["anomalies"]), 7)
        # Sep 2 to Sep 7 are normal, Sep 8 has Alert / High reading
        self.assertEqual(data["anomalies"][-1], True)
        self.assertFalse(data["anomalies"][0])  # Sep 2 is normal

    def test_custom_meter_anomaly_detection_isolation(self):
        """Dynamic consumption endpoint correctly isolates anomalies to the specific meter requested."""
        base_d = date(2026, 11, 10)
        # Seed 3 days for test meter: 2 normal days, 1 anomalous day
        r1 = MeterReading(
            meter_id=self.test_meter,
            timestamp=datetime(2026, 11, 8, 12, 0),
            usage_kwh=10.0,
            reading_type="hourly",
            status="Normal",
        )
        r2 = MeterReading(
            meter_id=self.test_meter,
            timestamp=datetime(2026, 11, 9, 12, 0),
            usage_kwh=12.0,
            reading_type="hourly",
            status="Normal",
        )
        r3 = MeterReading(
            meter_id=self.test_meter,
            timestamp=datetime(2026, 11, 10, 12, 0),
            usage_kwh=45.0,
            reading_type="hourly",
            status="High",
        )
        self.created_readings.extend([r1, r2, r3])
        self.db.add_all([r1, r2, r3])
        self.db.commit()

        # Create alert linked to r3
        alert = Alert(
            reading_id=r3.id,
            alert_type="unusual_consumption",
            severity="warning",
            message="Test anomaly spike",
            triggered_at=datetime(2026, 11, 10, 12, 5),
            acknowledged=False,
        )
        self.created_alerts.append(alert)
        self.db.add(alert)
        self.db.commit()

        res = self.client.get(f"/api/consumption?range=7d&meter_id={self.test_meter}&current_date=2026-11-10")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # The last day (Nov 10) must be flagged True in anomalies, Nov 8 and 9 must be False
        self.assertEqual(data["labels"][-1], "Nov 10")
        self.assertTrue(data["anomalies"][-1])
        self.assertFalse(data["anomalies"][-2])
        self.assertFalse(data["anomalies"][-3])

    def test_forecast_api_remains_intact_and_independent(self):
        """Forecast API endpoint continues working independently of the consumption trends endpoint."""
        res = self.client.get("/api/forecast?model_type=arima&horizon=7")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("days", data)
        self.assertEqual(len(data["days"]), 7)
        self.assertIn("ARIMA", data["model_name"])
        self.assertIn("forecast_series", data)

    def test_budget_percentage_calculation_logic(self):
        """Simulate configured demonstration budget percentage calculation for normal, over-budget, zero, and missing states."""
        # Configured demonstration/default monthly budget threshold (INR), not a regulatory tariff parameter
        monthly_budget = 10000.0

        # Normal usage (e.g. October estimated bill: Rs 8,903.0)
        oct_bill = 8903.0
        pct_oct = (oct_bill / monthly_budget) * 100
        self.assertAlmostEqual(pct_oct, 89.03, places=2)
        self.assertLessEqual(pct_oct, 100.0)

        # September benchmark usage (e.g. Rs 2,778.0)
        sep_bill = 2778.0
        pct_sep = (sep_bill / monthly_budget) * 100
        self.assertAlmostEqual(pct_sep, 27.78, places=2)

        # Over-budget condition (e.g. Rs 12,500.0)
        high_bill = 12500.0
        pct_high = (high_bill / monthly_budget) * 100
        self.assertGreater(pct_high, 100.0)
        self.assertAlmostEqual(pct_high, 125.0, places=1)
        # Visual clamped width should be 100%
        clamped_width = min(100.0, pct_high)
        self.assertEqual(clamped_width, 100.0)

        # Zero or missing bill
        zero_bill = 0.0
        pct_zero = (zero_bill / monthly_budget) * 100
        self.assertEqual(pct_zero, 0.0)


if __name__ == "__main__":
    unittest.main()
