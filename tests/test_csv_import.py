"""Unit and API test suite for CSV meter readings import."""
from datetime import datetime, timezone
import io
import unittest
from starlette.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import MeterReading
from backend.services.csv_import import parse_and_validate_csv, parse_timestamp_flexible


class TestCSVValidation(unittest.TestCase):
    """Unit tests for CSV parsing and validation logic."""

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_empty_csv_raises(self):
        """Empty string or whitespace raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            parse_and_validate_csv("", self.db)
        self.assertIn("empty", str(ctx.exception).lower())

        with self.assertRaises(ValueError):
            parse_and_validate_csv("   \n\n  ", self.db)

    def test_missing_required_columns_raises(self):
        """Missing any required header raises ValueError."""
        # Missing consumption_kwh
        csv_data = "timestamp,meter_id\n2026-09-15 10:00:00,EW-TEST-01\n"
        with self.assertRaises(ValueError) as ctx:
            parse_and_validate_csv(csv_data, self.db)
        self.assertIn("consumption_kwh", str(ctx.exception))

        # Missing timestamp
        csv_data2 = "consumption_kwh,meter_id\n2.5,EW-TEST-01\n"
        with self.assertRaises(ValueError) as ctx:
            parse_and_validate_csv(csv_data2, self.db)
        self.assertIn("timestamp", str(ctx.exception))

        # Missing meter_id
        csv_data3 = "timestamp,consumption_kwh\n2026-09-15 10:00:00,2.5\n"
        with self.assertRaises(ValueError) as ctx:
            parse_and_validate_csv(csv_data3, self.db)
        self.assertIn("meter_id", str(ctx.exception))

    def test_invalid_values_all_rows_raises(self):
        """File with only invalid values raises ValueError (maps to 400)."""
        csv_data = (
            "timestamp,consumption_kwh,meter_id\n"
            "invalid_date,2.5,EW-TEST-01\n"
            "2026-09-15 10:00:00,-5.0,EW-TEST-01\n"
            "2026-09-15 12:00:00,not_a_number,EW-TEST-01\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse_and_validate_csv(csv_data, self.db)
        self.assertIn("no valid readings", str(ctx.exception).lower())

    def test_partial_valid_rows_imported(self):
        """Valid rows are imported while invalid rows are recorded in rejected count."""
        ts = f"2026-11-01 10:00:00"
        csv_data = (
            "timestamp,consumption_kwh,meter_id\n"
            f"{ts},3.5,EW-PARTIAL-01\n"
            "2026-11-01 12:00:00,-1.0,EW-PARTIAL-01\n"  # Invalid negative
        )
        try:
            result = parse_and_validate_csv(csv_data, self.db)
            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(result["rejected_invalid_count"], 1)
            self.assertEqual(result["status"], "partial_success")
        finally:
            # Clean up test row
            self.db.query(MeterReading).filter(MeterReading.meter_id == "EW-PARTIAL-01").delete()
            self.db.commit()

    def test_intra_file_duplicate_skipped(self):
        """Duplicate rows in the same CSV file are detected and skipped."""
        ts = "2026-11-02 10:00:00"
        csv_data = (
            "timestamp,consumption_kwh,meter_id\n"
            f"{ts},2.5,EW-DEDUP-01\n"
            f"{ts},2.5,EW-DEDUP-01\n"  # Duplicate row
        )
        try:
            result = parse_and_validate_csv(csv_data, self.db)
            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(result["skipped_duplicates_count"], 1)
        finally:
            self.db.query(MeterReading).filter(MeterReading.meter_id == "EW-DEDUP-01").delete()
            self.db.commit()

    def test_empty_meter_id_rejected(self):
        """Row with empty or whitespace meter_id is rejected."""
        csv_data = (
            "timestamp,consumption_kwh,meter_id\n"
            "2026-11-03T10:00:00,2.5,EW-VALID-01\n"
            "2026-11-03T11:00:00,3.0,   \n"  # Empty meter_id
        )
        try:
            result = parse_and_validate_csv(csv_data, self.db)
            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(result["rejected_invalid_count"], 1)
            self.assertTrue(any("meter_id cannot be empty" in d for d in result["details"]))
        finally:
            self.db.query(MeterReading).filter(MeterReading.meter_id == "EW-VALID-01").delete()
            self.db.commit()

    def test_invalid_timestamp_rejected(self):
        """Row with unparseable timestamp format is rejected."""
        csv_data = (
            "timestamp,consumption_kwh,meter_id\n"
            "2026-11-04T10:00:00,2.5,EW-VALID-02\n"
            "not-a-valid-timestamp,3.0,EW-VALID-02\n"  # Bad timestamp
        )
        try:
            result = parse_and_validate_csv(csv_data, self.db)
            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(result["rejected_invalid_count"], 1)
            self.assertTrue(any("invalid timestamp format" in d for d in result["details"]))
        finally:
            self.db.query(MeterReading).filter(MeterReading.meter_id == "EW-VALID-02").delete()
            self.db.commit()

    def test_negative_consumption_rejected(self):
        """Row with negative consumption value is rejected."""
        csv_data = (
            "timestamp,consumption_kwh,meter_id\n"
            "2026-11-05T10:00:00,2.5,EW-VALID-03\n"
            "2026-11-05T11:00:00,-2.5,EW-VALID-03\n"  # Negative consumption
        )
        try:
            result = parse_and_validate_csv(csv_data, self.db)
            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(result["rejected_invalid_count"], 1)
            self.assertTrue(any("cannot be negative" in d for d in result["details"]))
        finally:
            self.db.query(MeterReading).filter(MeterReading.meter_id == "EW-VALID-03").delete()
            self.db.commit()

    def test_database_duplicate_deduplicated(self):
        """Existing database readings are skipped as duplicates upon re-import."""
        ts = datetime(2026, 11, 6, 10, 0, 0)
        test_meter = "EW-DB-DEDUP-01"
        try:
            # 1. Pre-insert a reading into DB
            existing = MeterReading(
                meter_id=test_meter,
                timestamp=ts,
                usage_kwh=2.8,
                voltage_v=230.0,
                current_a=12.5,
                power_factor=0.96,
                status="Normal",
                source="simulated",
                reading_type="hourly",
            )
            self.db.add(existing)
            self.db.commit()

            # 2. Try importing CSV containing the same reading
            csv_data = (
                "timestamp,consumption_kwh,meter_id\n"
                f"2026-11-06T10:00:00,2.8,{test_meter}\n"
            )
            result = parse_and_validate_csv(csv_data, self.db)
            self.assertEqual(result["imported_count"], 0)
            self.assertEqual(result["skipped_duplicates_count"], 1)
            self.assertEqual(result["status"], "skipped")

            # Verify total count in DB remains exactly 1
            total_in_db = self.db.query(MeterReading).filter(MeterReading.meter_id == test_meter).count()
            self.assertEqual(total_in_db, 1)
        finally:
            self.db.query(MeterReading).filter(MeterReading.meter_id == test_meter).delete()
            self.db.commit()

    def test_timestamp_parser_formats(self):
        """Flexible timestamp parser handles multiple ISO and datetime formats."""
        self.assertIsNotNone(parse_timestamp_flexible("2026-09-08 14:00:00"))
        self.assertIsNotNone(parse_timestamp_flexible("2026-09-08T14:00:00"))
        self.assertIsNotNone(parse_timestamp_flexible("2026-09-08T14:00:00Z"))
        self.assertIsNotNone(parse_timestamp_flexible("2026-09-08"))
        self.assertIsNone(parse_timestamp_flexible("not_a_date"))


class TestCSVImportAPI(unittest.TestCase):
    """API integration tests for /api/readings/upload-csv."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_upload_missing_file_returns_400(self):
        """Empty request body returns HTTP 400."""
        res = self.client.post("/api/readings/upload-csv", content="")
        self.assertEqual(res.status_code, 400)
        self.assertIn("empty", res.json()["detail"].lower())

    def test_upload_missing_columns_returns_400(self):
        """Uploading CSV with missing columns returns HTTP 400."""
        csv_bytes = b"time,power\n2026-09-08 10:00:00,3.5\n"
        res = self.client.post(
            "/api/readings/upload-csv",
            files={"file": ("readings.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Missing required column", res.json()["detail"])

    def test_upload_invalid_values_all_returns_400(self):
        """Uploading CSV where all rows have invalid values returns HTTP 400."""
        csv_bytes = b"timestamp,consumption_kwh,meter_id\n2026-09-08 10:00:00,-99.0,EW-TEST\n"
        res = self.client.post(
            "/api/readings/upload-csv",
            files={"file": ("readings.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("No valid readings found", res.json()["detail"])

    def test_upload_valid_csv_and_deduplicate(self):
        """Upload valid CSV file, then verify re-upload skips duplicate readings."""
        db = SessionLocal()
        test_meter = "EW-TEST-API-01"
        try:
            csv_content = (
                "timestamp,consumption_kwh,meter_id\n"
                f"2026-11-10 08:00:00,2.4,{test_meter}\n"
                f"2026-11-10 10:00:00,3.1,{test_meter}\n"
                f"2026-11-10 12:00:00,4.2,{test_meter}\n"
            )
            # 1. First upload -> should import 3 rows
            res = self.client.post(
                "/api/readings/upload-csv",
                files={"file": ("meter_readings.csv", csv_content.encode("utf-8"), "text/csv")},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["imported_count"], 3)
            self.assertEqual(data["skipped_duplicates_count"], 0)
            self.assertEqual(data["rejected_invalid_count"], 0)
            self.assertEqual(data["status"], "success")

            # 2. Second upload -> should skip all 3 as duplicates
            res2 = self.client.post(
                "/api/readings/upload-csv",
                files={"file": ("meter_readings.csv", csv_content.encode("utf-8"), "text/csv")},
            )
            self.assertEqual(res2.status_code, 200)
            data2 = res2.json()
            self.assertEqual(data2["imported_count"], 0)
            self.assertEqual(data2["skipped_duplicates_count"], 3)
            self.assertEqual(data2["status"], "skipped")
        finally:
            db.query(MeterReading).filter(MeterReading.meter_id == test_meter).delete()
            db.commit()
            db.close()

    def test_upload_raw_body(self):
        """Direct raw text/csv upload works seamlessly."""
        db = SessionLocal()
        test_meter = "EW-RAW-BODY-01"
        try:
            csv_content = (
                "timestamp,consumption_kwh,meter_id\n"
                f"2026-11-11 08:00:00,2.7,{test_meter}\n"
            )
            res = self.client.post(
                "/api/readings/upload-csv",
                content=csv_content,
                headers={"Content-Type": "text/csv"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["imported_count"], 1)
        finally:
            db.query(MeterReading).filter(MeterReading.meter_id == test_meter).delete()
            db.commit()
            db.close()

    def test_sample_csv_file_is_valid(self):
        """The sample file data/meter_readings.csv has 168 hourly rows, ISO format, and valid ranges."""
        import csv
        import re
        from datetime import datetime, timedelta

        with open("data/meter_readings.csv", "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        # 1. Header verification
        self.assertGreater(len(lines), 1)
        header = lines[0].split(",")
        self.assertEqual(header, ["timestamp", "consumption_kwh", "meter_id"])

        # 2. Row count: exactly 168 data rows (7 days * 24 hours)
        data_lines = lines[1:]
        self.assertEqual(len(data_lines), 168)

        reader = csv.DictReader(lines)
        rows = list(reader)
        self.assertEqual(len(rows), 168)

        iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        prev_dt = None
        night_samples = []
        peak_samples = []

        for idx, row in enumerate(rows, start=1):
            ts_str = row["timestamp"]
            kwh_str = row["consumption_kwh"]
            meter = row["meter_id"]

            # ISO timestamp format check
            self.assertTrue(iso_pattern.match(ts_str), f"Row {idx}: '{ts_str}' is not in YYYY-MM-DDTHH:MM:SS format")
            dt = datetime.fromisoformat(ts_str)

            # Strict 1-hour chronological step
            if prev_dt is not None:
                self.assertEqual(dt - prev_dt, timedelta(hours=1), f"Row {idx}: timestamp {dt} not 1 hour after {prev_dt}")
            prev_dt = dt

            # Consistent meter ID
            self.assertEqual(meter, "EW-2847-HH", f"Row {idx}: expected meter EW-2847-HH, got {meter}")

            # Positive and sensible consumption bounds
            kwh = float(kwh_str)
            self.assertGreater(kwh, 0.0, f"Row {idx}: consumption must be positive, got {kwh}")
            self.assertLess(kwh, 6.0, f"Row {idx}: consumption unusually high for domestic sample, got {kwh}")

            # Collect night vs evening values for profile validation
            if dt.hour in (2, 3, 4):
                night_samples.append(kwh)
            elif dt.hour in (19, 20, 21):
                peak_samples.append(kwh)

        # Verify date range: 2026-09-11T00:00:00 to 2026-09-17T23:00:00
        self.assertEqual(rows[0]["timestamp"], "2026-09-11T00:00:00")
        self.assertEqual(rows[-1]["timestamp"], "2026-09-17T23:00:00")

        # Verify overnight usage is noticeably lower than evening peak
        avg_night = sum(night_samples) / len(night_samples)
        avg_peak = sum(peak_samples) / len(peak_samples)
        self.assertLess(avg_night, avg_peak * 0.4, f"Night avg {avg_night} should be significantly lower than peak avg {avg_peak}")

    def test_repeated_import_sample_does_not_duplicate_in_db(self):
        """Uploading sample CSV data twice does not duplicate readings in the database."""
        db = SessionLocal()
        test_meter = "EW-TEST-REPEAT-168"
        try:
            with open("data/meter_readings.csv", "r", encoding="utf-8") as f:
                content = f.read()
            # Replace sample meter ID with isolated test meter ID
            test_content = content.replace("EW-2847-HH", test_meter)

            # 1. First upload
            res1 = self.client.post(
                "/api/readings/upload-csv",
                files={"file": ("meter_readings.csv", test_content.encode("utf-8"), "text/csv")},
            )
            self.assertEqual(res1.status_code, 200)
            data1 = res1.json()
            self.assertEqual(data1["imported_count"], 168)
            self.assertEqual(data1["skipped_duplicates_count"], 0)
            self.assertEqual(data1["rejected_invalid_count"], 0)

            # Verify exactly 168 records in DB
            db_count_1 = db.query(MeterReading).filter(MeterReading.meter_id == test_meter).count()
            self.assertEqual(db_count_1, 168)

            # 2. Second upload of exact same CSV
            res2 = self.client.post(
                "/api/readings/upload-csv",
                files={"file": ("meter_readings.csv", test_content.encode("utf-8"), "text/csv")},
            )
            self.assertEqual(res2.status_code, 200)
            data2 = res2.json()
            self.assertEqual(data2["imported_count"], 0)
            self.assertEqual(data2["skipped_duplicates_count"], 168)
            self.assertEqual(data2["status"], "skipped")

            # Verify DB record count remains strictly 168 (no duplicates)
            db_count_2 = db.query(MeterReading).filter(MeterReading.meter_id == test_meter).count()
            self.assertEqual(db_count_2, 168)
        finally:
            db.query(MeterReading).filter(MeterReading.meter_id == test_meter).delete()
            db.commit()
            db.close()


class TestReadingsFilterAll(unittest.TestCase):
    """Test the 'all' filter on /api/readings."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_readings_filter_all(self):
        """GET /api/readings?filter=all returns list of readings."""
        res = self.client.get("/api/readings?filter=all")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)


if __name__ == "__main__":
    unittest.main()
