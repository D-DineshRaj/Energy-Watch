"""EnergyWatch FastAPI application entry point."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import SessionLocal, init_db
from backend.routers.alerts import router as alerts_router
from backend.routers.billing import router as billing_router
from backend.routers.consumption import router as consumption_router
from backend.routers.forecast import router as forecast_router
from backend.routers.meters import router as meters_router
from backend.routers.metrics import router as metrics_router
from backend.routers.readings import router as readings_router
from backend.routers.reports import router as reports_router
from backend.routers.streaming import router as streaming_router
from backend.schemas import HealthResponse
from backend.services.multithreaded_ingestion import ingestion_manager
from backend.services.october_simulation import seed_october_simulation

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize database tables and seed default meter on startup
    init_db()

    # 2. Automatically ensure October demonstration simulation is populated idempotently
    db = SessionLocal()
    try:
        seed_october_simulation(db)
    except Exception:
        db.rollback()
    finally:
        db.close()

    yield

    # Clean shutdown of multithreaded ingestion manager and queue flushing
    ingestion_manager.shutdown()


app = FastAPI(
    title="EnergyWatch API",
    description="Smart Utility Consumption Forecasting System (3-1 Academic Project 24091A3239)",
    version="1.0.0-final",
    lifespan=lifespan,
)

# CORS configuration supporting local dev (port 8082, 8000) and cloud deployments (Vercel, Render)
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
allowed_origins = [
    "http://localhost:8082",
    "http://127.0.0.1:8082",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if cors_origins_env:
    for o in cors_origins_env.split(","):
        if o.strip() and o.strip() not in allowed_origins:
            allowed_origins.append(o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$|^https://.*\.vercel\.app$|^https://.*\.onrender\.com$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 1. Health check registered first
@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Verify backend and database operational status."""
    return HealthResponse(
        status="ok",
        version="1.0.0-final",
        database="connected",
    )


# 2. API routers registered BEFORE static file mount
app.include_router(readings_router, prefix="/api", tags=["Readings"])
app.include_router(metrics_router, prefix="/api", tags=["Metrics"])
app.include_router(billing_router, prefix="/api", tags=["Billing"])
app.include_router(consumption_router, prefix="/api", tags=["Consumption"])
app.include_router(forecast_router, prefix="/api", tags=["Forecast"])
app.include_router(alerts_router, prefix="/api", tags=["Alerts"])
app.include_router(reports_router, prefix="/api", tags=["Reports"])
app.include_router(meters_router, prefix="/api", tags=["DBMS - Meters"])
app.include_router(streaming_router, prefix="/api", tags=["OS - Multithreaded Stream"])

# 3. Static files mounted LAST
# Serves index.html from project root at http://localhost:8082/ or http://localhost:8000/
app.mount("/", StaticFiles(directory=str(_PROJECT_ROOT), html=True), name="static")
