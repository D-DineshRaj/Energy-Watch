# ⚡ EnergyWatch — Smart Utility Consumption Dashboard

EnergyWatch is a household electricity monitoring and forecasting application designed to help users track power consumption (kWh), inspect historical trends, detect unusual load spikes, estimate electricity bills using verified regulatory tariffs, and view predictive consumption insights.

---

## 📌 Project Status: Working Full-Stack Prototype (~85% Milestone — ML Forecasting)

| Layer | Status | Implementation Details |
|---|---|---|
| **Frontend UI** | ✅ Fully Functional | Connected to live FastAPI endpoints; Chart.js graphs, filter chips, dynamic alerts, live ticking clock, ML forecast display |
| **Backend API** | ✅ Operational | FastAPI application with CORS and lifespan database initialization |
| **Database** | ✅ Operational | SQLite (`data/energywatch.db`) via SQLAlchemy 2.1.4 |
| **Data Seeder** | ✅ Operational | Idempotent baseline seeder for simulated readings, alerts, and APERC tariff configurations |
| **Alert Management** | ✅ Interactive | Full acknowledgement & reset cycle persisted in SQLite |
| **Bill Calculation** | ✅ Verified (Phase 3) | Official APERC LT-I(A) Domestic telescopic tariff with slab breakdown, fixed charges, and duty |
| **ML Forecasts** | ✅ Operational (Phase 4) | Gradient Boosting Regressor (shallow trees) with chronological 80/20 holdout evaluation & baseline benchmarking |
| **Meter Hardware** | ⚠️ Simulated Readings | Readings represent simulated household patterns for validation prior to smart meter integration |

---

## 🏛️ Official Electricity Tariff Schedule (Andhra Pradesh)

Bill calculations in Phase 3 strictly implement the official retail supply tariff order issued by the **Andhra Pradesh Electricity Regulatory Commission (APERC)** for domestic consumers.

