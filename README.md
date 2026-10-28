# ⚡ EnergyWatch — Smart Utility Consumption Dashboard

EnergyWatch is a household electricity monitoring and forecasting application designed to help users track power consumption (kWh), inspect historical trends, detect unusual load spikes, estimate electricity bills using verified regulatory tariffs, and view predictive consumption insights.

---

## 📌 Project Status: Working Full-Stack Prototype (~95% Milestone — Anomaly Detection & Alert Generation)

| Layer | Status | Implementation Details |
|---|---|---|
| **Frontend UI** | ✅ Fully Functional | Connected to live FastAPI endpoints; Chart.js graphs, filter chips, dynamic alerts, live ticking clock, ML forecast display, CSV import modal |
| **Backend API** | ✅ Operational | FastAPI application with CORS and lifespan database initialization |
| **Database** | ✅ Operational | SQLite (`data/energywatch.db`) via SQLAlchemy 2.1.4 |
| **Data Seeder** | ✅ Operational | Idempotent baseline seeder for simulated readings, alerts, and APERC tariff configurations |
| **CSV Import** | ✅ Operational | Validates columns/values, rejects invalid/duplicates, stores readings in SQLite, sample file included |
| **Anomaly Detection** | ✅ Operational | Statistical $Z$-score thresholding against hour-of-day baselines; automatic scan on CSV import & on-demand scan API |
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
├── index.html                  # Responsive dashboard with live clock, bill modal, ML forecast, CSV import, anomaly alerts
├── requirements.txt            # Pinned dependencies (FastAPI, scikit-learn, numpy, python-multipart)
├── .gitignore                  # Exclusion rules for venv, DB, secrets, and caches
├── README.md                   # Project documentation and developer guide
├── data/
│   ├── .gitkeep                # Git tracking stub for database folder
│   ├── meter_readings.csv      # Sample simulated meter readings CSV template (168 hourly rows)
│   └── energywatch.db          # SQLite database (auto-generated, untracked)
├── tests/
│   ├── test_bill_calculation.py# Unit & API test suite for APERC bill calculation (18 tests)
│   ├── test_forecasting.py     # Unit & API test suite for ML forecasting pipeline (43 tests)
│   ├── test_csv_import.py      # Unit & API test suite for CSV import & deduplication (18 tests)
│   ├── test_anomaly_detection.py# Unit & API test suite for automated anomaly detection (16 tests)
│   └── test_reports.py         # Unit & API test suite for reports, export & statement (13 tests)
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
    │   ├── forecasting.py      # Autoregressive ML forecasting pipeline (scikit-learn)
    │   ├── csv_import.py       # CSV validation, deduplication, and database import engine
    │   ├── anomaly_detection.py# Statistical Z-score anomaly detection & alert generation engine
    │   └── reports.py          # Daily/monthly aggregations, APERC bill integration, CSV export
    └── routers/
        ├── __init__.py         # Routers package marker
        ├── readings.py         # /api/readings (filters: today, yesterday, week, all; upload-csv)
        ├── metrics.py          # /api/metrics (usage summaries, estimated bill)
        ├── billing.py          # /api/bill-estimate (itemized APERC bill calculation)
        ├── consumption.py      # /api/consumption (7d, 30d, 3m trends)
        ├── forecast.py         # /api/forecast (ML predictions + evaluation metrics)
        ├── alerts.py           # /api/alerts (retrieval, acknowledge, reset, detect-anomalies)
        └── reports.py          # /api/reports (summary, export-csv, statement)
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
| `GET` | `/api/readings?filter=all` | All recent simulated meter readings (paginated to 50 latest) |
| `POST` | `/api/readings/upload-csv` | Upload and validate meter readings CSV file, reject duplicates, and insert valid records |
| `GET` | `/api/consumption?range=7d` | Consumption trend data (7-day series + forecast overlay) |
| `GET` | `/api/consumption?range=30d` | 30-day historical consumption series |
| `GET` | `/api/consumption?range=3m` | 3-month aggregated consumption series |
| `GET` | `/api/forecast` | Dynamic ML forecast (Gradient Boosting) with holdout MAE/RMSE and baseline comparisons |
| `GET` | `/api/alerts` | List unacknowledged anomaly alerts |
| `POST` | `/api/alerts/{id}/acknowledge` | Mark an alert as acknowledged in SQLite |
| `POST` | `/api/alerts/{id}/reset` | Re-arm an alert for demonstration testing |
| `POST` | `/api/alerts/detect-anomalies` | Run statistical Z-score anomaly scan across meter readings and generate persistent alerts |
| `GET` | `/api/reports/summary` | Generate daily/monthly consumption summaries and APERC bill estimates |
| `GET` | `/api/reports/export-csv` | Download filtered meter readings as an RFC-4180 CSV file |
| `GET` | `/api/reports/statement` | Formal energy statement data with APERC telescopic breakdown for printing/PDF |


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

