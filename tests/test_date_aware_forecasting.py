"""Dedicated test suite for Date-Aware Forecasting, Dashboard Correction & Statement Preview.

Tests cover:
1. Calendar date handling (Asia/Kolkata timezone, month/year boundaries, leap year, date injection)
2. Forecast target dates (tomorrow onwards, calendar day accuracy, dynamic horizon)
3. Forecasting across the data gap (gap calculation, bounds, extrapolation metadata)
4. Metrics behavior on current date (honest empty states for October, historical anchors)
5. Report summaries & bill estimation (September data vs empty October, statement generation)
6. Frontend contract & modal structural integrity (DOM closing tags, Escape handler, body overflow)
"""
import os
import re
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from starlette.testclient import TestClient

from backend.main import app
from backend.services.date_utils import (
    APP_TIMEZONE,
    get_current_date,
    get_current_datetime,
    parse_reference_date,
)
from backend.services.forecasting import (
    DEFAULT_SIMULATED_30D_DATES,
    DEFAULT_SIMULATED_30D_VALUES,
    train_and_evaluate_forecasting_pipeline,
)


class TestCalendarDateHandling(unittest.TestCase):
    """Tests for application timezone and calendar date calculation logic."""

    def test_timezone_asia_kolkata_offset(self):
        """Application timezone must be Asia/Kolkata (UTC+05:30)."""
        now = get_current_datetime()
        self.assertIsNotNone(now.tzinfo)
        offset = now.utcoffset()
        self.assertEqual(offset, timedelta(hours=5, minutes=30))

    def test_environment_variable_date_override(self):
        """ENERGYWATCH_CURRENT_DATE override allows deterministic system-level testing."""
        with patch.dict(os.environ, {"ENERGYWATCH_CURRENT_DATE": "2026-10-31"}):
            self.assertEqual(get_current_date(), date(2026, 10, 31))

    def test_parse_reference_date_formats(self):
        """parse_reference_date correctly parses valid ISO strings and rejects invalid."""
        self.assertEqual(parse_reference_date("2026-10-31"), date(2026, 10, 31))
        self.assertEqual(parse_reference_date("2026-11-01"), date(2026, 11, 1))
        self.assertIsNone(parse_reference_date(None))
        self.assertIsNone(parse_reference_date("invalid-date"))
        self.assertIsNone(parse_reference_date("2026/10/31"))

    def test_month_boundary_transition_oct_to_nov(self):
        """October 31 transitions cleanly to November 1 (Tomorrow) and November 2."""
        ref = date(2026, 10, 31)
        tomorrow = ref + timedelta(days=1)
        day_after = ref + timedelta(days=2)
        self.assertEqual(tomorrow, date(2026, 11, 1))
        self.assertEqual(tomorrow.strftime("%A"), "Sunday")
        self.assertEqual(day_after, date(2026, 11, 2))
        self.assertEqual(day_after.strftime("%A"), "Monday")

    def test_year_boundary_transition_dec_to_jan(self):
        """December 31 transitions cleanly across the year boundary to January 1."""
        ref = date(2026, 12, 31)
        tomorrow = ref + timedelta(days=1)
        day_after = ref + timedelta(days=2)
        self.assertEqual(tomorrow, date(2027, 1, 1))
        self.assertEqual(day_after, date(2027, 1, 2))

    def test_leap_year_transition_feb_28_to_29(self):
        """Leap year 2028 handles February 28 to February 29 correctly."""
        ref = date(2028, 2, 28)
        tomorrow = ref + timedelta(days=1)
        self.assertEqual(tomorrow, date(2028, 2, 29))
        self.assertEqual(tomorrow + timedelta(days=1), date(2028, 3, 1))


