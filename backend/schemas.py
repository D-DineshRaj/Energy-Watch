"""Pydantic schemas for EnergyWatch API request and response validation."""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class MeterReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meter_id: str
    timestamp: datetime
    usage_kwh: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_factor: Optional[float] = None
    status: str
    source: str
    reading_type: Optional[str] = "hourly"
    created_at: Optional[datetime] = None


class MetricsResponse(BaseModel):
    today_kwh: float
    month_kwh: float
    tomorrow_forecast_kwh: Optional[float] = None
    estimated_bill_inr: Optional[float] = None  # Always None in Phase 1 per Correction 4
    tariff_note: str = "Bill estimation not yet implemented. Configurable AP tariff rules will be added in Phase 4."
    forecast_is_real_model: bool = False
    data_source: str = "simulated"


class ForecastDay(BaseModel):
    date: str
    day_name: str
    predicted_kwh: float
    lower_bound_kwh: Optional[float] = None
    upper_bound_kwh: Optional[float] = None
    is_peak: bool = False


class ForecastResponse(BaseModel):
    model: str = "static_seed"
    is_real_model: bool = False
    is_computed: bool = False
    note: str = (
        "Forecast values are static sample data seeded from the original mock dashboard. "
        "No forecasting computation has been performed."
    )
    days: List[ForecastDay]
    chart_labels: List[str]
    actual_series: List[Optional[float]]
    forecast_series: List[Optional[float]]


class ConsumptionResponse(BaseModel):
    range: str
    labels: List[str]
    actual: List[Optional[float]]
    forecast: List[Optional[float]]
    unit: str = "kWh"
    source: str = "simulated"


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reading_id: Optional[int] = None
    alert_type: str
    severity: str
    message: str
    triggered_at: datetime
    acknowledged: bool
    acknowledged_at: Optional[datetime] = None


class AlertAcknowledgeResponse(BaseModel):
    id: int
    acknowledged: bool
    acknowledged_at: datetime
    message: str
