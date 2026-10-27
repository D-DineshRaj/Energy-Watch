"""Comprehensive unit and API test suite for Phase 3 APERC electricity bill calculation."""
import unittest
from decimal import Decimal
from starlette.testclient import TestClient

from backend.main import app
from backend.services.billing import (
    calculate_aperc_bill,
    DEFAULT_APERC_TARIFF,
)


class TestBillingService(unittest.TestCase):
    """Test suite for the core bill calculation service."""

    def test_zero_consumption(self):
        """Zero consumption incurs fixed charge only; energy charge and duty are zero."""
        res = calculate_aperc_bill(consumption_kwh=0.0, sanctioned_load_kw=1.0)
        self.assertEqual(res["consumption_kwh"], 0.0)
        self.assertEqual(res["energy_charges_inr"], 0.0)
        self.assertEqual(res["fixed_charges_inr"], 10.0)
        self.assertEqual(res["electricity_duty_inr"], 0.0)
        self.assertEqual(res["estimated_total_inr"], 10.0)
        self.assertEqual(res["estimated_total_rounded_inr"], 10)
        self.assertEqual(len(res["slabs_breakdown"]), 6)
        # All slabs should have 0 units billed
        for slab in res["slabs_breakdown"]:
            self.assertEqual(slab["units_billed"], 0.0)
            self.assertEqual(slab["charge_inr"], 0.0)

    def test_normal_consumption_50_kwh(self):
        """50 kWh spans across slab 1 (30 units) and slab 2 (20 units)."""
        res = calculate_aperc_bill(consumption_kwh=50.0, sanctioned_load_kw=1.0)
        # 30 * 1.90 = 57.00
        # 20 * 3.00 = 60.00
        # Energy = 117.00, Fixed = 10.00, Duty = 50 * 0.06 = 3.00, Total = 130.00
        self.assertEqual(res["energy_charges_inr"], 117.0)
        self.assertEqual(res["fixed_charges_inr"], 10.0)
        self.assertEqual(res["electricity_duty_inr"], 3.0)
        self.assertEqual(res["estimated_total_inr"], 130.0)
        self.assertEqual(res["slabs_breakdown"][0]["units_billed"], 30.0)
        self.assertEqual(res["slabs_breakdown"][1]["units_billed"], 20.0)
        self.assertEqual(res["slabs_breakdown"][2]["units_billed"], 0.0)

    def test_normal_consumption_420_kwh(self):
        """420 kWh matches the dashboard's current monthly consumption."""
        res = calculate_aperc_bill(consumption_kwh=420.0, sanctioned_load_kw=1.0)
        # Slabs:
        # 1: 30 * 1.90 = 57.00
        # 2: 45 * 3.00 = 135.00
        # 3: 50 * 4.50 = 225.00
        # 4: 100 * 6.00 = 600.00
        # 5: 175 * 8.75 = 1531.25
        # 6: 20 * 9.75 = 195.00
        # Sum energy = 2743.25
        # Fixed = 10.00, Duty = 420 * 0.06 = 25.20
        # Grand total = 2778.45 (rounded: 2778)
        self.assertEqual(res["energy_charges_inr"], 2743.25)
        self.assertEqual(res["fixed_charges_inr"], 10.0)
        self.assertEqual(res["electricity_duty_inr"], 25.20)
        self.assertEqual(res["estimated_total_inr"], 2778.45)
        self.assertEqual(res["estimated_total_rounded_inr"], 2778)

    def test_slab_boundaries(self):
        """Test exact threshold boundaries for each of the 5 slab thresholds."""
        boundaries = [
            (30.0, 57.0),          # 30 * 1.90
            (75.0, 192.0),         # 57 + 45*3.00
            (125.0, 417.0),        # 192 + 50*4.50
            (225.0, 1017.0),       # 417 + 100*6.00
            (400.0, 2548.25),      # 1017 + 175*8.75
        ]
        for units, expected_energy in boundaries:
            with self.subTest(boundary=units):
                res = calculate_aperc_bill(consumption_kwh=units)
                self.assertEqual(res["energy_charges_inr"], expected_energy)

    def test_slab_boundary_deltas_below_and_above(self):
        """Test values immediately below (boundary - 0.1) and above (boundary + 0.1)."""
        # Boundary 1: 30 kWh (rates: 1.90 then 3.00)
        b1_below = calculate_aperc_bill(29.9)["energy_charges_inr"]
        b1_above = calculate_aperc_bill(30.1)["energy_charges_inr"]
        self.assertEqual(b1_below, round(29.9 * 1.90, 2))  # 56.81
        self.assertEqual(b1_above, round(30 * 1.90 + 0.1 * 3.00, 2))  # 57.30

        # Boundary 2: 75 kWh (rates: 3.00 then 4.50)
        b2_below = calculate_aperc_bill(74.9)["energy_charges_inr"]
        b2_above = calculate_aperc_bill(75.1)["energy_charges_inr"]
        self.assertEqual(b2_below, round(57.0 + 44.9 * 3.00, 2))  # 191.70
        self.assertEqual(b2_above, round(192.0 + 0.1 * 4.50, 2))  # 192.45

        # Boundary 3: 125 kWh (rates: 4.50 then 6.00)
        b3_below = calculate_aperc_bill(124.9)["energy_charges_inr"]
        b3_above = calculate_aperc_bill(125.1)["energy_charges_inr"]
        self.assertEqual(b3_below, round(192.0 + 49.9 * 4.50, 2))  # 416.55
        self.assertEqual(b3_above, round(417.0 + 0.1 * 6.00, 2))  # 417.60

        # Boundary 4: 225 kWh (rates: 6.00 then 8.75)
        b4_below = calculate_aperc_bill(224.9)["energy_charges_inr"]
        b4_above = calculate_aperc_bill(225.1)["energy_charges_inr"]
        self.assertEqual(b4_below, round(417.0 + 99.9 * 6.00, 2))  # 1016.40
        self.assertEqual(b4_above, round(1017.0 + 0.1 * 8.75, 2))  # 1017.88

        # Boundary 5: 400 kWh (rates: 8.75 then 9.75)
        b5_below = calculate_aperc_bill(399.9)["energy_charges_inr"]
        b5_above = calculate_aperc_bill(400.1)["energy_charges_inr"]
        self.assertEqual(b5_below, 2547.38)
        self.assertEqual(b5_above, 2549.23)

    def test_invalid_input_validation(self):
        """Negative consumption or invalid load values must raise ValueError."""
        with self.assertRaises(ValueError):
            calculate_aperc_bill(-10.0)

        with self.assertRaises(ValueError):
            calculate_aperc_bill(100.0, sanctioned_load_kw=0.0)

        with self.assertRaises(ValueError):
            calculate_aperc_bill(100.0, sanctioned_load_kw=-2.0)

        with self.assertRaises(ValueError):
            calculate_aperc_bill("invalid")  # type: ignore

    def test_monetary_rounding_precision(self):
        """Fractional consumption arithmetic must adhere to half-up monetary precision."""
        res = calculate_aperc_bill(33.333, sanctioned_load_kw=1.0)
        # All monetary figures should have at most 2 decimal places
        for k in ["energy_charges_inr", "fixed_charges_inr", "electricity_duty_inr", "estimated_total_inr"]:
            val = res[k]
            self.assertEqual(val, round(val, 2))

    def test_charge_breakdown_arithmetic_integrity(self):
        """Sum of slab units must equal consumption, and sum of charges must equal total."""
        res = calculate_aperc_bill(275.5, sanctioned_load_kw=2.5)
        sum_units = sum(s["units_billed"] for s in res["slabs_breakdown"])
        self.assertAlmostEqual(sum_units, 275.5, places=2)

        sum_energy = sum(s["charge_inr"] for s in res["slabs_breakdown"])
        self.assertAlmostEqual(sum_energy, res["energy_charges_inr"], places=2)

        expected_total = round(
            res["energy_charges_inr"]
            + res["fixed_charges_inr"]
            + res["electricity_duty_inr"]
            + res["fpppa_charges_inr"]
            + res["customer_charges_inr"],
            2,
        )
        self.assertEqual(res["estimated_total_inr"], expected_total)

    def test_high_consumption_1000_kwh(self):
        """1000 kWh deeply exercises the top unbounded slab (> 400 kWh at 9.75/unit)."""
        res = calculate_aperc_bill(1000.0, sanctioned_load_kw=5.0)
        # Slabs 1-5 capped total = 2548.25
        # Slab 6: 600 * 9.75 = 5850.00
        # Energy = 8398.25
        # Fixed: 5 kW * 10 = 50.00
        # Duty: 1000 * 0.06 = 60.00
        # Total = 8508.25
        self.assertEqual(res["energy_charges_inr"], 8398.25)
        self.assertEqual(res["fixed_charges_inr"], 50.00)
        self.assertEqual(res["electricity_duty_inr"], 60.00)
        self.assertEqual(res["estimated_total_inr"], 8508.25)
        self.assertEqual(res["slabs_breakdown"][5]["units_billed"], 600.0)

    def test_custom_tariff_override(self):
        """Verify custom tariff schedules can be passed seamlessly."""
        custom = dict(DEFAULT_APERC_TARIFF)
        custom["fixed_charge_per_kw_per_month"] = "25.00"
        res = calculate_aperc_bill(100.0, sanctioned_load_kw=2.0, custom_tariff=custom)
        self.assertEqual(res["fixed_charges_inr"], 50.0)  # 2 kW * 25


