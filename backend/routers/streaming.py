"""Router for multithreaded meter reading streaming and producer-consumer demonstration (OS Module)."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Query

from backend.services.multithreaded_ingestion import ingestion_manager

router = APIRouter()


@router.get("/stream/stats")
def get_stream_statistics() -> Dict[str, Any]:
    """Retrieve real-time producer-consumer metrics, queue length, and memory buffer status."""
    return ingestion_manager.get_statistics()


@router.post("/stream/simulate")
def start_concurrent_simulation(
    num_producers: int = Query(3, ge=1, le=10, description="Number of concurrent producer threads to launch"),
    readings_per_producer: int = Query(6, ge=1, le=50, description="Readings generated per producer"),
    interval_seconds: float = Query(0.05, ge=0.01, le=1.0, description="Delay between reading submissions"),
) -> Dict[str, Any]:
    """Spawn multiple concurrent producer threads that submit readings to the thread-safe queue."""
    return ingestion_manager.start_concurrent_simulation(
        num_producers=num_producers,
        readings_per_producer=readings_per_producer,
        interval_seconds=interval_seconds,
    )


@router.post("/stream/submit")
def submit_single_reading(
    reading: Dict[str, Any] = Body(
        ...,
        openapi_examples={
            "standard_reading": {
                "summary": "Sample smart meter hourly telemetry reading",
                "value": {
                    "meter_id": "EW-2847-HH",
                    "usage_kwh": 2.15,
                    "voltage_v": 230.2,
                    "power_factor": 0.97,
                    "status": "Normal",
                    "source": "simulated",
                    "reading_type": "hourly",
                },
            }
        },
    ),
) -> Dict[str, Any]:
    """Submit a single meter reading directly to the thread-safe queue from an external smart meter."""
    success = ingestion_manager.submit_reading(reading)
    return {
        "status": "queued" if success else "failed",
        "reading": reading,
        "message": "Reading placed onto thread-safe queue for asynchronous batch insertion.",
    }


@router.post("/stream/flush")
def flush_stream_buffer() -> Dict[str, Any]:
    """Manually trigger immediate flushing of the in-memory buffer to the SQLite database."""
    ingestion_manager.flush()
    return {
        "status": "flushed",
        "stats": ingestion_manager.get_statistics(),
        "message": "Queue and memory buffer successfully drained to SQLite database.",
    }
