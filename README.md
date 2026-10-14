# ⚡ EnergyWatch — Smart Utility Consumption Dashboard

EnergyWatch is a household electricity monitoring and forecasting application designed to help users track power consumption (kWh), inspect historical trends, detect unusual load spikes, and view predictive consumption insights.

---

## 📌 Project Status: Working Full-Stack Prototype (~65% Milestone)

| Layer | Status | Implementation Details |
|---|---|---|
| **Frontend UI** | ✅ Fully Functional | Connected to live FastAPI endpoints; Chart.js graphs, filter chips, dynamic alerts |
| **Backend API** | ✅ Operational | FastAPI application with CORS and lifespan database initialization |
| **Database** | ✅ Operational | SQLite (`data/energywatch.db`) via SQLAlchemy 2.1.4 |
| **Data Seeder** | ✅ Operational | Idempotent baseline seeder for simulated readings and alerts |
| **Alert Management** | ✅ Interactive | Full acknowledgement & reset cycle persisted in SQLite |
| **ML Forecasts** | ⚠️ Static Simulation | Model labelled `static_seed` (Machine learning pipeline planned for Phase 5) |
| **Electricity Tariff** | ⚠️ Pending APERC | Kept `null` pending official APERC tariff schedule verification (Phase 4) |

---

## 🏗️ Architecture

```
EnergyWatch/
├── index.html                  # Responsive frontend dashboard connected to FastAPI
├── requirements.txt            # Pinned dependencies for Python 3.14.3
├── .gitignore                  # Exclusion rules for venv, DB, secrets, and caches
├── README.md                   # Project documentation and developer guide
├── data/
│   ├── .gitkeep                # Git tracking stub for database folder
│   └── energywatch.db          # SQLite database (auto-generated, untracked)
└── backend/
    ├── __init__.py             # Backend package marker
    ├── main.py                 # FastAPI app, middleware, and route mounting
    ├── database.py             # Database engine and session management
    ├── models.py               # SQLAlchemy ORM models (Readings, Forecasts, Alerts)
    ├── schemas.py              # Pydantic request and response schemas
    ├── seed_data.py            # Idempotent database population script
    └── routers/
        ├── __init__.py         # Routers package marker
        ├── readings.py         # /api/readings (today, yesterday, week)
        ├── metrics.py          # /api/metrics (usage summaries, null bill)
        ├── consumption.py      # /api/consumption (7d, 30d, 3m trends)
        ├── forecast.py         # /api/forecast (static sample forecasts)
        └── alerts.py           # /api/alerts (retrieval, acknowledge, & reset)
```

---

## 🚀 Quick Start for Windows

Open **PowerShell** in the project directory (`C:\Projects\EnergyWatrch(3-1)`):

### 1. (One-time) Seed the SQLite Database
```powershell
.venv\Scripts\python.exe backend/seed_data.py
```
*(The seeder is strictly idempotent; re-running it skips duplicate records safely).*

### 2. Start the FastAPI Development Server
```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

### 3. Open the Dashboard in your Browser
- **Live Dashboard:** [http://localhost:8000/](http://localhost:8000/)
- **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧑‍🏫 Mentor Demonstration Guide

Follow these steps to demonstrate the working full-stack application to your mentor:

1. **System Health & Architecture:**
   - Notice the status chip in the top banner: **"Backend Online · SQLite Connected"**.
   - Explain that the single-page application is served directly by **FastAPI** and communicates asynchronously with SQLite via JSON REST endpoints.
2. **Dynamic Metric Cards:**
   - Point out **Today's Usage** (35.4 kWh) and **This Month** (420 kWh), which dynamically animate using count-up transitions.
   - Explain the honest labelling: **Tomorrow's Forecast** is tagged `Static Baseline`, and **Estimated Bill** displays `Pending Tariff` because official Andhra Pradesh Electricity Regulatory Commission (APERC) slabs will be integrated in Phase 4.
3. **Interactive Consumption History Chart:**
   - Click the **30 Days** tab: observe the chart re-render with daily bar series from SQLite and dynamic average calculation.
   - Click the **3 Months** tab: observe the quarterly aggregation and seasonal trend insight.
   - Click the **7 Days** tab: observe the actual usage bars with the yellow forecast overlay.
4. **Live SQLite Meter Readings Table:**
   - Show the hourly readings table with cumulative meter readings, interval usage, and line voltage.
   - Click the **Yesterday** filter button to query yesterday's hourly log from SQLite.
   - Click the **This Week** filter button to query daily summary totals.
   - Click **Today** to return to the active hourly stream.
5. **Interactive Anomaly Detection & State Persistence:**
   - Show the **Smart Alert** card identifying the 8.9 kWh spike at 8:00 PM. Notice the red notification dot on the bell icon in the navbar.
   - Click **"Acknowledge Alert"**:
     - The button updates, calls `POST /api/alerts/1/acknowledge`, and persists the change to SQLite.
     - The card transitions to **"✅ All Systems Normal"** and the bell red dot disappears.
   - Click **"Re-arm Demo Alert"** to reset the alert back to active status, proving two-way live database communication.
6. **Backend Transparency (Swagger UI):**
   - Click the **"API Docs"** button in the top banner to open `/docs` and show your mentor the automated OpenAPI contracts for all endpoints.

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application status and database health check |
| `GET` | `/api/readings?filter=today` | Hourly simulated meter readings for current day |
| `GET` | `/api/readings?filter=yesterday` | Hourly simulated readings for yesterday |
| `GET` | `/api/readings?filter=week` | Daily simulated totals for the past 7 days |
| `GET` | `/api/metrics` | Summary metrics card data (`estimated_bill_inr` is `null`) |
| `GET` | `/api/consumption?range=7d` | Consumption trend data (7-day series + forecast overlay) |
| `GET` | `/api/consumption?range=30d` | 30-day historical consumption series |
| `GET` | `/api/consumption?range=3m` | 3-month aggregated consumption series |
| `GET` | `/api/forecast` | Static sample forecasts labelled as simulation |
| `GET` | `/api/alerts` | List unacknowledged anomaly alerts |
| `POST` | `/api/alerts/{id}/acknowledge` | Mark an alert as acknowledged in SQLite |
| `POST` | `/api/alerts/{id}/reset` | Re-arm an alert for demonstration testing |

---

## ⚠️ Data Disclaimer & Roadmap

- **Simulated Meter Data:** Readings represent simulated household patterns (Meter `EW-2847-HH`) used to validate full-stack data flow and API contracts.
- **Static Forecasts:** Forecast values represent a static seed baseline. Real machine learning models (e.g., ARIMA / Random Forest / Gradient Boosting) are scheduled for **Phase 5**.
- **Tariff Schedule:** Electricity billing estimation is deferred until **Phase 4**, where official multi-tier APERC tariff schedules and fixed charges will be configured.