class TestBillingAPI(unittest.TestCase):
    """Integration test suite for the FastAPI endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_bill_estimate_default(self):
        """GET /api/bill-estimate defaults to 420 kWh and returns 200 with complete breakdown."""
        res = self.client.get("/api/bill-estimate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["consumption_kwh"], 420.0)
        self.assertEqual(data["consumer_category"], "LT Category-I(A): Domestic")
        self.assertEqual(data["state"], "Andhra Pradesh")
        self.assertIn("APERC", data["regulatory_authority"])
        self.assertEqual(data["billing_method"], "telescopic")
        self.assertEqual(data["effective_date"], "2026-04-01")
        self.assertIn("2026-27", data["tariff_order_ref"])
        self.assertEqual(data["estimated_total_rounded_inr"], 2778)
        self.assertEqual(data["is_official_bill"], False)
        self.assertIn("https://aperc.gov.in/", data["official_source_url"])
        self.assertEqual(len(data["slabs_breakdown"]), 6)
        self.assertTrue(len(data["calculation_assumptions"]) >= 3)
        self.assertTrue(len(data["limitations"]) > 10)

    def test_get_bill_estimate_with_params(self):
        """GET /api/bill-estimate accepts custom consumption_kwh and sanctioned_load_kw."""
        res = self.client.get("/api/bill-estimate?consumption_kwh=100&sanctioned_load_kw=2.0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["consumption_kwh"], 100.0)
        self.assertEqual(data["sanctioned_load_kw"], 2.0)
        self.assertEqual(data["fixed_charges_inr"], 20.0)  # 2 kW * 10
        self.assertEqual(data["energy_charges_inr"], 304.5)  # 30*1.90 + 45*3.00 + 25*4.50
        self.assertEqual(data["electricity_duty_inr"], 6.0)  # 100 * 0.06

    def test_get_bill_estimate_zero_consumption(self):
        """GET /api/bill-estimate with 0 units succeeds and returns base fixed charges."""
        res = self.client.get("/api/bill-estimate?consumption_kwh=0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["consumption_kwh"], 0.0)
        self.assertEqual(data["estimated_total_inr"], 10.0)

    def test_get_bill_estimate_negative_consumption_422(self):
        """GET /api/bill-estimate with negative consumption returns 422 validation error."""
        res = self.client.get("/api/bill-estimate?consumption_kwh=-25")
        self.assertEqual(res.status_code, 422)

    def test_get_bill_estimate_invalid_load_422(self):
        """GET /api/bill-estimate with negative or zero load returns 422 validation error."""
        res = self.client.get("/api/bill-estimate?sanctioned_load_kw=0")
        self.assertEqual(res.status_code, 422)

    def test_get_bill_estimate_non_numeric_422(self):
        """GET /api/bill-estimate with non-numeric consumption returns 422 validation error."""
        res = self.client.get("/api/bill-estimate?consumption_kwh=abc")
        self.assertEqual(res.status_code, 422)

    def test_get_bill_estimate_excessive_load_422(self):
        """GET /api/bill-estimate with load exceeding 50 kW returns 422 validation error."""
        res = self.client.get("/api/bill-estimate?sanctioned_load_kw=100")
        self.assertEqual(res.status_code, 422)

    def test_metrics_endpoint_includes_estimated_bill(self):
        """GET /api/metrics returns populated estimated_bill_inr matching 420 kWh bill."""
        res = self.client.get("/api/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["today_kwh"], 35.4)
        self.assertEqual(data["month_kwh"], 420.0)
        self.assertEqual(data["estimated_bill_inr"], 2778.0)
        self.assertIn("APERC", data["tariff_note"])


if __name__ == "__main__":
    unittest.main()