class TestForecastTargetDates(unittest.TestCase):
    """Tests for API forecast target date generation relative to current calendar date."""

    def setUp(self):
        self.client = TestClient(app)

    def test_forecast_targets_october_31_are_november_1_and_2(self):
        """Target dates for October 31 must be Nov 01 (Tomorrow) and Nov 02."""
        resp = self.client.get("/api/forecast?current_date=2026-10-31&horizon=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["current_date"], "2026-10-31")
        days = data["days"]
        self.assertEqual(len(days), 2)

        day1 = days[0]
        day2 = days[1]
        self.assertEqual(day1["forecast_date"], "2026-11-01")
        self.assertEqual(day1["day_name"], "Tomorrow")
        self.assertIn("Sunday", day1["date"])

        self.assertEqual(day2["forecast_date"], "2026-11-02")
        self.assertIn("Nov 02", day2["day_name"])
        self.assertIn("Monday", day2["date"])

    def test_forecast_targets_horizon_3(self):
        """Horizon=3 produces target dates for Nov 1, Nov 2, and Nov 3."""
        resp = self.client.get("/api/forecast?current_date=2026-10-31&horizon=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        days = data["days"]
        self.assertEqual(len(days), 3)
        self.assertEqual(days[2]["forecast_date"], "2026-11-03")
        self.assertIn("Tuesday", days[2]["date"])

    def test_forecast_updates_with_arbitrary_future_date(self):
        """Forecast dynamically computes future targets for any arbitrary future reference date."""
        resp = self.client.get("/api/forecast?current_date=2026-11-15&horizon=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["days"][0]["forecast_date"], "2026-11-16")
        self.assertEqual(data["days"][1]["forecast_date"], "2026-11-17")


class TestForecastingAcrossDataGap(unittest.TestCase):
    """Tests for ML extrapolation across the calendar gap without data fabrication."""

    def test_pipeline_extrapolation_metadata(self):
        """Pipeline returns extrapolation flags and gap metadata when forecasting beyond training data."""
        result = train_and_evaluate_forecasting_pipeline(
            dates=DEFAULT_SIMULATED_30D_DATES,
            values=DEFAULT_SIMULATED_30D_VALUES,
            horizon_days=2,
            target_start_date=date(2026, 11, 1),
        )
        self.assertIn("is_extrapolated_gap", result)
        self.assertTrue(result["is_extrapolated_gap"])
        self.assertGreater(result["gap_days"], 30)
        self.assertEqual(str(result["latest_historical_date"]), "2026-09-08")

    def test_forecast_values_positive_and_intervals_valid(self):
        """Forecasted values must be positive, reasonable, and have valid confidence bounds."""
        result = train_and_evaluate_forecasting_pipeline(
            dates=DEFAULT_SIMULATED_30D_DATES,
            values=DEFAULT_SIMULATED_30D_VALUES,
            horizon_days=2,
            target_start_date=date(2026, 11, 1),
        )
        forecast_days = result["forecast_days"]
        self.assertEqual(len(forecast_days), 2)
        for day in forecast_days:
            pred = day["predicted_kwh"]
            low = day["lower_bound_kwh"]
            up = day["upper_bound_kwh"]
            self.assertGreater(pred, 0.0)
            self.assertLess(pred, 100.0)  # Realistic daily domestic consumption
            self.assertGreaterEqual(up, low)
            self.assertGreaterEqual(low, 0.0)

    def test_historical_training_series_unmutated(self):
        """Input training arrays are never modified by the pipeline."""
        dates_copy = list(DEFAULT_SIMULATED_30D_DATES)
        values_copy = list(DEFAULT_SIMULATED_30D_VALUES)
        train_and_evaluate_forecasting_pipeline(
            dates=DEFAULT_SIMULATED_30D_DATES,
            values=DEFAULT_SIMULATED_30D_VALUES,
            horizon_days=2,
            target_start_date=date(2026, 11, 1),
        )
        self.assertEqual(DEFAULT_SIMULATED_30D_DATES, dates_copy)
        self.assertEqual(DEFAULT_SIMULATED_30D_VALUES, values_copy)


class TestMetricsBehaviorOnCurrentDate(unittest.TestCase):
    """Tests for honest metrics representation when current date has no telemetry."""

    def setUp(self):
        self.client = TestClient(app)

    def test_metrics_october_31_returns_populated_demonstration_data(self):
        """October 31 demonstration dashboard returns populated simulated consumption and bill."""
        resp = self.client.get("/api/metrics?current_date=2026-10-31")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["current_date"], "2026-10-31")
        self.assertTrue(data["today_has_data"])
        self.assertIsNotNone(data["today_kwh"])
        self.assertGreater(data["today_kwh"], 25.0)
        self.assertTrue(data["month_has_data"])
        self.assertIsNotNone(data["month_kwh"])
        self.assertGreater(data["month_kwh"], 900.0)
        self.assertIsNotNone(data["estimated_bill_inr"])
        self.assertGreater(data["estimated_bill_inr"], 5000.0)

        # Tomorrow forecast is available from ML model
        self.assertIsNotNone(data["tomorrow_forecast_kwh"])
        self.assertGreater(data["tomorrow_forecast_kwh"], 0.0)

    def test_metrics_future_date_without_readings_returns_empty_states(self):
        """Future date with no meter readings returns honest empty state indicators."""
        resp = self.client.get("/api/metrics?current_date=2026-12-01")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["current_date"], "2026-12-01")
        self.assertFalse(data["today_has_data"])
        self.assertIsNone(data["today_kwh"])
        self.assertFalse(data["month_has_data"])
        self.assertIsNone(data["month_kwh"])
        self.assertIsNone(data["estimated_bill_inr"])
        self.assertIsNotNone(data["today_message"])
        self.assertIsNotNone(data["month_message"])

    def test_metrics_historical_reference_preserved(self):
        """Historical reference (Sep monthly benchmark) is provided for contextual UI comparison."""
        resp = self.client.get("/api/metrics?current_date=2026-10-31")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["historical_reference_kwh"], 420.0)
        self.assertIn("Historical baseline", data["historical_reference_note"])

    def test_metrics_historical_anchor_regression(self):
        """Requesting the Phase 3 historical anchor (2026-09-08) returns benchmark numbers."""
        resp = self.client.get("/api/metrics?current_date=2026-09-08")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["today_has_data"])
        self.assertEqual(data["today_kwh"], 35.4)
        self.assertTrue(data["month_has_data"])
        self.assertEqual(data["month_kwh"], 420.0)
        self.assertEqual(data["estimated_bill_inr"], 2778.0)


