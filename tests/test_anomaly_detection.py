"""Unit and API test suite for automated energy anomaly detection and alert generation."""
from datetime import datetime, timedelta, timezone
import unittest
from starlette.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import Alert, MeterReading
from backend.services.anomaly_detection import (
    compute_baseline_stats,
    evaluate_reading_for_anomaly,
    scan_and_generate_alerts,
)


class TestStatisticalBaseline(unittest.TestCase):
    """Test elementary statistical baseline and variance calculations."""

    def test_empty_list(self):
        """Empty list yields mean=0, std=0, n=0."""
        mean, std, n = compute_baseline_stats([])
        self.assertEqual(mean, 0.0)
        self.assertEqual(std, 0.0)
        self.assertEqual(n, 0)

    def test_single_value(self):
        """Single value yields mean=val, std=0, n=1."""
        mean, std, n = compute_baseline_stats([2.5])
        self.assertEqual(mean, 2.5)
        self.assertEqual(std, 0.0)
        self.assertEqual(n, 1)

    def test_zero_variance(self):
        """Identical values yield std=0."""
        mean, std, n = compute_baseline_stats([3.0, 3.0, 3.0, 3.0])
        self.assertEqual(mean, 3.0)
        self.assertEqual(std, 0.0)
        self.assertEqual(n, 4)

    def test_known_mean_and_std(self):
        """Known distribution yields expected sample statistics."""
        # [2.0, 4.0]: mean=3.0, sample variance=((2-3)^2 + (4-3)^2)/1 = 2.0, sample std=sqrt(2) ~= 1.414
        mean, std, n = compute_baseline_stats([2.0, 4.0])
        self.assertEqual(mean, 3.0)
        self.assertAlmostEqual(std, 1.414, places=3)
        self.assertEqual(n, 2)


