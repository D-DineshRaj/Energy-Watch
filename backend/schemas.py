"""Pydantic schemas for EnergyWatch API request and response validation."""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class MeterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meter_id: str
    name: str
    consumer_name: str
    installation_date: Optional[date] = None
    meter_type: str
    sanctioned_load_kw: float
    status: str
    created_at: Optional[datetime] = None


class MeterDetailOut(MeterOut):
    readings_count: int = 0
    latest_reading_time: Optional[datetime] = None
    latest_reading_kwh: Optional[float] = None


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


class CSVImportResponse(BaseModel):
    status: str
    filename: str
    total_rows: int
    imported_count: int
    skipped_duplicates_count: int
    rejected_invalid_count: int
    anomalies_detected: Optional[int] = 0
    alerts_created: Optional[int] = 0
    message: str
    details: List[str] = []



class MetricsResponse(BaseModel):
    today_kwh: Optional[float] = None
    month_kwh: Optional[float] = None
    tomorrow_forecast_kwh: Optional[float] = None
    estimated_bill_inr: Optional[float] = None
    tariff_note: str = "Estimated using official APERC LT-I(A) Domestic tariff order for FY 2026-27. Not an official DISCOM bill."
    forecast_is_real_model: bool = False
    data_source: str = "simulated"
    current_date: Optional[str] = None
    latest_reading_date: Optional[str] = None
    today_has_data: bool = False
    month_has_data: bool = False
    today_message: Optional[str] = None
    month_message: Optional[str] = None
    historical_reference_kwh: Optional[float] = 420.0
    historical_reference_note: Optional[str] = "Historical baseline: 420 kWh in September 2026."


class ForecastDay(BaseModel):
    date: str
    day_name: str
    predicted_kwh: float
    lower_bound_kwh: Optional[float] = None
    upper_bound_kwh: Optional[float] = None
    is_peak: bool = False
    forecast_date: Optional[str] = None
    status: Optional[str] = "predicted"
    is_extrapolated_gap: Optional[bool] = False


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
    model_name: Optional[str] = None
    training_data_points: Optional[int] = None
    train_samples: Optional[int] = None
    test_samples: Optional[int] = None
    evaluation_split: Optional[str] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    baseline_model: Optional[str] = None
    baseline_mae: Optional[float] = None
    baseline_rmse: Optional[float] = None
    data_source: Optional[str] = "simulated"
    limitations: Optional[str] = None
    current_date: Optional[str] = None
    latest_historical_date: Optional[str] = None
    gap_days: Optional[int] = None
    is_extrapolated_gap: Optional[bool] = False
    forecast_status: Optional[str] = "extrapolated_forward"
    forecast_generation_date: Optional[str] = None


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


class AnomalyDetailOut(BaseModel):
    reading_id: Optional[int] = None
    usage_kwh: float
    is_anomaly: bool
    status: str
    reason: str
    z_score: float
    baseline_mean: float
    baseline_std: float
    sample_count: Optional[int] = 0
    comparison_scope: Optional[str] = None
    alert_status: Optional[str] = None
    alert_severity: Optional[str] = None


class AnomalyDetectionResponse(BaseModel):
    status: str
    meter_id: str
    total_scanned: int
    anomalies_detected: int
    alerts_created: int
    alerts_skipped_existing: int
    z_threshold: float
    min_kwh_threshold: float
    message: str
    details: List[AnomalyDetailOut] = []



class SlabBreakdownItem(BaseModel):
    slab_index: int
    slab_label: str
    min_kwh: float
    max_kwh: Optional[float] = None
    rate_per_kwh: float
    units_billed: float
    charge_inr: float


class BillEstimateResponse(BaseModel):
    consumption_kwh: float
    sanctioned_load_kw: float
    consumer_category: str
    state: str
    regulatory_authority: str
    tariff_order_ref: str
    effective_date: str
    official_source_url: str
    billing_method: str
    slabs_breakdown: List[SlabBreakdownItem]
    energy_charges_inr: float
    fixed_charges_inr: float
    electricity_duty_inr: float
    fpppa_charges_inr: float
    customer_charges_inr: float
    estimated_total_inr: float
    estimated_total_rounded_inr: int
    is_official_bill: bool = False
    calculation_assumptions: List[str]
    limitations: str


class DailyReportItem(BaseModel):
    date: str
    consumption_kwh: float
    reading_count: int
    peak_hour: Optional[str] = None
    peak_kwh: Optional[float] = None
    reading_type: str = "hourly"


class MonthlyReportItem(BaseModel):
    month: str
    consumption_kwh: float
    daily_avg_kwh: float
    days_count: int
    estimated_bill_inr: float


class ReportSummaryResponse(BaseModel):
    status: str
    meter_id: str
    start_date: str
    end_date: str
    total_consumption_kwh: float
    daily_avg_kwh: float
    days_count: int
    readings_count: int
    peak_day: Optional[str] = None
    peak_day_kwh: Optional[float] = None
    peak_hour: Optional[str] = None
    peak_hour_kwh: Optional[float] = None
    sanctioned_load_kw: float = 1.0
    estimated_bill_inr: float
    estimated_bill_rounded_inr: int
    bill_breakdown: BillEstimateResponse
    daily_breakdown: List[DailyReportItem] = []
    monthly_breakdown: List[MonthlyReportItem] = []
    data_source: str = "simulated"
    tariff_reference: str
    message: str


class StatementResponse(BaseModel):
    statement_id: str
    statement_date: str
    consumer_name: str = "Household Consumer"
    meter_id: str
    period_start: str
    period_end: str
    days_in_period: int
    total_kwh: float
    daily_avg_kwh: float
    peak_day: Optional[str] = None
    peak_day_kwh: Optional[float] = None
    bill_estimate: BillEstimateResponse
    daily_breakdown: List[DailyReportItem] = []
    is_official: bool = False
    disclaimer: str
