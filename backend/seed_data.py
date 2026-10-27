"""Idempotent seed script to populate SQLite with baseline simulated electricity data."""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Add project root to path if running standalone
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal, init_db
from backend.models import Alert, Forecast, MeterReading, TariffConfig
from backend.services.billing import DEFAULT_APERC_TARIFF


def seed_readings(db) -> dict:
    existing = db.query(MeterReading).count()
    if existing > 0:
        return {"status": "skipped", "count": existing, "message": f"{existing} readings already exist"}

    readings = []

    # 1. Today's hourly readings (Sep 8, 2026)
    today_hourly = [
        ("06:00:00", 2.1, 230.1, 9.1, 0.98, "Normal"),
        ("08:00:00", 2.1, 229.8, 9.1, 0.97, "Normal"),
        ("10:00:00", 3.2, 231.2, 13.8, 0.96, "Normal"),
        ("12:00:00", 4.1, 228.5, 17.9, 0.95, "Normal"),
        ("14:00:00", 3.8, 230.0, 16.5, 0.96, "Normal"),
        ("16:00:00", 3.5, 229.4, 15.2, 0.97, "Normal"),
        ("18:00:00", 4.2, 230.8, 18.2, 0.95, "Normal"),
        ("20:00:00", 8.9, 227.1, 39.2, 0.92, "High"),
        ("22:00:00", 3.1, 230.5, 13.4, 0.98, "Normal"),
    ]
    for t_str, usage, volt, curr, pf, status in today_hourly:
        readings.append(
            MeterReading(
                meter_id="EW-2847-HH",
                timestamp=datetime.strptime(f"2026-09-08 {t_str}", "%Y-%m-%d %H:%M:%S"),
                usage_kwh=usage,
                voltage_v=volt,
                current_a=curr,
                power_factor=pf,
                status=status,
                source="simulated",
                reading_type="hourly",
            )
        )

    # 2. Yesterday's hourly readings (Sep 7, 2026)
    yesterday_hourly = [
        ("06:00:00", 2.0, 230.0, 8.7, 0.98, "Normal"),
        ("08:00:00", 2.1, 229.5, 9.1, 0.97, "Normal"),
        ("10:00:00", 2.8, 231.0, 12.1, 0.96, "Normal"),
        ("12:00:00", 3.7, 228.9, 16.1, 0.95, "Normal"),
        ("14:00:00", 3.6, 230.2, 15.6, 0.96, "Normal"),
        ("16:00:00", 3.3, 229.7, 14.3, 0.97, "Normal"),
        ("18:00:00", 4.1, 230.5, 17.8, 0.95, "Normal"),
        ("20:00:00", 4.6, 228.1, 20.1, 0.94, "Normal"),
        ("22:00:00", 2.8, 230.8, 12.1, 0.98, "Normal"),
    ]
    for t_str, usage, volt, curr, pf, status in yesterday_hourly:
        readings.append(
            MeterReading(
                meter_id="EW-2847-HH",
                timestamp=datetime.strptime(f"2026-09-07 {t_str}", "%Y-%m-%d %H:%M:%S"),
                usage_kwh=usage,
                voltage_v=volt,
                current_a=curr,
                power_factor=pf,
                status=status,
                source="simulated",
                reading_type="hourly",
            )
        )

    # 3. Week daily readings (Sep 2 - Sep 8, 2026)
    week_daily = [
        ("2026-09-02", 32.1),
        ("2026-09-03", 29.8),
        ("2026-09-04", 34.5),
        ("2026-09-05", 31.2),
        ("2026-09-06", 33.9),
        ("2026-09-07", 33.9),
        ("2026-09-08", 35.4),
    ]
    for d_str, usage in week_daily:
        readings.append(
            MeterReading(
                meter_id="EW-2847-HH",
                timestamp=datetime.strptime(f"{d_str} 23:59:59", "%Y-%m-%d %H:%M:%S"),
                usage_kwh=usage,
                voltage_v=230.0,
                current_a=None,
                power_factor=0.96,
                status="Normal",
                source="simulated",
                reading_type="daily",
            )
        )

    db.add_all(readings)
    db.commit()
    return {"status": "seeded", "count": len(readings), "message": f"Inserted {len(readings)} readings"}