class TestAnomalyEvaluationRules(unittest.TestCase):
    """Unit tests for evaluate_reading_for_anomaly logic and edge cases."""

    def setUp(self):
        self.meter_id = "EW-TEST-ANOMALY-RULES"

    def _make_reading(self, id_val: int, dt: datetime, kwh: float) -> MeterReading:
        return MeterReading(
            id=id_val,
            meter_id=self.meter_id,
            timestamp=dt,
            usage_kwh=kwh,
            voltage_v=230.0,
            status="High" if kwh > 8.0 else "Normal",
            source="simulated",
            reading_type="hourly",
        )

    def test_normal_reading_within_distribution(self):
        """Normal reading within 1 standard deviation is not an anomaly."""
        base_dt = datetime(2026, 9, 15, 14, 0, 0)
        history = [
            self._make_reading(1, base_dt - timedelta(days=3), 2.2),
            self._make_reading(2, base_dt - timedelta(days=2), 2.4),
            self._make_reading(3, base_dt - timedelta(days=1), 2.3),
        ]
        candidate = self._make_reading(4, base_dt, 2.5)

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_kwh_threshold=4.0)
        self.assertFalse(res["is_anomaly"])
        self.assertEqual(res["status"], "normal")

    def test_high_consumption_spike_flagged(self):
        """High consumption spike exceeding Z-score threshold is flagged as an anomaly."""
        base_dt = datetime(2026, 9, 15, 20, 0, 0)
        # Baseline evening load around 2.5 kWh
        history = [
            self._make_reading(1, base_dt - timedelta(days=4), 2.4),
            self._make_reading(2, base_dt - timedelta(days=3), 2.6),
            self._make_reading(3, base_dt - timedelta(days=2), 2.5),
            self._make_reading(4, base_dt - timedelta(days=1), 2.5),
        ]
        # Massive spike to 9.2 kWh
        candidate = self._make_reading(5, base_dt, 9.2)

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_kwh_threshold=4.5)
        self.assertTrue(res["is_anomaly"])
        self.assertEqual(res["status"], "anomaly_detected")
        self.assertGreater(res["z_score"], 2.5)

    def test_below_absolute_min_kwh_not_flagged(self):
        """Small spike in tiny overnight load is not flagged when below min_kwh_threshold."""
        base_dt = datetime(2026, 9, 15, 3, 0, 0)
        history = [
            self._make_reading(1, base_dt - timedelta(days=3), 0.22),
            self._make_reading(2, base_dt - timedelta(days=2), 0.23),
            self._make_reading(3, base_dt - timedelta(days=1), 0.22),
        ]
        # 0.45 kWh is double 0.22, but still negligible household power (below 4.5 kWh threshold)
        candidate = self._make_reading(4, base_dt, 0.45)

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_kwh_threshold=4.5)
        self.assertFalse(res["is_anomaly"])
        self.assertIn("below minimum anomaly threshold", res["reason"])

    def test_insufficient_history_handled_safely(self):
        """Fewer than min_samples returns is_anomaly=False with status 'insufficient_history'."""
        base_dt = datetime(2026, 9, 15, 12, 0, 0)
        history = [
            self._make_reading(1, base_dt - timedelta(days=1), 2.5),
        ]  # Only 1 prior reading, min_samples=3
        candidate = self._make_reading(2, base_dt, 9.0)

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_samples=3)
        self.assertFalse(res["is_anomaly"])
        self.assertEqual(res["status"], "insufficient_history")
        self.assertIn("Insufficient historical data", res["reason"])

    def test_zero_variance_handled_safely(self):
        """Zero variance in historical readings avoids division-by-zero errors."""
        base_dt = datetime(2026, 9, 15, 12, 0, 0)
        # All historical values exactly 2.0 kWh
        history = [
            self._make_reading(1, base_dt - timedelta(days=3), 2.0),
            self._make_reading(2, base_dt - timedelta(days=2), 2.0),
            self._make_reading(3, base_dt - timedelta(days=1), 2.0),
        ]
        # Candidate of 8.0 kWh is 300% above 2.0 and above min_kwh
        candidate = self._make_reading(4, base_dt, 8.0)

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_kwh_threshold=4.5)
        self.assertTrue(res["is_anomaly"])
        self.assertIn("Zero variance baseline", res["reason"])

    def test_historical_only_baseline_excludes_candidate_and_future_readings(self):
        """Historical baseline strictly excludes future readings and candidate reading itself."""
        base_dt = datetime(2026, 9, 15, 12, 0, 0)
        history = [
            self._make_reading(1, base_dt - timedelta(days=3), 2.0),
            self._make_reading(2, base_dt - timedelta(days=2), 2.0),
            self._make_reading(3, base_dt - timedelta(days=1), 2.0),
            self._make_reading(4, base_dt, 8.0),                     # Candidate itself
            self._make_reading(5, base_dt + timedelta(days=1), 9.9), # Future reading 1
            self._make_reading(6, base_dt + timedelta(days=2), 9.9), # Future reading 2
        ]
        candidate = history[3]  # reading 4 at base_dt

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_kwh_threshold=4.5)
        # Only the 3 prior readings should be included in sample count
        self.assertEqual(res["sample_count"], 3)
        self.assertEqual(res["baseline_mean"], 2.0)
        self.assertTrue(res["is_anomaly"])

    def test_multi_meter_isolation_in_evaluation(self):
        """Evaluation strictly excludes readings belonging to other meters."""
        base_dt = datetime(2026, 9, 15, 12, 0, 0)
        history = [
            # Meter A (target meter) prior readings around 2.0 kWh
            self._make_reading(1, base_dt - timedelta(days=3), 2.0),
            self._make_reading(2, base_dt - timedelta(days=2), 2.0),
            self._make_reading(3, base_dt - timedelta(days=1), 2.0),
            # Foreign Meter B readings with massive consumption
            MeterReading(id=10, meter_id="EW-FOREIGN-METER", timestamp=base_dt - timedelta(days=3), usage_kwh=25.0, reading_type="hourly"),
            MeterReading(id=11, meter_id="EW-FOREIGN-METER", timestamp=base_dt - timedelta(days=2), usage_kwh=30.0, reading_type="hourly"),
        ]
        candidate = self._make_reading(4, base_dt, 7.5)

        res = evaluate_reading_for_anomaly(candidate, history, z_threshold=2.5, min_kwh_threshold=4.5)
        self.assertEqual(res["sample_count"], 3)
        self.assertEqual(res["baseline_mean"], 2.0)
        self.assertTrue(res["is_anomaly"])


