# Mini-project #5 — AI-assisted IoT threat monitoring

This repo contains a **reproducible Python + R workflow** for analyzing `IoT_smart_building_telemetry.csv` and building a visual narrative about **device behavior, anomalies, and operational risk**.

## Repository layout

- `data/`
  - (optional) place datasets here if you prefer (current dataset is in repo root)
- `python/`
  - `00_csv_profile.py`: fast dataset profiling (no pandas)
  - `01_prepare_features.py`: cleaning + time features + outlier flags (writes `artifacts/features.parquet`)
  - `02_time_series_patterns.py`: rhythm / periodicity / spikes (writes plots to `artifacts/plots/`)
  - `05_statsmodels_trends.py`: **statsmodels** STL / OLS trend + HP filter on resampled series (`artifacts/trends/`)
  - `03_ai_evaluation.py`: confusion matrix, ROC, calibration, threshold trade-offs
  - `04_floorplan_risk_map.py`: floorplan-like risk maps by building/floor/room
  - `06_operational_delay.py`: AI alert vs manual-rule **proxy** delays (see script docstring; `artifacts/operational/`)
  - `07_risk_matrix.py`: **device type × firmware** risk table + heatmaps (`artifacts/risk_matrix/`)
  - `08_excel_starter_workbook.py`: starter **.xlsx** for PivotTables + KPI summary (`artifacts/excel/`, needs `openpyxl`)
- `design/`
  - `workflow.mermaid`: **decision flow** (device event → AI → analyst → verdict) for Mermaid Live / report
- `r/`
  - `01_modelling_clustering.R`: predictive modelling + feature importance + clustering
- `artifacts/`
  - generated outputs (created by scripts)

## Setup

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run order (step-by-step)

1) Quick profiling (works without pandas):

```bash
python python/00_csv_profile.py --csv IoT_smart_building_telemetry.csv
```

2) Build cleaned feature table:

```bash
python python/01_prepare_features.py --csv IoT_smart_building_telemetry.csv
```

3) Create “operational rhythm” + time-series plots:

```bash
python python/02_time_series_patterns.py --features artifacts/features.parquet
```

4) Statsmodels trend / seasonal analysis (required by brief):

```bash
python python/05_statsmodels_trends.py --features artifacts/features.parquet
```

5) Evaluate AI anomaly score as a detector:

```bash
python python/03_ai_evaluation.py --features artifacts/features.parquet
```

6) Produce floorplan-like risk maps:

```bash
python python/04_floorplan_risk_map.py --features artifacts/features.parquet
```

7) Operational delay (AI vs **manual-monitoring proxy**; document assumptions in your report):

```bash
python python/06_operational_delay.py --features artifacts/features.parquet --ai-threshold 0.5
```

8) Risk matrix (patching / monitoring priorities):

```bash
python python/07_risk_matrix.py --features artifacts/features.parquet
```

9) (Optional) Starter Excel file for PivotTables + KPIs (run 03 and 06 first to fill K_summary):

```bash
python python/08_excel_starter_workbook.py --features artifacts/features.parquet
```

10) Run R modelling + clustering:

```bash
Rscript r/01_modelling_clustering.R artifacts/features.parquet
```

## Excel deliverables (PivotTables + KPIs)

Use the feature table produced in step (2) and create PivotTables/KPIs:

- **Pivot dimensions**: `device_type`, `building`, `floor`, `room`, `day_of_week`, `hour`
- **Measures**: events, compromised events, median anomaly score, outbound bytes sum/median, false positives/negatives at threshold
- **KPI cards**: device count, compromised device count, precision/recall/F1 at chosen threshold(s), median detection delay (AI vs manual)

(A concrete “Excel build sheet” template is provided in `python/03_ai_evaluation.py` outputs as CSV summaries. Delay KPIs can be taken from `artifacts/operational/kpi_delay_summary.csv` — note the **proxy** definition for “manual” in `06_operational_delay.py`.)

## What to do next (non-code deliverables)

1. **Excel**: use `python/08_excel_starter_workbook.py` output as a base, add PivotTable + slicers on `data_for_pivot`, and refine KPIs.
2. **Visual narrative**: arrange exported Plotly HTML (or static screenshots) into your report: rhythm → AI evaluation → floor risk → delays → risk matrix.
3. **Workflow diagram**: start from `design/workflow.mermaid` — open in [Mermaid Live](https://mermaid.live) and export as PNG/SVG, or rebuild in PowerPoint.

