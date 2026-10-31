"""Tests for DBMS Module: Meter model, relationships, and metadata API endpoints."""
from datetime import date
import unittest
from starlette.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import app
from backend.models import Meter, MeterReading


class TestDBMSMeters(unittest.TestCase):
    """Test suite for relational smart meters schema, relationships, and endpoints."""

    def setUp(self):
        init_db()
        self.client = TestClient(app)
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_default_meter_exists_in_database(self):
        """Primary meter EW-2847-HH must exist in meters table."""
        meter = self.db.query(Meter).filter(Meter.meter_id == "EW-2847-HH").first()
        self.assertIsNotNone(meter)
        self.assertEqual(meter.meter_id, "EW-2847-HH")
        self.assertEqual(meter.name, "Main Residential Meter")
        self.assertEqual(meter.consumer_name, "Dinesh Raj")
        self.assertEqual(meter.sanctioned_load_kw, 1.0)
        self.assertEqual(meter.status, "Active")

    def test_meter_reading_relationship_bidirectional(self):
        """Meter entity can access its readings and MeterReading can access its Meter."""
        meter = self.db.query(Meter).filter(Meter.meter_id == "EW-2847-HH").first()
        self.assertIsNotNone(meter)
        self.assertGreater(len(meter.readings), 0)

        # Reverse relationship
        sample_reading = meter.readings[0]
        self.assertIsNotNone(sample_reading.meter)
        self.assertEqual(sample_reading.meter.meter_id, "EW-2847-HH")

    def test_list_meters_endpoint(self):
        """GET /api/meters returns list of smart utility meters."""
        resp = self.client.get("/api/meters")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        m_ids = [m["meter_id"] for m in data]
        self.assertIn("EW-2847-HH", m_ids)

    def test_get_meter_details_endpoint(self):
        """GET /api/meters/EW-2847-HH returns detailed meter telemetry and readings count."""
        resp = self.client.get("/api/meters/EW-2847-HH")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["meter_id"], "EW-2847-HH")
        self.assertEqual(data["consumer_name"], "Dinesh Raj")
        self.assertGreater(data["readings_count"], 0)
        self.assertIsNotNone(data["latest_reading_time"])

    def test_get_meter_details_not_found_404(self):
        """GET /api/meters/NON-EXISTENT-ID returns 404 error."""
        resp = self.client.get("/api/meters/NON-EXISTENT-ID")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()