def seed_forecasts(db) -> dict:
    existing = db.query(Forecast).count()
    if existing > 0:
        return {"status": "skipped", "count": existing, "message": f"{existing} forecasts already exist"}

    forecasts = [
        Forecast(
            forecast_date=date(2026, 9, 8),
            predicted_kwh=35.4,
            lower_bound_kwh=33.0,
            upper_bound_kwh=37.5,
            model_name="static_seed",
            is_ml_model=False,
            data_source="simulated",
        ),
        Forecast(
            forecast_date=date(2026, 9, 9),
            predicted_kwh=37.2,
            lower_bound_kwh=34.5,
            upper_bound_kwh=39.8,
            model_name="static_seed",
            is_ml_model=False,
            data_source="simulated",
        ),
        Forecast(
            forecast_date=date(2026, 9, 10),
            predicted_kwh=38.1,
            lower_bound_kwh=35.2,
            upper_bound_kwh=41.0,
            model_name="static_seed",
            is_ml_model=False,
            data_source="simulated",
        ),
    ]
    db.add_all(forecasts)
    db.commit()
    return {"status": "seeded", "count": len(forecasts), "message": f"Inserted {len(forecasts)} static forecasts"}


def seed_alerts(db) -> dict:
    existing = db.query(Alert).count()
    if existing > 0:
        return {"status": "skipped", "count": existing, "message": f"{existing} alerts already exist"}

    # Find the high spike reading if it exists
    high_reading = (
        db.query(MeterReading)
        .filter(MeterReading.status == "High")
        .first()
    )

    alert = Alert(
        reading_id=high_reading.id if high_reading else None,
        alert_type="unusual_consumption",
        severity="warning",
        message=(
            "Your electricity usage at 8:00 PM on Monday reached 8.9 kWh — "
            "63% above your typical evening pattern. This may indicate a high-draw appliance left running."
        ),
        triggered_at=datetime(2026, 9, 8, 20, 0, 0),
        acknowledged=False,
        acknowledged_at=None,
    )
    db.add(alert)
    db.commit()
    return {"status": "seeded", "count": 1, "message": "Inserted 1 baseline alert"}


def seed_tariffs(db) -> dict:
    existing = db.query(TariffConfig).filter(TariffConfig.is_active == True).first()
    if existing:
        existing.slab_json = json.dumps(DEFAULT_APERC_TARIFF)
        existing.effective_from = date(2026, 4, 1)
        db.commit()
        return {"status": "skipped", "count": 1, "message": "Active APERC FY 2026-27 tariff config refreshed"}

    config = TariffConfig(
        state="Andhra Pradesh",
        category="LT Category-I(A): Domestic",
        slab_json=json.dumps(DEFAULT_APERC_TARIFF),
        is_active=True,
        effective_from=date(2026, 4, 1),
    )
    db.add(config)
    db.commit()
    return {"status": "seeded", "count": 1, "message": "Inserted 1 APERC verified domestic tariff config"}


def run_seed():
    """Execute complete seeding process idempotently."""
    print("=" * 60)
    print("EnergyWatch — Database Seeder (Phases 1-3)")
    print("=" * 60)
    init_db()
    db = SessionLocal()
    try:
        r1 = seed_readings(db)
        r2 = seed_forecasts(db)
        r3 = seed_alerts(db)
        r4 = seed_tariffs(db)

        print(f"Readings:  [{r1['status'].upper()}] - {r1['message']}")
        print(f"Forecasts: [{r2['status'].upper()}] - {r2['message']}")
        print(f"Alerts:    [{r3['status'].upper()}] - {r3['message']}")
        print(f"Tariffs:   [{r4['status'].upper()}] - {r4['message']}")
        print("=" * 60)
        return {"readings": r1, "forecasts": r2, "alerts": r3, "tariffs": r4}
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
