"""Router for consumption trends endpoints."""
from datetime import date, timedelta
from enum import Enum
from fastapi import APIRouter, Query
from backend.schemas import ConsumptionResponse

router = APIRouter()


class ConsumptionRange(str, Enum):
    seven_days = "7d"
    thirty_days = "30d"
    three_months = "3m"


# Static baseline datasets preserving original dashboard mock values
_DATASETS = {
    ConsumptionRange.seven_days: {
        "labels": [
            "Sep 2", "Sep 3", "Sep 4", "Sep 5", "Sep 6",
            "Sep 7", "Sep 8", "Sep 9", "Sep 10",
        ],
        "actual": [32.1, 29.8, 34.5, 31.2, 33.9, 33.9, 35.4, None, None],
        "forecast": [None, None, None, None, None, None, 35.4, 37.2, 38.1],
    },
    ConsumptionRange.thirty_days: {
        "labels": [
            f"{(date(2026, 8, 10) + timedelta(days=i)).day} {(date(2026, 8, 10) + timedelta(days=i)).strftime('%b')}"
            for i in range(30)
        ],
        "actual": [
            28.2, 30.1, 29.5, 31.8, 27.3, 30.9, 32.4, 28.8, 31.2, 29.9,
            33.5, 30.2, 31.7, 29.4, 32.1, 30.8, 33.2, 31.5, 30.3, 32.8,
            33.1, 31.9, 32.4, 33.8, 31.2, 33.9, 33.9, 34.2, 35.1, 35.4,
        ],
        "forecast": [],
    },
    ConsumptionRange.three_months: {
        "labels": [
            "Jul 1", "Jul 8", "Jul 15", "Jul 22", "Jul 29",
            "Aug 5", "Aug 12", "Aug 19", "Aug 26", "Sep 2", "Sep 8",
        ],
        "actual": [26.1, 27.4, 28.2, 27.9, 28.8, 29.5, 30.2, 31.8, 32.4, 33.1, 35.4],
        "forecast": [],
    },
}


@router.get("/consumption", response_model=ConsumptionResponse)
def get_consumption(
    range: ConsumptionRange = Query(..., description="Time range: 7d, 30d, or 3m"),
):
    """Retrieve historical consumption series and forecast overlay."""
    ds = _DATASETS[range]
    return ConsumptionResponse(
        range=range.value,
        labels=ds["labels"],
        actual=ds["actual"],
        forecast=ds["forecast"],
        unit="kWh",
        source="simulated",
    )
