"""SQLAlchemy database models for EnergyWatch."""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(String(50), nullable=False, default="EW-2847-HH", index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    usage_kwh = Column(Float, nullable=False)
    voltage_v = Column(Float, nullable=True)
    current_a = Column(Float, nullable=True)
    power_factor = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="Normal")
    source = Column(String(20), nullable=False, default="simulated")
    reading_type = Column(String(20), nullable=False, default="hourly")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("usage_kwh >= 0", name="chk_usage_kwh_non_negative"),
        CheckConstraint("status IN ('Normal', 'High')", name="chk_status_valid"),
        CheckConstraint("source IN ('simulated', 'real')", name="chk_source_valid"),
        CheckConstraint("reading_type IN ('hourly', 'daily')", name="chk_reading_type_valid"),
    )

    alerts = relationship("Alert", back_populates="reading")


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    forecast_date = Column(Date, nullable=False, index=True)
    predicted_kwh = Column(Float, nullable=False)
    lower_bound_kwh = Column(Float, nullable=True)
    upper_bound_kwh = Column(Float, nullable=True)
    model_name = Column(String(50), nullable=False, default="static_seed")
    is_ml_model = Column(Boolean, nullable=False, default=False)
    data_source = Column(String(20), nullable=False, default="simulated")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    reading_id = Column(Integer, ForeignKey("meter_readings.id", ondelete="SET NULL"), nullable=True)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="warning")
    message = Column(Text, nullable=False)
    triggered_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_at = Column(DateTime, nullable=True)

    reading = relationship("MeterReading", back_populates="alerts")


class TariffConfig(Base):
    __tablename__ = "tariff_configs"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(50), nullable=False, default="Andhra Pradesh")
    category = Column(String(50), nullable=False, default="Domestic")
    slab_json = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    effective_from = Column(Date, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
