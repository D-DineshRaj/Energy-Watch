"""Service for electricity consumption reporting, aggregations, and CSV export."""
import csv
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy.orm import Session

from backend.models import MeterReading
from backend.services.billing import calculate_aperc_bill, DEFAULT_APERC_TARIFF


def parse_date_param(val: Union[str, date, datetime], is_end: bool = False) -> datetime:
    """Parse flexible date strings or objects into a timezone-naive datetime boundary."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, time.max if is_end else time.min)

    val_str = str(val).strip()
    # Try ISO formats
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            parsed = datetime.strptime(val_str.replace("Z", ""), fmt)
            if fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
                return datetime.combine(parsed.date(), time.max if is_end else time.min)
            return parsed
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date parameter '{val}'. Use ISO-8601 format (YYYY-MM-DD).")


def generate_consumption_summary(
    db: Session,
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    meter_id: Optional[str] = "EW-2847-HH",
    sanctioned_load_kw: float = 1.0,
) -> Dict[str, Any]:
    """Generate comprehensive electricity consumption summary and APERC bill estimate from stored readings.

    Args:
        db: SQLAlchemy database session.
        start_date: Beginning of reporting window (inclusive).
        end_date: End of reporting window (inclusive).
        meter_id: Specific smart meter ID (default: EW-2847-HH).
        sanctioned_load_kw: Contracted connected load in kW for fixed charge computation.

    Returns:
        Dict with total_kwh, daily_avg_kwh, peak metrics, bill estimate, and daily/monthly breakdowns.

    Raises:
        ValueError: If date parameters are invalid or start_date > end_date.
    """
    if sanctioned_load_kw <= 0:
        raise ValueError(f"Sanctioned load must be strictly positive (got {sanctioned_load_kw} kW).")

    # 1. Resolve and validate date range
    meter = meter_id.strip() if meter_id else "EW-2847-HH"
    query = db.query(MeterReading)
    if meter:
        query = query.filter(MeterReading.meter_id == meter)

    # Determine default boundaries from database if not supplied
    if start_date is None or end_date is None:
        first_r = query.order_by(MeterReading.timestamp.asc()).first()
        last_r = query.order_by(MeterReading.timestamp.desc()).first()
        earliest_dt = first_r.timestamp if first_r else datetime(2026, 9, 1, 0, 0, 0)
        latest_dt = last_r.timestamp if last_r else datetime(2026, 9, 30, 23, 59, 59)
    else:
        earliest_dt = None
        latest_dt = None

    parsed_start = parse_date_param(start_date) if start_date is not None else earliest_dt
    parsed_end = parse_date_param(end_date, is_end=True) if end_date is not None else latest_dt

    if parsed_start > parsed_end:
        raise ValueError(
            f"Start date '{parsed_start.strftime('%Y-%m-%d')}' cannot be after "
            f"end date '{parsed_end.strftime('%Y-%m-%d')}'."
        )

    # 2. Fetch all matching readings ordered chronologically
    readings = (
        query.filter(
            MeterReading.timestamp >= parsed_start,
            MeterReading.timestamp <= parsed_end,
        )
        .order_by(MeterReading.timestamp.asc())
        .all()
    )

    start_str = parsed_start.strftime("%Y-%m-%d")
    end_str = parsed_end.strftime("%Y-%m-%d")

    # Handle empty dataset
    if not readings:
        empty_bill = calculate_aperc_bill(0.0, sanctioned_load_kw=sanctioned_load_kw)
        return {
            "status": "empty",
            "meter_id": meter,
            "start_date": start_str,
            "end_date": end_str,
            "total_consumption_kwh": 0.0,
            "daily_avg_kwh": 0.0,
            "days_count": 0,
            "readings_count": 0,
            "peak_day": None,
            "peak_day_kwh": None,
            "peak_hour": None,
            "peak_hour_kwh": None,
            "sanctioned_load_kw": sanctioned_load_kw,
            "estimated_bill_inr": float(empty_bill["estimated_total_inr"]),
            "estimated_bill_rounded_inr": int(empty_bill["estimated_total_rounded_inr"]),
            "bill_breakdown": empty_bill,
            "daily_breakdown": [],
            "monthly_breakdown": [],
            "data_source": "simulated",
            "tariff_reference": DEFAULT_APERC_TARIFF["order_reference"],
            "message": f"No readings found for meter '{meter}' between {start_str} and {end_str}.",
        }

    # 3. Group readings by calendar date and evaluate daily consumption
    # Precedence: If a calendar day has hourly readings, sum the hourly readings.
    # Otherwise, use the daily summary reading.
    readings_by_date: Dict[date, List[MeterReading]] = {}
    for r in readings:
        readings_by_date.setdefault(r.timestamp.date(), []).append(r)

    daily_breakdown: List[Dict[str, Any]] = []
    overall_peak_hour_kwh = 0.0
    overall_peak_hour_str = None

    for cal_date in sorted(readings_by_date.keys()):
        day_readings = readings_by_date[cal_date]
        hourly_readings = [r for r in day_readings if r.reading_type == "hourly"]

        if hourly_readings:
            day_usage = sum(float(r.usage_kwh) for r in hourly_readings)
            day_count = len(hourly_readings)
            rtype = "hourly"
            # Find peak hour of the day
            peak_reading = max(hourly_readings, key=lambda r: float(r.usage_kwh))
            peak_kwh = round(float(peak_reading.usage_kwh), 2)
            peak_hour = peak_reading.timestamp.strftime("%I:%M %p").lstrip("0")
            if peak_kwh > overall_peak_hour_kwh:
                overall_peak_hour_kwh = peak_kwh
                dt_peak = peak_reading.timestamp
                overall_peak_hour_str = f"{dt_peak.strftime('%Y-%m-%d')} {peak_hour}"
        else:
            # Fall back to daily reading
            daily_readings = [r for r in day_readings if r.reading_type == "daily"]
            day_usage = sum(float(r.usage_kwh) for r in daily_readings)
            day_count = len(day_readings)
            rtype = "daily"
            peak_reading = daily_readings[0] if daily_readings else day_readings[0]
            peak_kwh = None
            peak_hour = None

        daily_breakdown.append({
            "date": cal_date.strftime("%Y-%m-%d"),
            "consumption_kwh": round(day_usage, 2),
            "reading_count": day_count,
            "peak_hour": peak_hour,
            "peak_kwh": peak_kwh,
            "reading_type": rtype,
        })

    # 4. Compute aggregate metrics
    total_kwh = round(sum(d["consumption_kwh"] for d in daily_breakdown), 2)
    days_count = len(daily_breakdown)
    daily_avg_kwh = round(total_kwh / days_count, 2) if days_count > 0 else 0.0

    peak_day_entry = max(daily_breakdown, key=lambda d: d["consumption_kwh"]) if daily_breakdown else None
    peak_day = peak_day_entry["date"] if peak_day_entry else None
    peak_day_kwh = peak_day_entry["consumption_kwh"] if peak_day_entry else None

    # 5. Group by month for monthly breakdown
    monthly_data: Dict[str, List[float]] = {}
    for d in daily_breakdown:
        m_key = d["date"][:7]  # YYYY-MM
        monthly_data.setdefault(m_key, []).append(d["consumption_kwh"])

    monthly_breakdown: List[Dict[str, Any]] = []
    for m_key in sorted(monthly_data.keys()):
        usages = monthly_data[m_key]
        m_total = round(sum(usages), 2)
        m_days = len(usages)
        m_avg = round(m_total / m_days, 2) if m_days > 0 else 0.0
        m_bill = calculate_aperc_bill(m_total, sanctioned_load_kw=sanctioned_load_kw)
        monthly_breakdown.append({
            "month": m_key,
            "consumption_kwh": m_total,
            "daily_avg_kwh": m_avg,
            "days_count": m_days,
            "estimated_bill_inr": float(m_bill["estimated_total_inr"]),
        })

    # 6. Calculate itemized APERC bill using official billing service
    bill_calc = calculate_aperc_bill(
        consumption_kwh=total_kwh,
        sanctioned_load_kw=sanctioned_load_kw,
    )

    return {
        "status": "success",
        "meter_id": meter,
        "start_date": start_str,
        "end_date": end_str,
        "total_consumption_kwh": total_kwh,
        "daily_avg_kwh": daily_avg_kwh,
        "days_count": days_count,
        "readings_count": len(readings),
        "peak_day": peak_day,
        "peak_day_kwh": peak_day_kwh,
        "peak_hour": overall_peak_hour_str,
        "peak_hour_kwh": round(overall_peak_hour_kwh, 2) if overall_peak_hour_kwh > 0 else None,
        "sanctioned_load_kw": sanctioned_load_kw,
        "estimated_bill_inr": float(bill_calc["estimated_total_inr"]),
        "estimated_bill_rounded_inr": int(bill_calc["estimated_total_rounded_inr"]),
        "bill_breakdown": bill_calc,
        "daily_breakdown": daily_breakdown,
        "monthly_breakdown": monthly_breakdown,
        "data_source": "simulated",
        "tariff_reference": DEFAULT_APERC_TARIFF["order_reference"],
        "message": (
            f"Successfully generated consumption report for meter '{meter}' "
            f"({start_str} to {end_str}). Total: {total_kwh} kWh across {days_count} days."
        ),
    }


def generate_readings_csv(
    db: Session,
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    meter_id: Optional[str] = "EW-2847-HH",
) -> Tuple[str, str, int]:
    """Generate an RFC-4180 compliant CSV export of meter readings.

    Args:
        db: Database session.
        start_date: Start boundary.
        end_date: End boundary.
        meter_id: Meter identifier.

    Returns:
        Tuple of (csv_content_str, suggested_filename, row_count).
    """
    meter = meter_id.strip() if meter_id else "EW-2847-HH"
    query = db.query(MeterReading)
    if meter:
        query = query.filter(MeterReading.meter_id == meter)

    if start_date is None or end_date is None:
        first_r = query.order_by(MeterReading.timestamp.asc()).first()
        last_r = query.order_by(MeterReading.timestamp.desc()).first()
        earliest_dt = first_r.timestamp if first_r else datetime(2026, 9, 1, 0, 0, 0)
        latest_dt = last_r.timestamp if last_r else datetime(2026, 9, 30, 23, 59, 59)
    else:
        earliest_dt = None
        latest_dt = None

    parsed_start = parse_date_param(start_date) if start_date is not None else earliest_dt
    parsed_end = parse_date_param(end_date, is_end=True) if end_date is not None else latest_dt

    if parsed_start > parsed_end:
        raise ValueError(
            f"Start date '{parsed_start.strftime('%Y-%m-%d')}' cannot be after "
            f"end date '{parsed_end.strftime('%Y-%m-%d')}'."
        )

    readings = (
        query.filter(
            MeterReading.timestamp >= parsed_start,
            MeterReading.timestamp <= parsed_end,
        )
        .order_by(MeterReading.timestamp.asc())
        .all()
    )

    start_str = parsed_start.strftime("%Y%m%d")
    end_str = parsed_end.strftime("%Y%m%d")
    filename = f"energywatch_readings_{meter}_{start_str}_{end_str}.csv"

    output = StringIO()
    writer = csv.writer(output, lineterminator="\r\n")

    # Header columns
    writer.writerow([
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

    for r in readings:
        writer.writerow([
            r.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            f"{float(r.usage_kwh):.2f}",
            r.meter_id,
            f"{float(r.voltage_v):.1f}" if r.voltage_v is not None else "",
            f"{float(r.current_a):.1f}" if r.current_a is not None else "",
            f"{float(r.power_factor):.2f}" if r.power_factor is not None else "",
            r.status or "Normal",
            r.source or "simulated",
            r.reading_type or "hourly",
        ])

    return output.getvalue(), filename, len(readings)
