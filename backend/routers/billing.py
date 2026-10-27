"""Router for electricity bill estimation endpoints."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import TariffConfig
from backend.schemas import BillEstimateResponse
from backend.services.billing import calculate_aperc_bill, DEFAULT_APERC_TARIFF

router = APIRouter()


@router.get("/bill-estimate", response_model=BillEstimateResponse)
def get_bill_estimate(
    consumption_kwh: Optional[float] = Query(
        None,
        description="Monthly electricity consumption in kWh. Defaults to current month usage (420.0 kWh) if omitted.",
        ge=0.0,
    ),
    sanctioned_load_kw: float = Query(
        1.0,
        description="Sanctioned connected load in kW (must be positive).",
        gt=0.0,
        le=50.0,
    ),
    db: Session = Depends(get_db),
):
    """Calculate an itemized electricity bill estimate based on APERC domestic tariff schedule."""
    # Default to current month consumption if not explicitly passed
    units = 420.0 if consumption_kwh is None else consumption_kwh

    # Attempt to load active APERC tariff config from SQLite database
    tariff_dict = None
    try:
        active_config = (
            db.query(TariffConfig)
            .filter(TariffConfig.is_active == True)
            .first()
        )
        if active_config and active_config.slab_json:
            tariff_dict = json.loads(active_config.slab_json)
    except Exception:
        # Fall back gracefully to verified default schedule
        tariff_dict = DEFAULT_APERC_TARIFF

    try:
        result = calculate_aperc_bill(
            consumption_kwh=units,
            sanctioned_load_kw=sanctioned_load_kw,
            custom_tariff=tariff_dict,
        )
        return BillEstimateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
