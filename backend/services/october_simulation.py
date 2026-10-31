"""Realistic Indian Household Consumption Simulation for October 1–31, 2026.

Simulates believable smart utility telemetry for an Indian residential household:
- Overnight low consumption (refrigerator cycling, fans, standby electronics)
- Morning peak (geyser/water heater, electric kettle, water pump)
- Afternoon steady load (work-from-home, fans, refrigerator)
- Evening peak (lighting, cooking appliances, entertainment, air cooling)
- Weekday vs. weekend behavioral variations (+15% daytime weekend load)
- Plausible grid voltage (220V - 238V) and power factor (0.94 - 0.98)
- Idempotent: checks for existing readings before insertion to prevent duplicates.
"""
from datetime import datetime, timedelta
import random
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.models import MeterReading

# Canonical hourly base profile in kWh for an active Indian residential household
HOURLY_BASE_KWH = {
    0: 0.35,   # Sleeping hours (refrigerator idle/fans)
    1: 0.32,
    2: 0.30,
    3: 0.28,
    4: 0.34,
    5: 0.45,   # Early morning wake-up
    6: 1.35,   # Morning routine begins
    7: 2.15,   # Geyser / water heater & water pump
    8: 2.55,   # Breakfast preparation / induction / kettle
    9: 1.65,   # Morning wind-down
    10: 1.15,  # Work-from-home / routine appliances
    11: 1.10,
    12: 1.35,  # Lunch cooking / microwave / refrigerator
    13: 1.40,
    14: 1.15,  # Afternoon idle
    15: 1.10,
    16: 1.25,
    17: 1.55,  # Evening tea / preparation
    18: 2.05,  # Sunset lighting / TV
    19: 2.85,  # Evening cooking / cooling
    20: 3.35,  # Dinner peak / multiple appliances active
    21: 2.60,  # Family entertainment / lighting
    22: 1.45,  # Preparing for bed / AC / cooling
    23: 0.75,  # Transition to sleep mode
}


def generate_october_reading(
    meter_id: str,
    timestamp: datetime,
    rng: random.Random,
) -> Dict[str, Any]:
    """Generate a single realistic hourly meter reading for a given timestamp."""
    hour = timestamp.hour
    is_weekend = timestamp.weekday() in (5, 6)  # Saturday=5, Sunday=6

    base_kwh = HOURLY_BASE_KWH.get(hour, 1.0)

    # Weekend occupancy boost for daytime hours (09:00 - 18:00)
    if is_weekend and 9 <= hour <= 18:
        base_kwh *= 1.18

    # Believable random variation (+/- 8%)
    noise_factor = rng.uniform(0.92, 1.08)
    usage_kwh = round(base_kwh * noise_factor, 2)

    # Realistic Indian grid voltage: 230V +/- 4V with slight evening sag
    voltage_sag = 2.5 if 19 <= hour <= 21 else 0.0
    voltage_v = round(rng.uniform(227.0, 233.0) - voltage_sag, 1)

    # Power factor: 0.95 - 0.98 typical for residential loads
    power_factor = round(rng.uniform(0.95, 0.98), 2)

    # Current in Amperes: I = P / (V * PF)
    # usage_kwh is energy over 1 hour, so average power in kW = usage_kwh
    power_watts = usage_kwh * 1000.0
    current_a = round(power_watts / (voltage_v * power_factor), 1)

    status = "High" if usage_kwh > 8.0 else "Normal"

    return {
        "meter_id": meter_id,
        "timestamp": timestamp,
        "usage_kwh": usage_kwh,
        "voltage_v": voltage_v,
        "current_a": current_a,
        "power_factor": power_factor,
        "status": status,
        "source": "simulated",
        "reading_type": "hourly",
    }


def seed_october_simulation(
    db: Session,
    meter_id: str = "EW-2847-HH",
    seed_value: int = 42,
) -> Dict[str, Any]:
    """Populate realistic Indian household simulation for October 1–31, 2026.

    Idempotent: If October readings are already populated for this meter,
    existing records are preserved without duplication.
    """
    rng = random.Random(seed_value)

    start_dt = datetime(2026, 10, 1, 0, 0, 0)
    end_dt = datetime(2026, 10, 31, 23, 0, 0)

    # Check existing October readings count
    existing_timestamps = set(
        ts[0]
        for ts in db.query(MeterReading.timestamp)
        .filter(
            MeterReading.meter_id == meter_id,
            MeterReading.timestamp >= start_dt,
            MeterReading.timestamp <= end_dt + timedelta(hours=1),
        )
        .all()
    )

    expected_hours = 31 * 24  # 744 hours
    if len(existing_timestamps) >= expected_hours:
        return {
            "status": "already_seeded",
            "inserted_count": 0,
            "existing_count": len(existing_timestamps),
            "meter_id": meter_id,
            "message": f"October 2026 simulated data already populated ({len(existing_timestamps)} hourly readings).",
        }

    readings_to_insert: List[MeterReading] = []
    curr = start_dt
    while curr <= end_dt:
        if curr not in existing_timestamps:
            reading_dict = generate_october_reading(meter_id, curr, rng)
            readings_to_insert.append(MeterReading(**reading_dict))
        curr += timedelta(hours=1)

    if readings_to_insert:
        db.add_all(readings_to_insert)
        db.commit()

    return {
        "status": "success",
        "inserted_count": len(readings_to_insert),
        "existing_count": len(existing_timestamps) + len(readings_to_insert),
        "meter_id": meter_id,
        "message": f"Successfully generated and inserted {len(readings_to_insert)} October 2026 simulated readings.",
    }

