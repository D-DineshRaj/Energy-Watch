# ⚡ EnergyWatch — Smart Utility Consumption Dashboard

EnergyWatch is a household electricity monitoring and forecasting application designed to help users track power consumption (kWh), inspect historical trends, detect unusual load spikes, and view predictive consumption insights.

---

## 📌 Project Status: Phase 1 (Backend & SQLite Foundation)

| Layer | Status | Implementation Details |
|---|---|---|
| **Frontend UI** | Preserved Baseline | Original `index.html` dashboard preserved byte-for-byte |
| **Backend API** | ✅ Operational | FastAPI with Python 3.14 compatibility |
| **Database** | ✅ Operational | SQLite (`data/energywatch.db`) via SQLAlchemy 2.1.4 |
| **Data Seeder** | ✅ Operational | Idempotent baseline seeder for simulated readings and alerts |
| **ML Forecasts** | ⚠️ Static Simulation | Model labelled `static_seed` (ML pipeline planned for Phase 5) |
| **Electricity Tariff** | ⚠️ Pending APERC | Kept `null` pending official APERC tariff schedule verification |

---

## 🏗️ Architecture

```
EnergyWatch/
├── index.html                  # Responsive frontend dashboard (preserved baseline)
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
        └── alerts.py           # /api/alerts (retrieval & acknowledgement)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.14.x installed on your system.
- Git 2.40+ installed.

### 2. Environment Setup
Create and activate the virtual environment:
```powershell
# Create virtual environment in project root
python -m venv .venv

# Activate on Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Seed the Database
Populate the database with sample baseline electricity readings:
```powershell
.venv\Scripts\python.exe backend/seed_data.py
```
*(The script is strictly idempotent: re-running it skips duplicate records safely).*

### 5. Run the Application
Start the Uvicorn development server:
```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

- **Dashboard:** Open [http://localhost:8000/](http://localhost:8000/) in your browser.
- **Interactive API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative API Docs (ReDoc):** [http://localhost:8000/redoc](http://localhost:8000/redoc)

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
| `POST` | `/api/alerts/{id}/acknowledge` | Mark an alert as acknowledged |

---

## ⚠️ Known Limitations & Disclaimers (Phase 1)

1. **Simulated Meter Data:** All meter readings and alerts are mock/simulated sample records designed to establish API contracts and schemas.
2. **Static Forecasts:** The forecast endpoint provides static seed values to mirror dashboard cards. Real machine learning computation will be integrated in Phase 5.
3. **Billing Rates:** `estimated_bill_inr` is returned as `null`. A preliminary rate of ₹7.73/kWh from initial mockups is unverified; official Andhra Pradesh Electricity Regulatory Commission (APERC) tariff schedules will be implemented in Phase 4.
4. **Decoupled UI:** In Phase 1, `index.html` remains byte-for-byte preserved. Live JavaScript fetching from the `/api` endpoints will be connected in Phase 2.
