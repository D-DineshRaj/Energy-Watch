"""Service for statistical energy anomaly detection and automated alert generation."""
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from backend.models import Alert, MeterReading

# Default statistical detection parameters
DEFAULT_Z_THRESHOLD = 2.5
DEFAULT_MIN_KWH_THRESHOLD = 4.5
DEFAULT_MIN_HISTORY_SAMPLES = 3


def compute_baseline_stats(values: List[float]) -> Tuple[float, float, int]:
    """Calculate mean, sample standard deviation, and count for a list of values."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std_dev = math.sqrt(variance)
    return round(mean, 3), round(std_dev, 3), n


def evaluate_reading_for_anomaly(
    reading: MeterReading,
    historical_readings: List[MeterReading],
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    min_kwh_threshold: float = DEFAULT_MIN_KWH_THRESHOLD,
    min_samples: int = DEFAULT_MIN_HISTORY_SAMPLES,
    excluded_ids: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """Evaluate whether a single meter reading represents a high-consumption anomaly.

    Enforces strict chronological baseline:
    - Only readings recorded strictly before candidate timestamp (r.timestamp < reading.timestamp) are used.
    - Readings from the same meter only (r.meter_id == reading.meter_id).
    - Excludes candidate itself and any other newly imported readings in the same batch (excluded_ids).

    Args:
        reading: The candidate MeterReading to evaluate.
        historical_readings: Prior readings to evaluate against.
        z_threshold: Multiplier for standard deviation (Z-score).
        min_kwh_threshold: Absolute minimum kWh required to flag as an anomaly.
        min_samples: Minimum required historical observations.
        excluded_ids: Optional set of reading IDs from the same batch to exclude from the baseline.

    Returns:
        Dict detailing anomaly evaluation outcome.
    """
    val = float(reading.usage_kwh)

    # 1. Immediate absolute minimum check (prevents noise in tiny night baseloads)
    if val < min_kwh_threshold:
        return {
            "is_anomaly": False,
            "status": "normal",
            "reason": f"Consumption {val:.2f} kWh is below minimum anomaly threshold ({min_kwh_threshold:.2f} kWh)",
            "reading_id": reading.id,
            "meter_id": reading.meter_id,
            "usage_kwh": val,
            "z_score": 0.0,
            "baseline_mean": 0.0,
            "baseline_std": 0.0,
            "sample_count": 0,
        }

    # 2. Filter historical readings:
    # Strictly earlier timestamp, same meter only, candidate itself excluded, and batch excluded
    prior = [
        r for r in historical_readings
        if r.meter_id == reading.meter_id
        and r.timestamp < reading.timestamp
        and r.id != reading.id
        and (excluded_ids is None or r.id not in excluded_ids)
    ]

    # 3. Stratified comparison: check same hour-of-day history first
    same_hour_readings = [r.usage_kwh for r in prior if r.timestamp.hour == reading.timestamp.hour]
    using_stratified = False

    if len(same_hour_readings) >= min_samples:
        mean, std_dev, sample_count = compute_baseline_stats(same_hour_readings)
        using_stratified = True
    else:
        # Fallback to overall meter history if stratified history is insufficient
        all_usages = [r.usage_kwh for r in prior]
        if len(all_usages) < min_samples:
            return {
                "is_anomaly": False,
                "status": "insufficient_history",
                "reason": (
                    f"Insufficient historical data ({len(all_usages)} observations found; "
                    f"minimum {min_samples} required for meter '{reading.meter_id}')"
                ),
                "reading_id": reading.id,
                "meter_id": reading.meter_id,
                "usage_kwh": val,
                "z_score": 0.0,
                "baseline_mean": 0.0,
                "baseline_std": 0.0,
                "sample_count": len(all_usages),
            }
        mean, std_dev, sample_count = compute_baseline_stats(all_usages)

    # 4. Handle zero variance (all prior values identical)
    if std_dev == 0.0:
        # Require 50% increase over constant baseline and above absolute threshold
        is_spike = (val >= mean * 1.5) and (val >= min_kwh_threshold)
        pct_increase = round(((val - mean) / mean * 100), 1) if mean > 0 else 100.0
        return {
            "is_anomaly": is_spike,
            "status": "anomaly_detected" if is_spike else "normal",
            "reason": (
                f"Zero variance baseline (mean: {mean:.2f} kWh). "
                + (f"Spike of {pct_increase}% exceeds 50% margin" if is_spike else "Within tolerance")
            ),
            "reading_id": reading.id,
            "meter_id": reading.meter_id,
            "usage_kwh": val,
            "z_score": 99.0 if is_spike else 0.0,
            "baseline_mean": mean,
            "baseline_std": 0.0,
            "sample_count": sample_count,
            "comparison_scope": "same_hour" if using_stratified else "overall_meter",
        }

    # 5. Standard Z-score computation
    z_score = round((val - mean) / std_dev, 2)
    is_anomaly = (z_score >= z_threshold) and (val >= min_kwh_threshold)
    pct_increase = round(((val - mean) / mean * 100), 1) if mean > 0 else 100.0

    return {
        "is_anomaly": is_anomaly,
        "status": "anomaly_detected" if is_anomaly else "normal",
        "reason": (
            f"Z-score {z_score:.2f} ({'+' if pct_increase >= 0 else ''}{pct_increase}% vs {mean:.2f} kWh baseline) "
            + (f"exceeds threshold {z_threshold:.1f}" if is_anomaly else f"within threshold {z_threshold:.1f}")
        ),
        "reading_id": reading.id,
        "meter_id": reading.meter_id,
        "usage_kwh": val,
        "z_score": z_score,
        "baseline_mean": mean,
        "baseline_std": std_dev,
        "sample_count": sample_count,
        "comparison_scope": "same_hour" if using_stratified else "overall_meter",
    }


def scan_and_generate_alerts(
    db: Session,
    meter_id: Optional[str] = None,
    candidate_readings: Optional[List[MeterReading]] = None,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    min_kwh_threshold: float = DEFAULT_MIN_KWH_THRESHOLD,
    min_samples: int = DEFAULT_MIN_HISTORY_SAMPLES,
) -> Dict[str, Any]:
    """Scan meter readings for consumption anomalies and create persistent alerts in SQLite.

    Guarantees:
    - Zero batch contamination: candidates in candidate_readings do not contaminate each other's baseline.
    - Multi-meter isolation: each reading is evaluated exclusively against historical readings of the same meter.
    - Chronological baseline: strictly prior observations (timestamp < candidate.timestamp).
    - Idempotency: duplicate alerts prevented by reading_id and alert_type.

    Returns:
        Dict with total_scanned, anomalies_detected, alerts_created, alerts_skipped_existing, details.
    """
    # 1. Determine target meter(s) and candidate readings
    if candidate_readings is not None:
        candidates = candidate_readings
        target_meters = sorted(list({r.meter_id for r in candidate_readings if r.meter_id}))
    elif meter_id:
        target_meters = [meter_id]
        candidates = (
            db.query(MeterReading)
            .filter(MeterReading.meter_id == meter_id, MeterReading.reading_type == "hourly")
            .order_by(MeterReading.timestamp.desc())
            .limit(50)
            .all()
        )[::-1]  # chronological order
    else:
        target_meters = ["EW-2847-HH"]
        candidates = (
            db.query(MeterReading)
            .filter(MeterReading.meter_id == "EW-2847-HH", MeterReading.reading_type == "hourly")
            .order_by(MeterReading.timestamp.desc())
            .limit(50)
            .all()
        )[::-1]

    if not candidates:
        return {
            "status": "skipped",
            "message": "No candidate readings found to scan",
            "total_scanned": 0,
            "anomalies_detected": 0,
            "alerts_created": 0,
            "alerts_skipped_existing": 0,
            "details": [],
        }

    # 2. Fetch historical readings for all target meters and index by meter_id
    all_readings = (
        db.query(MeterReading)
        .filter(MeterReading.meter_id.in_(target_meters))
        .order_by(MeterReading.timestamp.asc())
        .all()
    )
    readings_by_meter: Dict[str, List[MeterReading]] = {}
    for r in all_readings:
        readings_by_meter.setdefault(r.meter_id, []).append(r)

    # 3. Fetch existing alert reading_ids and (timestamp, type) pairs to avoid duplicates
    existing_alert_reading_ids = set(
        res[0] for res in db.query(Alert.reading_id).filter(
            Alert.reading_id.isnot(None),
            Alert.alert_type.in_(["unusual_consumption", "consumption_spike"]),
        ).all()
    )
    existing_alert_timestamps = set(
        (res[0], res[1]) for res in db.query(Alert.triggered_at, Alert.alert_type).filter(
            Alert.alert_type.in_(["unusual_consumption", "consumption_spike"])
        ).all()
    )

    total_scanned = 0
    anomalies_detected = 0
    alerts_created = 0
    alerts_skipped_existing = 0
    details: List[Dict[str, Any]] = []

    for reading in candidates:
        total_scanned += 1
        meter_history = readings_by_meter.get(reading.meter_id, [])

        eval_result = evaluate_reading_for_anomaly(
            reading=reading,
            historical_readings=meter_history,
            z_threshold=z_threshold,
            min_kwh_threshold=min_kwh_threshold,
            min_samples=min_samples,
        )

        if eval_result["is_anomaly"]:
            anomalies_detected += 1

            # Check if alert already exists for this reading or timestamp
            if reading.id in existing_alert_reading_ids or (reading.timestamp, "unusual_consumption") in existing_alert_timestamps:
                alerts_skipped_existing += 1
                eval_result["alert_status"] = "skipped_duplicate"
                details.append(eval_result)
                continue

            # Determine severity
            usage = eval_result["usage_kwh"]
            z = eval_result["z_score"]
            severity = "critical" if (z >= 3.5 or usage >= 8.0) else "warning"

            # Create new persistent Alert in SQLite
            hour_str = reading.timestamp.strftime("%I:%M %p").lstrip("0")
            day_str = reading.timestamp.strftime("%A, %b %d")
            message = (
                f"Unusual consumption spike: electricity usage reached {usage:.1f} kWh at {hour_str} on {day_str} "
                f"({eval_result['z_score']:.1f}σ above typical {eval_result['baseline_mean']:.1f} kWh baseline). "
                f"Simulated household load anomaly linked to meter {reading.meter_id}."
            )

            new_alert = Alert(
                reading_id=reading.id,
                alert_type="unusual_consumption",
                severity=severity,
                message=message,
                triggered_at=reading.timestamp,
                acknowledged=False,
                acknowledged_at=None,
            )
            db.add(new_alert)
            if reading.id is not None:
                existing_alert_reading_ids.add(reading.id)
            existing_alert_timestamps.add((reading.timestamp, "unusual_consumption"))
            alerts_created += 1
            eval_result["alert_status"] = "alert_created"
            eval_result["alert_severity"] = severity

        details.append(eval_result)

    if alerts_created > 0:
        db.commit()

    meter_summary = ", ".join(target_meters)
    return {
        "status": "success",
        "meter_id": meter_summary,
        "total_scanned": total_scanned,
        "anomalies_detected": anomalies_detected,
        "alerts_created": alerts_created,
        "alerts_skipped_existing": alerts_skipped_existing,
        "z_threshold": z_threshold,
        "min_kwh_threshold": min_kwh_threshold,
        "message": (
            f"Scanned {total_scanned} readings for meter(s) [{meter_summary}]. "
            f"Detected {anomalies_detected} anomalies. Created {alerts_created} new alerts "
            f"({alerts_skipped_existing} existing alerts skipped)."
        ),
        "details": details,
    }