* **Regulatory Authority:** Andhra Pradesh Electricity Regulatory Commission (APERC)
* **Official Website:** [https://aperc.gov.in/](https://aperc.gov.in/)
* **Consumer Category:** **LT Category-I(A): Domestic** (Residential Single-Phase / Three-Phase)
* **Order Reference:** APERC Retail Supply Tariff Order for FY 2026-27 (Order dated 25-March-2026, maintaining zero tariff hike for domestic consumers statewide)
* **Effective Date:** 01-April-2026 to 31-March-2027 (applicable across APSPDCL, APEPDCL, and APCPDCL)
* **Billing Structure:** **Telescopic Slab System** (units are billed progressively across designated tiers)

### Domestic Consumption Slabs & Rates (LT-I(A))

| Slab Index | Monthly Consumption Slab | Energy Charge (₹ / kWh) | Capacity in Tier | Maximum Slab Charge (₹) |
|---|---|---|---|---|
| **Slab 1** | 0 – 30 kWh | **₹1.90** | 30 units | ₹57.00 |
| **Slab 2** | 31 – 75 kWh | **₹3.00** | 45 units | ₹135.00 |
| **Slab 3** | 76 – 125 kWh | **₹4.50** | 50 units | ₹225.00 |
| **Slab 4** | 126 – 225 kWh | **₹6.00** | 100 units | ₹600.00 |
| **Slab 5** | 226 – 400 kWh | **₹8.75** | 175 units | ₹1,531.25 |
| **Slab 6** | Above 400 kWh | **₹9.75** | Unbounded | ₹9.75 per extra unit |

### Additional Bill Components & Statutory Levies

1. **Fixed Charges:** ₹10.00 per kW per month based on sanctioned contracted load (default: 1.0 kW single-phase domestic connection).
2. **Electricity Duty:** 6 paise per unit (**₹0.06 / kWh**) levied under Section 3(1) of the *Andhra Pradesh Electricity Duty Act, 1939* (as amended).
3. **Fuel Surcharge Adjustment (FSA / FPPPA):** Variable monthly/quarterly adjustment determined by APERC regulations; excluded (assumed ₹0.00/kWh baseline) in this estimate.
4. **Customer Charges & Meter Rent:** Nominal and itemized transparently in the breakdown.

### Step-by-Step Calculation Example (420.0 kWh Monthly Usage)

For the current monthly baseline consumption of **420.0 kWh** with **1.0 kW** sanctioned load:

```
• Slab 1 (0–30 units):     30 units  × ₹1.90 = ₹57.00
• Slab 2 (31–75 units):    45 units  × ₹3.00 = ₹135.00
• Slab 3 (76–125 units):   50 units  × ₹4.50 = ₹225.00
• Slab 4 (126–225 units): 100 units  × ₹6.00 = ₹600.00
• Slab 5 (226–400 units): 175 units  × ₹8.75 = ₹1,531.25
• Slab 6 (> 400 units):    20 units  × ₹9.75 = ₹195.00
────────────────────────────────────────────────────────
Subtotal Energy Charges:                      ₹2,743.25
Fixed Charges (1.0 kW × ₹10.00):                 ₹10.00
Electricity Duty (420 units × ₹0.06):            ₹25.20
────────────────────────────────────────────────────────
Grand Total Estimated Bill:                   ₹2,778.45  (Rounded: ₹2,778)
```

---

## 🏗️ Architecture

```
EnergyWatch/
├── index.html                  # Responsive dashboard with live clock, bill modal, and ML forecast card
├── requirements.txt            # Pinned dependencies including scikit-learn and numpy
├── .gitignore                  # Exclusion rules for venv, DB, secrets, and caches
├── README.md                   # Project documentation and developer guide
├── data/
│   ├── .gitkeep                # Git tracking stub for database folder
│   └── energywatch.db          # SQLite database (auto-generated, untracked)
├── tests/
│   ├── test_bill_calculation.py# Unit & API test suite for APERC bill calculation
│   └── test_forecasting.py     # Unit & API test suite for ML forecasting pipeline
└── backend/
    ├── __init__.py             # Backend package marker
    ├── main.py                 # FastAPI app, middleware, and route mounting
    ├── database.py             # Database engine and session management
    ├── models.py               # SQLAlchemy ORM models (Readings, Forecasts, Alerts, TariffConfig)
    ├── schemas.py              # Pydantic request and response schemas
    ├── seed_data.py            # Idempotent database population script
    ├── services/
    │   ├── __init__.py         # Services package marker
    │   ├── billing.py          # Pure Decimal APERC telescopic bill calculation engine
    │   └── forecasting.py      # Autoregressive ML forecasting pipeline (scikit-learn)
    └── routers/
        ├── __init__.py         # Routers package marker
        ├── readings.py         # /api/readings (today, yesterday, week)
        ├── metrics.py          # /api/metrics (usage summaries, estimated bill)
        ├── billing.py          # /api/bill-estimate (itemized APERC bill calculation)
        ├── consumption.py      # /api/consumption (7d, 30d, 3m trends)
        ├── forecast.py         # /api/forecast (ML predictions + evaluation metrics)
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
* **Live Dashboard:** [http://localhost:8000/](http://localhost:8000/)
* **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application status and database health check |
| `GET` | `/api/metrics` | Summary metrics card data including `estimated_bill_inr` |
| `GET` | `/api/bill-estimate` | Itemized APERC bill calculation (supports `consumption_kwh` & `sanctioned_load_kw` query params) |
| `GET` | `/api/readings?filter=today` | Hourly simulated meter readings for current day |
| `GET` | `/api/readings?filter=yesterday` | Hourly simulated readings for yesterday |
| `GET` | `/api/readings?filter=week` | Daily simulated totals for the past 7 days |
| `GET` | `/api/consumption?range=7d` | Consumption trend data (7-day series + forecast overlay) |
| `GET` | `/api/consumption?range=30d` | 30-day historical consumption series |
| `GET` | `/api/consumption?range=3m` | 3-month aggregated consumption series |
| `GET` | `/api/forecast` | Dynamic ML forecast (Gradient Boosting) with holdout MAE/RMSE and baseline comparisons |
| `GET` | `/api/alerts` | List unacknowledged anomaly alerts |
| `POST` | `/api/alerts/{id}/acknowledge` | Mark an alert as acknowledged in SQLite |
| `POST` | `/api/alerts/{id}/reset` | Re-arm an alert for demonstration testing |

### Sample Response: `GET /api/bill-estimate`

```json
{
  "consumption_kwh": 420.0,
  "sanctioned_load_kw": 1.0,
  "consumer_category": "LT Category-I(A): Domestic",
  "state": "Andhra Pradesh",
  "regulatory_authority": "Andhra Pradesh Electricity Regulatory Commission (APERC)",
  "tariff_order_ref": "APERC Retail Supply Tariff Order for FY 2026-27 (Order dated 25-03-2026)",
  "effective_date": "2026-04-01",
  "official_source_url": "https://aperc.gov.in/",
  "billing_method": "telescopic",
  "slabs_breakdown": [
    {
      "slab_index": 1,
      "slab_label": "0 – 30 kWh",
      "min_kwh": 0.0,
      "max_kwh": 30.0,
      "rate_per_kwh": 1.9,
      "units_billed": 30.0,
      "charge_inr": 57.0
    },
    {
      "slab_index": 2,
      "slab_label": "31 – 75 kWh",
      "min_kwh": 30.0,
      "max_kwh": 75.0,
      "rate_per_kwh": 3.0,
      "units_billed": 45.0,
      "charge_inr": 135.0
    },
    {
      "slab_index": 3,
      "slab_label": "76 – 125 kWh",
      "min_kwh": 75.0,
      "max_kwh": 125.0,
      "rate_per_kwh": 4.5,
      "units_billed": 50.0,
      "charge_inr": 225.0
    },
    {
      "slab_index": 4,
      "slab_label": "126 – 225 kWh",
      "min_kwh": 125.0,
      "max_kwh": 225.0,
      "rate_per_kwh": 6.0,
      "units_billed": 100.0,
      "charge_inr": 600.0
    },
    {
      "slab_index": 5,
      "slab_label": "226 – 400 kWh",
      "min_kwh": 225.0,
      "max_kwh": 400.0,
      "rate_per_kwh": 8.75,
      "units_billed": 175.0,
      "charge_inr": 1531.25
    },
    {
      "slab_index": 6,
      "slab_label": "Above 400 kWh",
      "min_kwh": 400.0,
      "max_kwh": null,
      "rate_per_kwh": 9.75,
      "units_billed": 20.0,
      "charge_inr": 195.0
    }
  ],
  "energy_charges_inr": 2743.25,
  "fixed_charges_inr": 10.0,
  "electricity_duty_inr": 25.2,
  "fpppa_charges_inr": 0.0,
  "customer_charges_inr": 0.0,
  "estimated_total_inr": 2778.45,
  "estimated_total_rounded_inr": 2778,
  "is_official_bill": false,
  "calculation_assumptions": [
    "Domestic category LT-I(A) telescopic energy tariff approved by APERC.",
    "Contracted load assumed at 1.0 kW single-phase domestic connection (₹10.00/kW/month).",
    "Electricity Duty calculated at statutory baseline rate of ₹0.06 (6 paise) per kWh.",
    "Fuel Surcharge Adjustment (FPPPA/FSA) assumed at ₹0.00/kWh as quarterly fluctuations are state-subsidized.",
    "Meter rent and localized municipal taxes are excluded unless specifically billed by the DISCOM."
  ],
  "limitations": "This is an estimated calculation for informational monitoring purposes only. Official electricity bills from APSPDCL/APEPDCL/APCPDCL may include seasonal fuel cost adjustments, solar net-metering credits, arrears, delayed payment surcharges, or localized municipal cess."
}
```

---

---

## 🤖 Machine Learning Forecasting Pipeline

EnergyWatch implements a disciplined, maintainable time-series forecasting pipeline using **Gradient Boosting Autoregression** with scikit-learn.

### 1. Model Choice & Rationale
* **Algorithm:** `GradientBoostingRegressor` (shallow trees: `max_depth=2`, `n_estimators=25`, `learning_rate=0.08`, `subsample=0.85`, `random_state=42`).
* **Why Gradient Boosting over ARIMA/Deep Learning:**
  * For compact interval datasets (30 daily simulated observations), complex neural networks or deep architectures overfit instantaneously.
  * Classical ARIMA requires strict stationarity differencing and can exhibit numerical instability on small sample sizes.
  * Constrained shallow-depth Gradient Boosting provides robust, monotonic regularization, natively ingests tabular autoregressive lags and calendar indicators, and executes deterministically with zero runtime latency.

### 2. Feature Formulation
For each observation at day $t$:
* **Lag 1 ($y_{t-1}$):** Consumption of the previous day.
* **Lag 2 ($y_{t-2}$):** Consumption from two days prior.
* **Rolling Mean 2:** $\frac{y_{t-1} + y_{t-2}}{2}$, smoothing high-frequency noise.
* **Day-of-Week:** Calendar indicator ($0=\text{Monday}, \dots, 6=\text{Sunday}$) capturing weekly cycle variations.

### 3. Chronological Train/Test Split (Zero Data Leakage)
To strictly avoid lookahead bias and data leakage:
* **Train Split (80%):** 22 observations chronologically from **2026-08-12 to 2026-09-02**.
* **Holdout Test Split (20%):** 6 observations chronologically from **2026-09-03 to 2026-09-08**.
* **Condition:** $\max(\text{train\_dates}) < \min(\text{test\_dates})$. No future or shuffle leakage.

### 4. Objective Evaluation & Baseline Benchmarking
Predictions on the holdout test set are benchmarked against a **Naive Persistence Baseline** ($y_t = y_{t-1}$):

| Model | MAE (Mean Absolute Error) | RMSE (Root Mean Squared Error) | Evaluation Split |
|---|---|---|---|
| **Gradient Boosting (Autoreg)** | **2.480 kWh** | **2.686 kWh** | Chronological 80/20 Holdout (6 test days) |
| **Naive Persistence Baseline (Lag-1)** | **1.133 kWh** | **1.583 kWh** | Chronological 80/20 Holdout (6 test days) |

> [!NOTE]
> **Data Science Insight:** The naive persistence baseline outperforms the machine learning model on this compact simulated holdout window (MAE 1.13 kWh vs 2.48 kWh). This confirms that with only 22 training observations on a relatively smooth synthetic series, complex models tend to revert toward the training mean and cannot reliably learn subtle day-of-week patterns without higher sample volume and exogenous weather inputs.

### 5. Multi-Step Recursive Forecasting
* Generates 3-day recursive forward projections (Tomorrow, Day 2, Day 3).
* Dynamically estimates prediction intervals using residual standard deviation:
  $$\text{Interval} = \hat{y} \pm 1.645 \times \sigma_{\text{residuals}}$$

---

## 🧪 Running Automated Tests

Run the complete 61-test suite (both APERC bill calculation and ML forecasting pipeline) using Python's standard `unittest` runner:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Or run individual test suites:

```powershell
# Phase 3 APERC Billing calculation tests (18 tests)
.venv\Scripts\python.exe -m unittest tests/test_bill_calculation.py -v

# Phase 4 ML Forecasting pipeline & API tests (43 tests)
.venv\Scripts\python.exe -m unittest tests/test_forecasting.py -v
```

### Test Suite Coverage (61 Passed Checks):
1. **APERC Billing Tests (18 tests):**
   * Zero consumption baseline (fixed charge only)
   * Telescopic slab tiers (30, 75, 125, 225, 400 kWh) and delta boundary checks ($\pm 0.1$)
   * Monetary half-up rounding precision
   * High-tier unbounded calculations (1,000 kWh)
   * Pydantic schema validation and 422 HTTP error contracts
2. **ML Forecasting Tests (43 tests):**
   * Input validation: insufficient data (< 14 samples), empty series, null values, negative consumption, NaN/inf, non-chronological dates, mismatched lengths
   * Autoregressive feature extraction: matrix shapes, lag alignment, rolling mean, weekday encoding
   * Chronological splitting: strict train/test date separation (zero leakage), partition ratios, sample minimums
   * Evaluation metrics: MAE, RMSE calculations against known synthetic targets
   * Full pipeline: schema keys, 3-day projection horizon, empirical prediction interval ordering
   * API endpoints: `/api/forecast` HTTP 200 contract, ML metadata fields, chart alignment
   * Regression tests: `/health`, `/api/metrics`, `/api/consumption?range=7d`, `/api/consumption?range=30d`, `/api/readings?filter=today`, `/api/readings?filter=week`, `/api/alerts`, `/api/bill-estimate`

---

## ⚠️ Data Disclaimer & Roadmap

* **Simulated Meter Data:** Readings represent simulated household patterns (Meter `EW-2847-HH`) used to validate full-stack data flow, API contracts, and user interactions.
* **Experimental ML Forecasting:** The machine learning pipeline is operational using simulated historical consumption. Because synthetic data lacks weather, temperature, occupancy, and solar factors, reported evaluation metrics reflect simulated behavior and do not claim real-world meter accuracy.
* **Informational Bill Estimates:** Bill calculation uses verified APERC domestic tariff rules, but is intended solely for consumption monitoring and financial budgeting. Official utility bills are issued exclusively by state distribution companies (APSPDCL, APEPDCL, APCPDCL).
* **Hardware Integration:** Real smart meter hardware integration (Modbus / MQTT / DLMS-COSEM) is scheduled for future physical deployment.