class TestReportSummariesAndReadings(unittest.TestCase):
    """Tests for monthly summaries and statement generation across months."""

    def setUp(self):
        self.client = TestClient(app)

    def test_september_report_has_actual_data(self):
        """September 2026 report returns actual recorded consumption and cost."""
        resp = self.client.get("/api/reports/summary?start_date=2026-09-01&end_date=2026-09-30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_consumption_kwh"], 0.0)
        self.assertGreater(data["estimated_bill_inr"], 0.0)
        self.assertGreater(data["readings_count"], 0)

    def test_october_report_has_simulated_demonstration_data(self):
        """October 2026 report returns full simulated consumption, bill estimate, and readings."""
        resp = self.client.get("/api/reports/summary?start_date=2026-10-01&end_date=2026-10-31")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total_consumption_kwh"], 900.0)
        self.assertGreater(data["estimated_bill_inr"], 5000.0)
        self.assertGreaterEqual(data["readings_count"], 744)

    def test_future_report_handles_no_data_gracefully(self):
        """Future month (December 2026) report returns zero consumption and fixed charge without crashing."""
        resp = self.client.get("/api/reports/summary?start_date=2026-12-01&end_date=2026-12-31")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_consumption_kwh"], 0.0)
        self.assertEqual(data["bill_breakdown"]["energy_charges_inr"], 0.0)
        self.assertEqual(data["estimated_bill_inr"], 10.0)  # Statutory fixed charge for 1 kW load
        self.assertEqual(data["readings_count"], 0)

    def test_statement_generation_date_format(self):
        """Statement includes valid generation date and month."""
        resp = self.client.get("/api/reports/statement?start_date=2026-09-01&end_date=2026-09-30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("statement_date", data)
        self.assertEqual(data["statement_date"], "2026-10-31")
        self.assertGreater(data["total_kwh"], 0.0)

    def test_readings_filters_use_current_date(self):
        """Readings endpoint with filter=today on current date returns today's readings, and on future date returns empty list."""
        with patch.dict(os.environ, {"ENERGYWATCH_CURRENT_DATE": "2026-10-31"}):
            resp = self.client.get("/api/readings?filter=today")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertGreater(len(data), 0)

        with patch.dict(os.environ, {"ENERGYWATCH_CURRENT_DATE": "2026-12-01"}):
            resp_empty = self.client.get("/api/readings?filter=today")
            self.assertEqual(resp_empty.status_code, 200)
            data_empty = resp_empty.json()
            self.assertEqual(len(data_empty), 0)


class TestFrontendContractAndModalIntegrity(unittest.TestCase):
    """Static and structural validation of index.html frontend contracts."""

    def setUp(self):
        with open("index.html", "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_csv_modal_properly_closed(self):
        """csvModalOverlay must be closed before statementModalOverlay begins."""
        csv_start = self.html.find('id="csvModalOverlay"')
        stmt_start = self.html.find('id="statementModalOverlay"')
        self.assertNotEqual(csv_start, -1)
        self.assertNotEqual(stmt_start, -1)
        self.assertLess(csv_start, stmt_start)

        # Slice between them to ensure all nested divs are closed
        between = self.html[csv_start:stmt_start]
        open_divs = len(re.findall(r'<div\b', between))
        close_divs = len(re.findall(r'</div>', between))
        self.assertEqual(open_divs, close_divs, "Unclosed div found inside or surrounding csvModalOverlay!")

    def test_escape_key_listener_closes_statement_modal(self):
        """Global keydown Escape handler must invoke closeStatementModal()."""
        self.assertIn("closeStatementModal()", self.html)
        pattern = r"e\.key\s*===\s*['\"]Escape['\"].*?closeStatementModal\(\)"
        self.assertTrue(re.search(pattern, self.html, re.DOTALL), "Escape handler does not invoke closeStatementModal()")

    def test_close_statement_modal_restores_scroll(self):
        """closeStatementModal function must reset document.body.style.overflow."""
        func_match = re.search(r"function\s+closeStatementModal\s*\(\)\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(func_match)
        body = func_match.group(1)
        self.assertIn("overflow", body)

    def test_view_print_statement_button_label(self):
        """Report statement button label must be 'View / Print Statement'."""
        self.assertIn("View / Print Statement", self.html)

    def test_simulation_badge_reference_clarity(self):
        """Header or welcome area must clearly disclose simulated telemetry and reference dates."""
        self.assertIn("Simulated Telemetry", self.html)
        self.assertIn("31 October 2026", self.html)
        self.assertIn("17 September 2026", self.html)


if __name__ == "__main__":
    unittest.main()