class TestAlertGenerationAndDeduplication(unittest.TestCase):
    """Database integration tests for alert creation and duplicate prevention."""

    def setUp(self):
        self.db = SessionLocal()
        self.test_meter = "EW-TEST-ALERT-GEN"

    def tearDown(self):
        # Clean up test alerts and readings
        test_reading_ids = [
            r[0] for r in self.db.query(MeterReading.id).filter(MeterReading.meter_id == self.test_meter).all()
        ]
        if test_reading_ids:
            self.db.query(Alert).filter(Alert.reading_id.in_(test_reading_ids)).delete(synchronize_session=False)
            self.db.query(MeterReading).filter(MeterReading.id.in_(test_reading_ids)).delete(synchronize_session=False)
            self.db.commit()
        self.db.close()

    def test_alert_created_for_spike_and_not_duplicated(self):
        """Anomalous reading creates an Alert, and re-running scan does NOT create duplicates."""
        base_dt = datetime(2026, 11, 20, 20, 0, 0)
        readings = [
            MeterReading(meter_id=self.test_meter, timestamp=base_dt - timedelta(days=3), usage_kwh=2.4, status="Normal"),
            MeterReading(meter_id=self.test_meter, timestamp=base_dt - timedelta(days=2), usage_kwh=2.5, status="Normal"),
            MeterReading(meter_id=self.test_meter, timestamp=base_dt - timedelta(days=1), usage_kwh=2.5, status="Normal"),
            MeterReading(meter_id=self.test_meter, timestamp=base_dt, usage_kwh=9.5, status="High"),  # Spike
        ]
        self.db.add_all(readings)
        self.db.commit()

        # 1. First scan -> Should create 1 alert
        res1 = scan_and_generate_alerts(
            db=self.db,
            meter_id=self.test_meter,
            candidate_readings=[readings[-1]],
            z_threshold=2.5,
            min_kwh_threshold=4.5,
        )
        self.assertEqual(res1["anomalies_detected"], 1)
        self.assertEqual(res1["alerts_created"], 1)
        self.assertEqual(res1["alerts_skipped_existing"], 0)

        # Verify alert exists in database
        alerts_in_db = self.db.query(Alert).filter(Alert.reading_id == readings[-1].id).all()
        self.assertEqual(len(alerts_in_db), 1)
        alert = alerts_in_db[0]
        self.assertEqual(alert.alert_type, "unusual_consumption")
        self.assertEqual(alert.severity, "critical")
        self.assertFalse(alert.acknowledged)
        self.assertIn("9.5 kWh", alert.message)

        # 2. Second scan on same reading -> Must skip duplicate alert creation
        res2 = scan_and_generate_alerts(
            db=self.db,
            meter_id=self.test_meter,
            candidate_readings=[readings[-1]],
            z_threshold=2.5,
            min_kwh_threshold=4.5,
        )
        self.assertEqual(res2["anomalies_detected"], 1)
        self.assertEqual(res2["alerts_created"], 0)
        self.assertEqual(res2["alerts_skipped_existing"], 1)

        # Database alert count must strictly remain 1
        alerts_in_db_after = self.db.query(Alert).filter(Alert.reading_id == readings[-1].id).count()
        self.assertEqual(alerts_in_db_after, 1)

    def test_scan_multi_meter_isolation(self):
        """Multi-meter scan keeps baselines and alerts completely isolated between meters."""
        base_dt = datetime(2026, 11, 20, 18, 0, 0)
        meter_a = "EW-TEST-ISO-A"
        meter_b = "EW-TEST-ISO-B"
        readings = [
            # Meter A: 3 baseline readings at 2.0 kWh, then a spike to 7.0 kWh
            MeterReading(meter_id=meter_a, timestamp=base_dt - timedelta(days=3), usage_kwh=2.0, status="Normal"),
            MeterReading(meter_id=meter_a, timestamp=base_dt - timedelta(days=2), usage_kwh=2.0, status="Normal"),
            MeterReading(meter_id=meter_a, timestamp=base_dt - timedelta(days=1), usage_kwh=2.0, status="Normal"),
            MeterReading(meter_id=meter_a, timestamp=base_dt, usage_kwh=7.0, status="High"),
            # Meter B: 3 baseline readings at 8.0 kWh, then a normal 8.2 kWh reading
            MeterReading(meter_id=meter_b, timestamp=base_dt - timedelta(days=3), usage_kwh=8.0, status="High"),
            MeterReading(meter_id=meter_b, timestamp=base_dt - timedelta(days=2), usage_kwh=8.0, status="High"),
            MeterReading(meter_id=meter_b, timestamp=base_dt - timedelta(days=1), usage_kwh=8.0, status="High"),
            MeterReading(meter_id=meter_b, timestamp=base_dt, usage_kwh=8.2, status="High"),
        ]
        self.db.add_all(readings)
        self.db.commit()

        try:
            # Candidate list containing both meters' 4th reading
            candidates = [readings[3], readings[7]]
            res = scan_and_generate_alerts(db=self.db, candidate_readings=candidates)

            # Meter A should trigger an anomaly, Meter B should NOT
            self.assertEqual(res["total_scanned"], 2)
            self.assertEqual(res["anomalies_detected"], 1)
            self.assertEqual(res["alerts_created"], 1)

            # Verify the alert is linked strictly to Meter A
            alert = self.db.query(Alert).filter(Alert.reading_id == readings[3].id).first()
            self.assertIsNotNone(alert)
            self.assertIn(meter_a, alert.message)

            # Meter B must have 0 alerts
            meter_b_alerts = self.db.query(Alert).filter(Alert.reading_id == readings[7].id).count()
            self.assertEqual(meter_b_alerts, 0)
        finally:
            ids = [r.id for r in readings if r.id is not None]
            self.db.query(Alert).filter(Alert.reading_id.in_(ids)).delete(synchronize_session=False)
            self.db.query(MeterReading).filter(MeterReading.id.in_(ids)).delete(synchronize_session=False)
            self.db.commit()


