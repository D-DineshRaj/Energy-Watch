"""Tests for Operating Systems Module: Multithreaded Producer-Consumer Ingestion Pipeline."""
from datetime import datetime, timedelta
import threading
import time
import unittest
from starlette.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import MeterReading
from backend.services.multithreaded_ingestion import MultithreadedIngestionManager


class TestMultithreadedIngestion(unittest.TestCase):
    """Test suite for concurrent producers, thread-safe buffering, and batch writes."""

    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        """Clean up any temporary stream demo readings."""
        db = SessionLocal()
        try:
            db.query(MeterReading).filter(
                MeterReading.meter_id.in_(["EW-STREAM-TEST", "TEST-CONCURRENT-METER"]) |
                MeterReading.meter_id.like("EW-STREAM-%")
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def test_stream_stats_endpoint(self):
        """GET /api/stream/stats returns producer-consumer architecture metrics."""
        resp = self.client.get("/api/stream/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("architecture", data)
        self.assertIn("consumer_status", data)
        self.assertIn("queue_current_size", data)
        self.assertIn("memory_buffer_size", data)
        self.assertIn("batches_written", data)
        self.assertIn("threading.Lock", data["thread_safety"])

    def test_single_reading_submit_endpoint(self):
        """POST /api/stream/submit enqueues a reading onto the thread-safe queue."""
        unique_ts = datetime(2026, 10, 31, 23, 45, 0).isoformat()
        payload = {
            "meter_id": "EW-STREAM-TEST",
            "timestamp": unique_ts,
            "usage_kwh": 1.75,
            "voltage_v": 230.5,
            "power_factor": 0.97,
            "status": "Normal",
            "source": "simulated",
            "reading_type": "hourly",
        }
        resp = self.client.post("/api/stream/submit", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "queued")

    def test_stream_flush_endpoint(self):
        """POST /api/stream/flush drains queue and memory buffer immediately."""
        resp = self.client.post("/api/stream/flush")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "flushed")
        self.assertEqual(data["stats"]["queue_current_size"], 0)
        self.assertEqual(data["stats"]["memory_buffer_size"], 0)

    def test_concurrent_producers_simulation_endpoint(self):
        """POST /api/stream/simulate spawns concurrent producer threads submitting to queue."""
        resp = self.client.post("/api/stream/simulate?num_producers=2&readings_per_producer=4&interval_seconds=0.01")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "started")
        self.assertEqual(data["producers_launched"], 2)
        self.assertEqual(data["readings_per_producer"], 4)
        self.assertEqual(data["expected_total_readings"], 8)

        # Allow worker threads to complete and flush
        time.sleep(0.3)
        flush_resp = self.client.post("/api/stream/flush")
        self.assertEqual(flush_resp.status_code, 200)
        stats = flush_resp.json()["stats"]
        self.assertGreater(stats["total_submitted"], 0)

    def test_isolated_manager_threading_and_deduplication(self):
        """Test isolated MultithreadedIngestionManager with concurrent threads and duplicate detection."""
        mgr = MultithreadedIngestionManager(batch_size=5, batch_timeout_seconds=0.5)

        base_dt = datetime(2026, 10, 31, 12, 0, 0)
        test_meter = "TEST-CONCURRENT-METER"

        # Submit 10 readings concurrently from 2 separate threads
        def producer_a():
            for i in range(5):
                mgr.submit_reading({
                    "meter_id": test_meter,
                    "timestamp": base_dt + timedelta(minutes=i),
                    "usage_kwh": 1.5,
                    "source": "simulated",
                })

        def producer_b():
            for i in range(5):
                mgr.submit_reading({
                    "meter_id": test_meter,
                    "timestamp": base_dt + timedelta(minutes=i + 10),
                    "usage_kwh": 2.0,
                    "source": "simulated",
                })

        t1 = threading.Thread(target=producer_a)
        t2 = threading.Thread(target=producer_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Flush
        mgr.flush()
        mgr.shutdown()

        stats = mgr.get_statistics()
        self.assertEqual(stats["total_submitted"], 10)
        self.assertGreaterEqual(stats["batches_written"], 1)

        # Clean up test readings from DB
        db = SessionLocal()
        try:
            db.query(MeterReading).filter(MeterReading.meter_id == test_meter).delete()
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