## 📥 CSV Meter Readings Import

EnergyWatch supports importing external meter readings via CSV files through both the web dashboard modal and the REST API.

### 1. CSV Schema & Requirements

The CSV file must contain a header row with the following three required columns (case-insensitive, whitespace-trimmed):

| Column Name | Type | Description | Example |
|---|---|---|---|
| `timestamp` | Datetime / ISO-8601 String | Reading timestamp in standard ISO-8601 format (`YYYY-MM-DDTHH:MM:SS`), optimized for spreadsheet software (Excel, LibreOffice) | `2026-09-11T00:00:00` |
| `consumption_kwh` | Float (Decimal) | Energy consumed during the hourly interval in kilowatt-hours ($\text{kWh} \ge 0.0$) | `1.45` |
| `meter_id` | String | Alphanumeric identifier for the smart meter | `EW-2847-HH` |

#### Sample CSV File (`data/meter_readings.csv`)

A complete 7-day sample dataset is provided at [`data/meter_readings.csv`](file:///c:/Projects/EnergyWatrch(3-1)/data/meter_readings.csv):
* **Sample Period:** 7 consecutive days (**2026-09-11T00:00:00 to 2026-09-17T23:00:00**).
* **Reading Volume:** Exactly **168 hourly readings** ($7 \text{ days} \times 24 \text{ hours/day}$).
* **Consumption Profile:** Realistic simulated household patterns featuring low overnight baseload (0.21–0.50 kWh), morning wake-up pickup (1.18–2.10 kWh), daytime activity (1.20–2.65 kWh), and evening household peak (2.32–3.55 kWh).
* **Simulated Data Notice:** *All sample readings represent synthetic/simulated load profiles generated for software testing and validation. They do not represent real physical smart-meter telemetry.*

```csv
timestamp,consumption_kwh,meter_id
2026-09-11T00:00:00,0.39,EW-2847-HH
2026-09-11T01:00:00,0.23,EW-2847-HH
2026-09-11T02:00:00,0.24,EW-2847-HH
2026-09-11T03:00:00,0.21,EW-2847-HH
2026-09-11T04:00:00,0.36,EW-2847-HH
2026-09-11T05:00:00,0.50,EW-2847-HH
2026-09-11T06:00:00,1.20,EW-2847-HH
...
2026-09-17T23:00:00,0.90,EW-2847-HH
```

### 2. Validation & Deduplication Rules

* **Header Integrity:** Missing required columns trigger an immediate `400 Bad Request` with itemized missing column names.
* **Timestamp Parsing:** Flexibly parses standard ISO-8601 (`YYYY-MM-DDTHH:MM:SS`), ISO with UTC timezone, and SQL datetimes. Unparseable strings are rejected.
* **Value Integrity:** Negative consumption values ($\text{kWh} < 0$), non-numeric entries, `NaN`/`Infinity`, and empty meter IDs are rejected with row-level error reporting.
* **Intra-batch Deduplication:** If the uploaded CSV contains multiple records with the same `(meter_id, timestamp)` pair, only the first valid row is imported; duplicate rows are tallied and reported.
* **Database Deduplication:** Before insertion, rows are checked against existing database records matching `(meter_id, timestamp)`. Existing records are left intact without raising SQL constraint errors, corrupting data, or creating duplicate entries upon repeated uploads.
* **Domain Integrity:** All imported records are tagged with `source="simulated"` and checked against SQLite table constraints (`reading_type IN ('hourly', 'daily')`, `status IN ('Normal', 'High')`).

### 3. How to Import a CSV File

#### Option A: Web Dashboard Modal
1. Open the dashboard at [http://localhost:8000/](http://localhost:8000/).
2. In the **Recent Meter Readings** section, click the **📥 Import CSV** button in the header.
3. Select your `.csv` file via the file picker, drag and drop it into the upload box, or click **Use Sample (data/meter_readings.csv)** to automatically load the 168-reading template.
4. Click **Import Readings**. The modal validates the file, displays an import summary badge (imported count, duplicates skipped, invalid rows rejected), and refreshes the readings table.
5. Use the **All Recent** filter chip to inspect all newly imported records.

#### Option B: REST API Endpoint (`POST /api/readings/upload-csv`)
Upload directly via `curl` with multipart form data:
```bash
curl -X POST -F "file=@data/meter_readings.csv" http://localhost:8000/api/readings/upload-csv
```

Or send raw CSV content directly with `Content-Type: text/csv`:
```bash
curl -X POST -H "Content-Type: text/csv" --data-binary "@data/meter_readings.csv" http://localhost:8000/api/readings/upload-csv
```

**Sample API Response:**
```json
{
  "status": "success",
  "filename": "meter_readings.csv",
  "total_rows": 168,
  "imported_count": 168,
  "skipped_duplicates_count": 0,
  "rejected_invalid_count": 0,
  "message": "Successfully imported 168 meter readings.",
  "details": []
}
```

---

## 🚨 Automated Energy Anomaly Detection

EnergyWatch features an automated, statistical energy anomaly detection engine that identifies unusual consumption spikes, flags potential appliance faults or abnormal usage, and generates persistent alerts in SQLite.

### 1. Statistical Detection Method

For any given candidate hourly meter reading with consumption $x$ at hour $h$:

$$Z = \frac{x - \mu}{\sigma}$$

* **Stratified Hour-of-Day Baseline:** The engine calculates the mean ($\mu$) and sample standard deviation ($\sigma$) using prior historical readings for the same meter matching the exact same hour of the day ($N \ge 3$).
* **Fallback Scope:** If fewer than 3 historical readings exist for that specific hour, the engine falls back to the meter's overall hourly history ($N \ge 5$).
* **Dual Thresholding:** A reading is flagged as an anomaly if and only if **both** conditions are met:
  1. **Statistical Threshold:** $Z \ge Z_{\text{threshold}}$ (default: $2.5\sigma$, identifying values in the extreme upper tail).
  2. **Absolute Noise Floor:** $x \ge \text{min\_kwh\_threshold}$ (default: $4.5\text{ kWh}$). This prevents micro-fluctuations during low overnight baseload periods (e.g. 0.22 kWh rising to 0.45 kWh) from triggering false alarms.

### 2. Edge-Case Safety & Guardrails

* **Insufficient History ($N < 3$):** Safely marks readings as `"insufficient_history"` with `is_anomaly=False`. No false alarms or crashes occur when initializing new meters.
* **Zero Variance ($\sigma = 0$):** If historical readings are identical (e.g. perfectly flat synthetic baseline), the engine avoids division-by-zero errors. An anomaly is flagged only if usage spikes by $\ge 50\%$ above the constant baseline and exceeds the absolute threshold.
* **Dynamic Severity Scaling:**
  * **Warning:** $2.5 \le Z < 3.5$ and usage $< 8.0\text{ kWh}$.
  * **Critical:** $Z \ge 3.5$ or usage $\ge 8.0\text{ kWh}$ (indicating major appliance overdraw or continuous fault load).

### 3. Idempotent Alert Generation & Deduplication

* **Persistent SQLite Storage:** Anomalies are persisted as `Alert` records linked to the specific `reading_id` with contextual messages detailing the timestamp, spike volume, and baseline difference.
* **Duplicate Prevention:** Before creating an alert, the engine queries existing active alerts by `reading_id` and `alert_type`. Re-scanning or re-uploading an identical CSV file will **never** generate duplicate alerts.

### 4. How to Use Anomaly Detection

* **Automated via CSV Import:** Every valid batch uploaded through `POST /api/readings/upload-csv` or the dashboard modal is automatically evaluated for anomalies.
* **On-Demand Dashboard Scan:** Click the **Scan Anomalies** button in the Smart Alert card to run a real-time scan across all recent meter readings.
* **REST API Endpoint (`POST /api/alerts/detect-anomalies`):**
  ```bash
  curl -X POST "http://localhost:8000/api/alerts/detect-anomalies?z_threshold=2.5&min_kwh=4.5"
  ```

---

## 📊 Energy Reports & Data Export

EnergyWatch provides comprehensive consumption reporting, raw interval data export, and print-ready utility statements calculated directly from stored smart meter readings in SQLite.

### 1. Consumption Aggregations
* **Date Range Filtering:** Query intervals flexibly by `start_date` and `end_date` (ISO `YYYY-MM-DD` or datetime).
* **Multi-Meter Isolation:** Summaries filter strictly by `meter_id` (`EW-2847-HH`), ensuring readings from different meters are never conflated.
* **Daily Breakdown:** Aggregates hourly readings for each calendar day, identifying daily total consumption, reading count, peak hour, and peak load in kWh.
* **Monthly Summary:** Groups multi-month intervals into calendar months, tracking monthly usage, daily averages, and month-level APERC bill estimates.

### 2. Official APERC Tariff Integration
* Reuses `calculate_aperc_bill()` from `backend.services.billing` without duplicating tariff or calculation logic.
* Computes itemized energy charges across all 6 APERC FY 2026-27 telescopic slabs, fixed monthly charges (₹10/kW), and state electricity duty (6 paise/unit).
* Clearly marks all calculated amounts as informational estimates.

### 3. CSV Data Export
* **Endpoint:** `GET /api/reports/export-csv?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&meter_id=EW-2847-HH`
* **Format:** RFC-4180 compliant CSV stream with headers `timestamp`, `consumption_kwh`, `meter_id`, `voltage_v`, `current_a`, `power_factor`, `status`, `source`, `reading_type`.
* **Download Headers:** Emits `Content-Disposition: attachment; filename="energywatch_readings_<meter>_<start>_<end>.csv"`.

### 4. Printable Energy Statement (Save as PDF)
* **Print-Ready Layout:** Accessible via **Print Statement** button in the dashboard or `GET /api/reports/statement`.
* **Zero External Dependencies:** Built with pure HTML and responsive `@media print` CSS. Requires no heavy PDF rendering binaries.
* **Browser Integration:** Formats cleanly for the browser's native **Print / Save as PDF** dialog (Ctrl+P / Cmd+P), automatically stripping navigation bars, action buttons, and sidebars.
* **Statutory Compliance:** Prominently displays reference ID, meter metadata, billing dates, itemized slab breakdown, and official APERC disclaimers.

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

Run the complete 108-test suite (APERC bill calculation, ML forecasting pipeline, CSV import engine, anomaly detection, and energy reports) using Python's standard `unittest` runner:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Or run individual test suites:

```powershell
# Phase 3 APERC Billing calculation tests (18 tests)
.venv\Scripts\python.exe -m unittest tests/test_bill_calculation.py -v

# Phase 4 ML Forecasting pipeline & API tests (43 tests)
.venv\Scripts\python.exe -m unittest tests/test_forecasting.py -v

# CSV Import & Deduplication tests (18 tests)
.venv\Scripts\python.exe -m unittest tests/test_csv_import.py -v

# Automated Anomaly Detection & Alert tests (16 tests)
.venv\Scripts\python.exe -m unittest tests/test_anomaly_detection.py -v

# Energy Reports & Data Export tests (13 tests)
.venv\Scripts\python.exe -m unittest tests/test_reports.py -v
```

### Test Suite Coverage (108 Passed Checks):
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
3. **CSV Import Tests (18 tests):**
   * Empty CSV file rejection (`400 Bad Request` on empty string / whitespace)
   * Missing required header validation (`timestamp`, `consumption_kwh`, `meter_id`)
   * Empty/whitespace meter ID row-level rejection
   * Invalid/malformed timestamp format rejection
   * Negative consumption value rejection
   * All-invalid value file rejection (`400 Bad Request`)
   * Partial valid batch import (valid rows committed, invalid rows tallied and reported)
   * Intra-file deduplication (repeated timestamps in same file skipped)
   * Database deduplication (pre-existing SQLite readings skipped without duplicate rows or errors)
   * Repeated API upload deduplication (consecutive imports do not create duplicate database rows)
   * Flexible timestamp format parsing (ISO-8601 with/without timezone, SQL datetimes, calendar dates)
   * API upload endpoints (`POST /api/readings/upload-csv` multipart and raw text/csv fallback)
   * Query filter integration (`GET /api/readings?filter=all`)
   * Sample `data/meter_readings.csv` verification (strictly 168 rows, sequential ISO timestamps, domestic ranges, and night vs peak distribution)
4. **Anomaly Detection & Alert Tests (16 tests):**
   * Elementary statistical baseline calculations (mean, sample standard deviation, empty lists, zero variance)
   * Normal consumption evaluation within standard deviation limits
   * High consumption anomaly detection ($Z > 2.5$)
   * Absolute minimum noise floor enforcement (ignoring minor night baseload increases)
   * Insufficient historical data handling ($N < 3$ returns safe fallback)
   * Zero variance handling ($\sigma = 0$ avoids division by zero)
   * Historical-only baseline enforcement (strictly excludes candidate reading itself and future readings)
   * Multi-meter isolation in evaluation (readings from other meters never contaminate candidate baseline)
   * Multi-meter database scan isolation (independent baselines and meter-specific alert generation)
   * Idempotent alert generation (re-scanning same spike creates zero duplicate alerts in SQLite)
   * CSV upload integration (importing anomaly automatically triggers alert)
   * CSV repeated upload deduplication (re-uploading identical batch creates zero duplicate alerts)
   * API endpoint contracts (`POST /api/alerts/detect-anomalies`, `GET /api/alerts`, acknowledge/reset lifecycle)
5. **Energy Reports & Data Export Tests (13 tests):**
   * Consumption totals and daily average calculation across date boundaries
   * Strict date-range filtering (excluding readings outside start and end dates)
   * Multi-meter baseline and data isolation in reporting
   * Zero double-counting verification between hourly readings and daily summary records
   * Invalid date range validation (start date > end date raises HTTP 400)
   * Empty dataset handling (0 readings returns structured summary with zero values)
   * Official APERC billing service integration and slab charge parity
   * RFC-4180 CSV export formatting, custom headers, and row count tracking
   * Printable statement endpoint parity with report summary metrics
   * REST API contracts (`GET /api/reports/summary`, `GET /api/reports/export-csv`, `GET /api/reports/statement`)

---

## ⚠️ Data Disclaimer & Roadmap

* **Simulated Meter Data:** Readings represent simulated household patterns (Meter `EW-2847-HH`) used to validate full-stack data flow, API contracts, and user interactions.
* **Experimental Anomaly Detection:** The anomaly detection engine is calibrated for demonstration and software validation against simulated consumption patterns. It has not been trained or certified on physical smart-meter telemetry or real-world household power signatures.
* **Experimental ML Forecasting:** The machine learning pipeline is operational using simulated historical consumption. Because synthetic data lacks weather, temperature, occupancy, and solar factors, reported evaluation metrics reflect simulated behavior and do not claim real-world meter accuracy.
* **Informational Bill Estimates:** Bill calculation uses verified APERC domestic tariff rules, but is intended solely for consumption monitoring and financial budgeting. Official utility bills are issued exclusively by state distribution companies (APSPDCL, APEPDCL, APCPDCL).
* **Hardware Integration:** Real smart meter hardware integration (Modbus / MQTT / DLMS-COSEM) is scheduled for future physical deployment.
