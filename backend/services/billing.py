"""Electricity bill calculation service implementing official APERC tariff schedules."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import json

# Official APERC LT Category-I(A): Domestic Telescopic Tariff Schedule
# Source: Andhra Pradesh Electricity Regulatory Commission (APERC) Retail Supply Tariff Order for FY 2026-27
# Order Date: 25-March-2026 | Effective: 01-April-2026 to 31-March-2027
# Official Portal: https://aperc.gov.in/
DEFAULT_APERC_TARIFF = {
    "state": "Andhra Pradesh",
    "regulatory_body": "Andhra Pradesh Electricity Regulatory Commission (APERC)",
    "order_reference": "APERC Retail Supply Tariff Order for FY 2026-27 (Order dated 25-03-2026)",
    "effective_from": "2026-04-01",
    "category": "LT Category-I(A): Domestic",
    "supply_type": "Low Tension (LT) Residential Single-Phase / Three-Phase",
    "official_url": "https://aperc.gov.in/",
    "billing_method": "telescopic",
    "slabs": [
        {"min": 0, "max": 30, "rate": "1.90", "label": "0 – 30 kWh"},
        {"min": 30, "max": 75, "rate": "3.00", "label": "31 – 75 kWh"},
        {"min": 75, "max": 125, "rate": "4.50", "label": "76 – 125 kWh"},
        {"min": 125, "max": 225, "rate": "6.00", "label": "126 – 225 kWh"},
        {"min": 225, "max": 400, "rate": "8.75", "label": "226 – 400 kWh"},
        {"min": 400, "max": None, "rate": "9.75", "label": "Above 400 kWh"},
    ],
    "fixed_charge_per_kw_per_month": "10.00",
    "electricity_duty_per_kwh": "0.06",  # 6 paise per unit per AP Electricity Duty Act
    "fpppa_per_kwh": "0.00",  # Fuel Surcharge Adjustment variable / state-subsidized
    "customer_charges_monthly": "0.00",
}


def _round_currency(val: Decimal) -> Decimal:
    """Round to 2 decimal places using standard half-up monetary convention."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_aperc_bill(
    consumption_kwh: float,
    sanctioned_load_kw: float = 1.0,
    custom_tariff: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate an itemized electricity bill estimate for a monthly consumption.

    Args:
        consumption_kwh: Monthly total electricity consumption in kilowatt-hours (units).
        sanctioned_load_kw: Contracted/sanctioned connected load in kW (default: 1.0 kW).
        custom_tariff: Optional dictionary overriding the default APERC tariff schedule.

    Returns:
        Dict containing full slab breakdown, fixed charges, duty, total, and metadata.

    Raises:
        ValueError: If consumption is negative, non-numeric, or sanctioned load <= 0.
    """
    if consumption_kwh is None or not isinstance(consumption_kwh, (int, float, Decimal)):
        raise ValueError("Consumption must be a valid numeric value.")
    if consumption_kwh < 0:
        raise ValueError("Monthly electricity consumption cannot be negative.")
    if sanctioned_load_kw is None or sanctioned_load_kw <= 0:
        raise ValueError("Sanctioned load must be greater than zero.")

    tariff = custom_tariff or DEFAULT_APERC_TARIFF
    cons = Decimal(str(consumption_kwh))
    load = Decimal(str(sanctioned_load_kw))

    slabs = tariff.get("slabs", DEFAULT_APERC_TARIFF["slabs"])
    fixed_rate = Decimal(str(tariff.get("fixed_charge_per_kw_per_month", "10.00")))
    duty_rate = Decimal(str(tariff.get("electricity_duty_per_kwh", "0.06")))
    fpppa_rate = Decimal(str(tariff.get("fpppa_per_kwh", "0.00")))
    customer_charge = Decimal(str(tariff.get("customer_charges_monthly", "0.00")))

    slabs_breakdown: List[Dict[str, Any]] = []
    total_energy_charges = Decimal("0.00")
    remaining_units = cons

    # Telescopic slab calculation
    for idx, slab in enumerate(slabs, start=1):
        s_min = Decimal(str(slab["min"]))
        s_max = Decimal(str(slab["max"])) if slab["max"] is not None else None
        rate = Decimal(str(slab["rate"]))
        label = slab.get("label", f"Slab {idx}")

        if cons <= s_min:
            # Consumption did not reach this slab
            units_in_slab = Decimal("0.00")
        elif s_max is None:
            # Highest unbounded slab
            units_in_slab = cons - s_min
        else:
            # Units falling strictly in [s_min, s_max]
            slab_capacity = s_max - s_min
            units_in_slab = min(cons - s_min, slab_capacity)

        charge = _round_currency(units_in_slab * rate)
        total_energy_charges += charge

        slabs_breakdown.append({
            "slab_index": idx,
            "slab_label": label,
            "min_kwh": float(s_min),
            "max_kwh": float(s_max) if s_max is not None else None,
            "rate_per_kwh": float(rate),
            "units_billed": float(units_in_slab),
            "charge_inr": float(charge),
        })

    # Fixed charge (per kW of sanctioned load per month)
    fixed_charge = _round_currency(load * fixed_rate)

    # Statutory Electricity Duty (6 paise/kWh)
    electricity_duty = _round_currency(cons * duty_rate)

    # Fuel Surcharge Adjustment (FSA / FPPPA)
    fpppa_charge = _round_currency(cons * fpppa_rate)

    # Customer charges
    cust_charge = _round_currency(customer_charge)

    # Grand total
    estimated_total = _round_currency(
        total_energy_charges + fixed_charge + electricity_duty + fpppa_charge + cust_charge
    )

    assumptions = [
        "Domestic category LT-I(A) telescopic energy tariff approved under APERC Retail Supply Tariff Order for FY 2026-27 (retaining zero tariff hike statewide).",
        f"Contracted load assumed at {float(load):.1f} kW single-phase domestic connection (₹{float(fixed_rate):.2f}/kW/month).",
        f"Electricity Duty levied at statutory domestic rate of ₹{float(duty_rate):.2f} (6 paise) per kWh pursuant to Section 3(1) of the Andhra Pradesh Electricity Duty Act, 1939.",
        "Fuel Surcharge Adjustment (FPPPA/FSA) is variable by billing cycle and is excluded (assumed ₹0.00/kWh baseline) in this estimate; actual DISCOM bills may reflect applicable fuel adjustments.",
        "Meter rent and localized municipal taxes are excluded unless specifically billed by the DISCOM.",
    ]

    limitations = (
        "This is an estimated calculation for informational monitoring purposes only. "
        "Official electricity bills from APSPDCL/APEPDCL/APCPDCL may include seasonal fuel cost "
        "adjustments, solar net-metering credits, arrears, delayed payment surcharges, or "
        "localized municipal cess."
    )

    return {
        "consumption_kwh": float(cons),
        "sanctioned_load_kw": float(load),
        "consumer_category": tariff.get("category", "LT Category-I(A): Domestic"),
        "state": tariff.get("state", "Andhra Pradesh"),
        "regulatory_authority": tariff.get("regulatory_body", "APERC"),
        "tariff_order_ref": tariff.get("order_reference", "APERC Retail Supply Tariff Order for FY 2026-27"),
        "effective_date": tariff.get("effective_from", "2026-04-01"),
        "official_source_url": tariff.get("official_url", "https://aperc.gov.in/"),
        "billing_method": "telescopic",
        "slabs_breakdown": slabs_breakdown,
        "energy_charges_inr": float(total_energy_charges),
        "fixed_charges_inr": float(fixed_charge),
        "electricity_duty_inr": float(electricity_duty),
        "fpppa_charges_inr": float(fpppa_charge),
        "customer_charges_inr": float(cust_charge),
        "estimated_total_inr": float(estimated_total),
        "estimated_total_rounded_inr": int(estimated_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "is_official_bill": False,
        "calculation_assumptions": assumptions,
        "limitations": limitations,
    }