class TestCSVImportAnomalyIntegration(unittest.TestCase):
    """Test automated anomaly detection when importing CSV files."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_csv_upload_with_anomaly_triggers_alert(self):
        """CSV containing a consumption spike automatically triggers an alert on import."""
        db = SessionLocal()
        test_meter = "EW-CSV-ANOMALY-01"
        try:
            # 3 baseline days at 20:00 + 1 massive spike day at 20:00
            csv_content = (
                "timestamp,consumption_kwh,meter_id\n"
                f"2026-11-21T20:00:00,2.5,{test_meter}\n"
                f"2026-11-22T20:00:00,2.6,{test_meter}\n"
                f"2026-11-23T20:00:00,2.4,{test_meter}\n"
                f"2026-11-24T20:00:00,9.8,{test_meter}\n"  # Anomaly spike
            )

            # 1. First upload -> should import 4 rows and create 1 alert
            res = self.client.post(
                "/api/readings/upload-csv",
                files={"file": ("meter_readings.csv", csv_content.encode("utf-8"), "text/csv")},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["imported_count"], 4)
            self.assertGreater(data.get("anomalies_detected", 0), 0)
            self.assertGreater(data.get("alerts_created", 0), 0)

            # Verify alert created in DB
            spike_reading = db.query(MeterReading).filter(
                MeterReading.meter_id == test_meter,
                MeterReading.usage_kwh == 9.8,
            ).first()
            self.assertIsNotNone(spike_reading)
            alert = db.query(Alert).filter(Alert.reading_id == spike_reading.id).first()
            self.assertIsNotNone(alert)
            self.assertIn("9.8 kWh", alert.message)

            # 2. Second upload of exact same CSV -> skips all readings and creates 0 alerts
            res2 = self.client.post(
                "/api/readings/upload-csv",
                files={"file": ("meter_readings.csv", csv_content.encode("utf-8"), "text/csv")},
            )
            self.assertEqual(res2.status_code, 200)
            data2 = res2.json()
            self.assertEqual(data2["imported_count"], 0)
            self.assertEqual(data2["skipped_duplicates_count"], 4)
            self.assertEqual(data2.get("alerts_created", 0), 0)

            # Total alerts for this test meter must remain exactly 1
            total_alerts = db.query(Alert).join(MeterReading).filter(MeterReading.meter_id == test_meter).count()
            self.assertEqual(total_alerts, 1)

        finally:
            readings = db.query(MeterReading).filter(MeterReading.meter_id == test_meter).all()
            r_ids = [r.id for r in readings]
            if r_ids:
                db.query(Alert).filter(Alert.reading_id.in_(r_ids)).delete(synchronize_session=False)
                db.query(MeterReading).filter(MeterReading.id.in_(r_ids)).delete(synchronize_session=False)
                db.commit()
            db.close()


class TestAnomalyDetectionAPI(unittest.TestCase):
    """API endpoint tests for /api/alerts/detect-anomalies."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_detect_anomalies_endpoint_200(self):
        """POST /api/alerts/detect-anomalies returns HTTP 200 and schema structure."""
        res = self.client.post("/api/alerts/detect-anomalies")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertIn("total_scanned", data)
        self.assertIn("anomalies_detected", data)
        self.assertIn("alerts_created", data)
        self.assertIn("details", data)
        self.assertIsInstance(data["details"], list)

    def test_alerts_lifecycle_acknowledge_and_reset(self):
        """Alerts endpoint supports acknowledge and reset lifecycle."""
        # 1. Fetch active alerts
        res = self.client.get("/api/alerts")
        self.assertEqual(res.status_code, 200)
        alerts = res.json()
        self.assertIsInstance(alerts, list)
        if len(alerts) > 0:
            target_id = alerts[0]["id"]

            # 2. Acknowledge alert
            ack_res = self.client.post(f"/api/alerts/{target_id}/acknowledge")
            self.assertEqual(ack_res.status_code, 200)
            self.assertTrue(ack_res.json()["acknowledged"])

            # 3. Reset alert
            rst_res = self.client.post(f"/api/alerts/{target_id}/reset")
            self.assertEqual(rst_res.status_code, 200)
            self.assertFalse(rst_res.json()["acknowledged"])


if __name__ == "__main__":
    unittest.main()
