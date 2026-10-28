"""EnergyWatch FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.routers.alerts import router as alerts_router
from backend.routers.billing import router as billing_router
from backend.routers.consumption import router as consumption_router
from backend.routers.forecast import router as forecast_router
from backend.routers.metrics import router as metrics_router
from backend.routers.readings import router as readings_router
from backend.routers.reports import router as reports_router
from backend.schemas import HealthResponse

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    yield


app = FastAPI(
    title="EnergyWatch API",
    description="Household Electricity Monitoring & Forecasting Dashboard API",
    version="1.0.0-phase1",
    lifespan=lifespan,
)

# CORS configuration restricted to local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 1. Health check registered first
@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Verify backend and database operational status."""
    return HealthResponse(
        status="ok",
        version="1.0.0-phase1",
        database="connected",
    )


# 2. API routers registered BEFORE static file mount (Correction 7)
app.include_router(readings_router, prefix="/api", tags=["Readings"])
app.include_router(metrics_router, prefix="/api", tags=["Metrics"])
app.include_router(billing_router, prefix="/api", tags=["Billing"])
app.include_router(consumption_router, prefix="/api", tags=["Consumption"])
app.include_router(forecast_router, prefix="/api", tags=["Forecast"])
app.include_router(alerts_router, prefix="/api", tags=["Alerts"])
app.include_router(reports_router, prefix="/api", tags=["Reports"])

# 3. Static files mounted LAST (Correction 1 & 7)
# Serves index.html from project root at http://localhost:8000/
app.mount("/", StaticFiles(directory=str(_PROJECT_ROOT), html=True), name="static")
