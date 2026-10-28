"""Unit and API test suite for Energy Reports and Data Export."""
from datetime import datetime, timedelta
import unittest
from starlette.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import MeterReading
from backend.services.billing import calculate_aperc_bill
from backend.services.reports import (
    generate_consumption_summary,
    generate_readings_csv,
    parse_date_param,
)


class TestReportAggregations(unittest.TestCase):
    """Unit tests for consumption aggregation logic and edge cases."""

    def setUp(self):
        self.db = SessionLocal()
        self.test_meter = "EW-TEST-REPORTS-01"
        # Seed 3 days of readings for test meter:
        # Day 1: 2026-10-01 - 3 hourly readings of 2.0 kWh each (Total: 6.0 kWh)
        # Day 2: 2026-10-02 - 3 hourly readings: 3.0, 5.0, 2.0 kWh (Total: 10.0 kWh, Peak: 5.0 kWh at 14:00)
        # Day 3: 2026-10-03 - 1 daily reading of 8.0 kWh (Total: 8.0 kWh)
        # Other meter reading on Day 2: 50.0 kWh (Must be isolated)
        self.readings = [
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 1, 8, 0), usage_kwh=2.0, reading_type="hourly"),
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 1, 12, 0), usage_kwh=2.0, reading_type="hourly"),
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 1, 18, 0), usage_kwh=2.0, reading_type="hourly"),
            # Co-existing daily summary for Day 1: must NOT be added to hourly readings (avoids double-counting)
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 1, 23, 59, 59), usage_kwh=6.0, reading_type="daily"),

            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 2, 8, 0), usage_kwh=3.0, reading_type="hourly"),
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 2, 14, 0), usage_kwh=5.0, reading_type="hourly"),
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 2, 20, 0), usage_kwh=2.0, reading_type="hourly"),

            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, 3, 23, 59, 59), usage_kwh=8.0, reading_type="daily"),

            # Foreign meter reading (different meter ID, same day)
            MeterReading(meter_id="EW-OTHER-METER", timestamp=datetime(2026, 10, 2, 12, 0), usage_kwh=50.0, reading_type="hourly"),
        ]
        self.db.add_all(self.readings)
        self.db.commit()

    def tearDown(self):
        ids = [r.id for r in self.readings if r.id is not None]
        if ids:
            self.db.query(MeterReading).filter(MeterReading.id.in_(ids)).delete(synchronize_session=False)
            self.db.commit()
        self.db.close()

    def test_full_range_aggregation_totals(self):
        """Report calculates correct totals and daily averages across date window."""
        res = generate_consumption_summary(
            db=self.db,
            start_date="2026-10-01",
            end_date="2026-10-03",
            meter_id=self.test_meter,
            sanctioned_load_kw=1.0,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["meter_id"], self.test_meter)
        # Expected: 6.0 (day 1) + 10.0 (day 2) + 8.0 (day 3) = 24.0 kWh
        self.assertEqual(res["total_consumption_kwh"], 24.0)
        self.assertEqual(res["days_count"], 3)
        self.assertEqual(res["daily_avg_kwh"], 8.0)
        self.assertEqual(res["peak_day"], "2026-10-02")
        self.assertEqual(res["peak_day_kwh"], 10.0)
        self.assertEqual(res["peak_hour_kwh"], 5.0)
        self.assertIn("2026-10-02", res["peak_hour"])
        self.assertEqual(len(res["daily_breakdown"]), 3)

    def test_no_double_counting_hourly_and_daily_summary(self):
        """Verify that a day with both hourly readings and a daily summary does not double-count."""
        res = generate_consumption_summary(
            db=self.db,
            start_date="2026-10-01",
            end_date="2026-10-01",
            meter_id=self.test_meter,
        )
        self.assertEqual(res["status"], "success")
        # Day 1 has 3 hourly readings of 2.0 kWh AND 1 daily summary of 6.0 kWh
        # Daily breakdown must have exactly 6.0 kWh, not 12.0 kWh
        self.assertEqual(res["total_consumption_kwh"], 6.0)
        self.assertEqual(res["daily_breakdown"][0]["consumption_kwh"], 6.0)
        self.assertEqual(res["daily_breakdown"][0]["reading_type"], "hourly")
        self.assertEqual(res["daily_breakdown"][0]["reading_count"], 3)

    def test_date_range_filtering(self):
        """Report excludes readings falling strictly outside the specified date boundaries."""
        # Query only day 2 (2026-10-02)
        res = generate_consumption_summary(
            db=self.db,
            start_date="2026-10-02",
            end_date="2026-10-02",
            meter_id=self.test_meter,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_consumption_kwh"], 10.0)
        self.assertEqual(res["days_count"], 1)
        self.assertEqual(len(res["daily_breakdown"]), 1)
        self.assertEqual(res["daily_breakdown"][0]["date"], "2026-10-02")

    def test_multi_meter_isolation(self):
        """Consumption from other meters is strictly excluded from target meter report."""
        res = generate_consumption_summary(
            db=self.db,
            start_date="2026-10-01",
            end_date="2026-10-03",
            meter_id=self.test_meter,
        )
        # If EW-OTHER-METER (50 kWh) had leaked in, total would be 74.0
        self.assertEqual(res["total_consumption_kwh"], 24.0)

    def test_invalid_date_range_raises(self):
        """Start date after end date raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            generate_consumption_summary(
                db=self.db,
                start_date="2026-10-05",
                end_date="2026-10-01",
                meter_id=self.test_meter,
            )
        self.assertIn("cannot be after end date", str(ctx.exception))

    def test_empty_dataset_handling(self):
        """Gracefully returns empty structure when no readings match date range."""
        res = generate_consumption_summary(
            db=self.db,
            start_date="2025-01-01",
            end_date="2025-01-05",
            meter_id=self.test_meter,
        )
        self.assertEqual(res["status"], "empty")
        self.assertEqual(res["total_consumption_kwh"], 0.0)
        self.assertEqual(res["daily_avg_kwh"], 0.0)
        self.assertEqual(res["days_count"], 0)
        self.assertEqual(res["readings_count"], 0)
        self.assertEqual(res["daily_breakdown"], [])
        self.assertIn("No readings found", res["message"])


class TestBillingIntegrationInReports(unittest.TestCase):
    """Verify that report bill estimation exactly matches the official APERC billing service."""

    def setUp(self):
        self.db = SessionLocal()
        self.test_meter = "EW-TEST-REPORT-BILL"
        # Seed 100 kWh across 4 days (25 kWh each)
        self.readings = [
            MeterReading(meter_id=self.test_meter, timestamp=datetime(2026, 10, i, 12, 0), usage_kwh=25.0, reading_type="hourly")
            for i in range(1, 5)
        ]
        self.db.add_all(self.readings)
        self.db.commit()

    def tearDown(self):
        ids = [r.id for r in self.readings if r.id is not None]
        if ids:
            self.db.query(MeterReading).filter(MeterReading.id.in_(ids)).delete(synchronize_session=False)
            self.db.commit()
        self.db.close()

    def test_bill_calculation_matches_billing_service(self):
        """Report bill estimate precisely mirrors direct calculate_aperc_bill output."""
        summary = generate_consumption_summary(
            db=self.db,
            start_date="2026-10-01",
            end_date="2026-10-04",
            meter_id=self.test_meter,
            sanctioned_load_kw=2.0,
        )
        expected_bill = calculate_aperc_bill(consumption_kwh=100.0, sanctioned_load_kw=2.0)

        self.assertEqual(summary["total_consumption_kwh"], 100.0)
        self.assertEqual(summary["estimated_bill_inr"], float(expected_bill["estimated_total_inr"]))
        self.assertEqual(summary["estimated_bill_rounded_inr"], int(expected_bill["estimated_total_rounded_inr"]))
        self.assertEqual(len(summary["bill_breakdown"]["slabs_breakdown"]), len(expected_bill["slabs_breakdown"]))


class TestCSVExport(unittest.TestCase):
    """Test CSV generation and export formatting."""

    def setUp(self):
        self.db = SessionLocal()
        self.test_meter = "EW-TEST-CSV-EXP"
        self.readings = [
            MeterReading(
                meter_id=self.test_meter,
                timestamp=datetime(2026, 10, 1, 10, 0),
                usage_kwh=3.45,
                voltage_v=230.2,
                current_a=15.1,
                power_factor=0.96,
                status="Normal",
                source="simulated",
                reading_type="hourly",
            ),
            MeterReading(
                meter_id=self.test_meter,
                timestamp=datetime(2026, 10, 1, 11, 0),
                usage_kwh=4.10,
                voltage_v=229.8,
                current_a=18.0,
                power_factor=0.95,
                status="Normal",
                source="simulated",
                reading_type="hourly",
            ),
        ]
        self.db.add_all(self.readings)
        self.db.commit()

    def tearDown(self):
        ids = [r.id for r in self.readings if r.id is not None]
        if ids:
            self.db.query(MeterReading).filter(MeterReading.id.in_(ids)).delete(synchronize_session=False)
            self.db.commit()
        self.db.close()

    def test_csv_export_format_and_headers(self):
        """CSV export contains expected RFC-4180 headers and row values."""
        csv_text, filename, count = generate_readings_csv(
            db=self.db,
            start_date="2026-10-01",
            end_date="2026-10-01",
            meter_id=self.test_meter,
        )
        self.assertEqual(count, 2)
        self.assertIn("energywatch_readings_EW-TEST-CSV-EXP_20261001_20261001.csv", filename)

        lines = [line for line in csv_text.splitlines() if line]
        self.assertEqual(len(lines), 3)  # Header + 2 data rows
        headers = lines[0].split(",")
        self.assertEqual(headers, [
            "timestamp",
            "consumption_kwh",
            "meter_id",
            "voltage_v",
            "current_a",
            "power_factor",
            "status",
            "source",
            "reading_type",
        ])
        self.assertIn("2026-10-01T10:00:00", lines[1])
        self.assertIn("3.45", lines[1])


class TestReportsAPIEndpoints(unittest.TestCase):
    """Integration tests for report REST API endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_report_summary_endpoint(self):
        """GET /api/reports/summary returns HTTP 200 and schema."""
        res = self.client.get("/api/reports/summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_consumption_kwh", data)
        self.assertIn("daily_avg_kwh", data)
        self.assertIn("estimated_bill_inr", data)
        self.assertIn("daily_breakdown", data)
        self.assertIn("bill_breakdown", data)

    def test_get_report_summary_invalid_range_400(self):
        """GET /api/reports/summary with start_date > end_date returns HTTP 400."""
        res = self.client.get("/api/reports/summary?start_date=2026-10-10&end_date=2026-10-01")
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be after end date", res.json()["detail"])

    def test_export_csv_endpoint(self):
        """GET /api/reports/export-csv returns text/csv with download headers."""
        res = self.client.get("/api/reports/export-csv")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/csv"))
        self.assertIn("attachment; filename=", res.headers.get("content-disposition", ""))
        self.assertIn("timestamp,consumption_kwh,meter_id", res.text)

    def test_get_energy_statement_endpoint(self):
        """GET /api/reports/statement returns HTTP 200 with formal statement structure."""
        res = self.client.get("/api/reports/statement")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("statement_id", data)
        self.assertIn("meter_id", data)
        self.assertIn("period_start", data)
        self.assertIn("period_end", data)
        self.assertIn("total_kwh", data)
        self.assertIn("bill_estimate", data)
        self.assertIn("slabs_breakdown", data["bill_estimate"])
        self.assertIn("disclaimer", data)

    def test_statement_matches_summary_totals(self):
        """Printable statement endpoint matches consumption and bill estimate from summary endpoint."""
        sum_res = self.client.get("/api/reports/summary")
        stmt_res = self.client.get("/api/reports/statement")
        self.assertEqual(sum_res.status_code, 200)
        self.assertEqual(stmt_res.status_code, 200)
        sum_data = sum_res.json()
        stmt_data = stmt_res.json()
        self.assertEqual(sum_data["total_consumption_kwh"], stmt_data["total_kwh"])
        self.assertEqual(sum_data["daily_avg_kwh"], stmt_data["daily_avg_kwh"])
        self.assertEqual(
            sum_data["bill_breakdown"]["estimated_total_inr"],
            stmt_data["bill_estimate"]["estimated_total_inr"],
        )


if __name__ == "__main__":
    unittest.main()
