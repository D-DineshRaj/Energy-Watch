"""Service for validating, parsing, and storing meter readings from CSV files."""
import csv
from datetime import datetime
import io
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from backend.models import MeterReading

REQUIRED_COLUMNS = {"timestamp", "consumption_kwh", "meter_id"}


def parse_timestamp_flexible(raw: str) -> Optional[datetime]:
    """Parse various timestamp and date formats into a naive datetime."""
    raw = raw.strip()
    if not raw:
        return None

    # Try ISO-8601
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    return None


def parse_and_validate_csv(
    csv_content: str,
    db: Session,
    filename: str = "meter_readings.csv",
    strict: bool = False,
) -> Dict[str, Any]:
    """Validate and import meter readings from CSV text.

    Args:
        csv_content: Text or decoded string of the CSV file.
        db: SQLAlchemy database session.
        filename: Uploaded filename for reporting.
        strict: If True, any invalid row aborts the whole transaction.

    Returns:
        Dict with status, imported_count, skipped_duplicates_count, rejected_invalid_count, details.

    Raises:
        ValueError: For missing columns, empty file, or non-viable files.
    """
    if not csv_content or not csv_content.strip():
        raise ValueError("CSV file is empty or contains no records.")

    # Handle utf-8-sig BOM if present
    clean_content = csv_content.lstrip("\ufeff").strip()
    if not clean_content:
        raise ValueError("CSV file is empty or contains no records.")

    reader = csv.reader(io.StringIO(clean_content))

    # Read header row
    try:
        header_row = next(reader)
    except StopIteration:
        raise ValueError("CSV file is empty or contains no records.")

    # Normalize header names (lowercase, stripped)
    normalized_headers = [h.strip().lower() for h in header_row if h is not None]
    header_set = set(normalized_headers)

    missing = REQUIRED_COLUMNS - header_set
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(sorted(missing))}")

    col_ts = normalized_headers.index("timestamp")
    col_kwh = normalized_headers.index("consumption_kwh")
    col_meter = normalized_headers.index("meter_id")

    total_rows = 0
    imported_count = 0
    skipped_duplicates_count = 0
    rejected_invalid_count = 0
    details: List[str] = []

    seen_in_batch: Set[Tuple[str, datetime]] = set()
    to_insert: List[MeterReading] = []

    for row_idx, row in enumerate(reader, start=2):
        if not row or all(not str(c).strip() for c in row):
            continue

        total_rows += 1

        if len(row) <= max(col_ts, col_kwh, col_meter):
            msg = f"Row {row_idx}: incomplete columns (expected at least 3)."
            details.append(msg)
            rejected_invalid_count += 1
            if strict:
                raise ValueError(msg)
            continue

        raw_ts = str(row[col_ts]).strip()
        raw_kwh = str(row[col_kwh]).strip()
        raw_meter = str(row[col_meter]).strip()

        # 1. Validate meter_id
        if not raw_meter:
            msg = f"Row {row_idx}: meter_id cannot be empty."
            details.append(msg)
            rejected_invalid_count += 1
            if strict:
                raise ValueError(msg)
            continue

        # 2. Validate timestamp
        parsed_dt = parse_timestamp_flexible(raw_ts)
        if parsed_dt is None:
            msg = f"Row {row_idx}: invalid timestamp format '{raw_ts}'."
            details.append(msg)
            rejected_invalid_count += 1
            if strict:
                raise ValueError(msg)
            continue

        # 3. Validate consumption_kwh
        try:
            usage_val = float(raw_kwh)
            if math.isnan(usage_val) or math.isinf(usage_val):
                raise ValueError("Non-finite value")
            if usage_val < 0:
                msg = f"Row {row_idx}: consumption cannot be negative ({usage_val} kWh)."
                details.append(msg)
                rejected_invalid_count += 1
                if strict:
                    raise ValueError(msg)
                continue
        except (ValueError, TypeError):
            msg = f"Row {row_idx}: non-numeric consumption value '{raw_kwh}'."
            details.append(msg)
            rejected_invalid_count += 1
            if strict:
                raise ValueError(msg)
            continue

        # 4. Check duplicate within uploaded batch
        batch_key = (raw_meter, parsed_dt)
        if batch_key in seen_in_batch:
            details.append(
                f"Row {row_idx}: duplicate reading for meter '{raw_meter}' at {parsed_dt} in file (skipped)."
            )
            skipped_duplicates_count += 1
            continue
        seen_in_batch.add(batch_key)

        # 5. Check duplicate against existing database records
        existing_reading = (
            db.query(MeterReading.id)
            .filter(
                MeterReading.meter_id == raw_meter,
                MeterReading.timestamp == parsed_dt,
            )
            .first()
        )
        if existing_reading:
            details.append(
                f"Row {row_idx}: reading for meter '{raw_meter}' at {parsed_dt} already exists in database (skipped)."
            )
            skipped_duplicates_count += 1
            continue

        # Determine reading_type and status
        is_daily = (parsed_dt.hour == 23 and parsed_dt.minute == 59 and parsed_dt.second == 59)
        reading_type = "daily" if is_daily else "hourly"
        status = "High" if usage_val > 8.0 else "Normal"
        curr_est = round(usage_val * 1000.0 / 230.0 / 0.96, 1) if usage_val > 0 else 0.0

        to_insert.append(
            MeterReading(
                meter_id=raw_meter,
                timestamp=parsed_dt,
                usage_kwh=round(usage_val, 2),
                voltage_v=230.0,
                current_a=curr_est,
                power_factor=0.96,
                status=status,
                source="simulated",
                reading_type=reading_type,
            )
        )

    if total_rows == 0:
        raise ValueError("CSV file is empty or contains no records.")

    # If all rows had invalid values, raise ValueError so it maps to HTTP 400
    if total_rows > 0 and len(to_insert) == 0 and rejected_invalid_count > 0 and skipped_duplicates_count == 0:
        err_summary = "; ".join(details[:3])
        raise ValueError(f"No valid readings found in CSV file. Errors: {err_summary}")

    anomalies_detected = 0
    alerts_created = 0

    # Commit valid non-duplicate readings
    if to_insert:
        db.add_all(to_insert)
        db.commit()
        imported_count = len(to_insert)

        # Automatically evaluate newly imported readings for consumption anomalies
        from backend.services.anomaly_detection import scan_and_generate_alerts
        target_meter = to_insert[0].meter_id if to_insert else None
        anomaly_summary = scan_and_generate_alerts(
            db=db,
            candidate_readings=to_insert,
            meter_id=target_meter,
        )
        anomalies_detected = anomaly_summary.get("anomalies_detected", 0)
        alerts_created = anomaly_summary.get("alerts_created", 0)
        if anomalies_detected > 0:
            details.append(
                f"Automated anomaly scan: {anomalies_detected} consumption spike(s) detected, "
                f"{alerts_created} new alert(s) generated."
            )

    if imported_count > 0:
        status_str = "success" if (rejected_invalid_count == 0 and skipped_duplicates_count == 0) else "partial_success"
        message_str = f"Successfully imported {imported_count} meter readings."
        if alerts_created > 0:
            message_str += f" ({alerts_created} anomaly alert(s) triggered)."
        elif skipped_duplicates_count > 0 or rejected_invalid_count > 0:
            message_str += f" ({skipped_duplicates_count} duplicates skipped, {rejected_invalid_count} invalid rows rejected)."
    else:
        status_str = "skipped"
        message_str = f"No new readings imported ({skipped_duplicates_count} duplicate records already exist in database)."

    return {
        "status": status_str,
        "filename": filename,
        "total_rows": total_rows,
        "imported_count": imported_count,
        "skipped_duplicates_count": skipped_duplicates_count,
        "rejected_invalid_count": rejected_invalid_count,
        "anomalies_detected": anomalies_detected,
        "alerts_created": alerts_created,
        "message": message_str,
        "details": details,
    }
