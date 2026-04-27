# Mini-project 5 - AI-assisted IoT threat monitoring

This repo is a Python and R workflow for working with `IoT_smart_building_telemetry.csv` and for building a visual story about device behaviour, anomalies, and risk. Plotly exports use a white theme, clear fonts, fixed heights, and they load the Plotly library from the web so each file stays small. The long line you may still see inside the file is the chart payload in JSON. Open HTML in a real browser. Offline use needs a tweak in `python/plotly_report.py` to inline the library instead of the CDN.

`run_all.py` at the top level runs the full pipeline. Use it or run the steps by hand (below).

## What is in the repo

`data/` optional place for copies of the CSV the course gives you (the sample file may sit in the repo root).

`python/` scripts

- `00_csv_profile.py` profiles the CSV quickly without pandas
- `01_prepare_features.py` cleans data and adds time features writes `artifacts/features.parquet` and `artifacts/features.csv` for R
- `02_time_series_patterns.py` rhythm and spike plots in `artifacts/plots/`
- `05_statsmodels_trends.py` STL or OLS trends and HP filter in `artifacts/trends/`
- `03_ai_evaluation.py` ROC calibration confusion matrix in `artifacts/ai_eval/`
- `04_floorplan_risk_map.py` simple room layout maps in `artifacts/floorplan/`
- `06_operational_delay.py` AI versus manual proxy timing in `artifacts/operational/`
- `07_risk_matrix.py` device type and firmware tables in `artifacts/risk_matrix/`
- `08_excel_starter_workbook.py` builds a starter xlsx needs `openpyxl` in `artifacts/excel/`

`design/`

- `workflow.mermaid` decision flow for reports open in Mermaid Live if you want a PNG

`appendix/`

- `build_appendix_code.py` glue all Python and R into one text file for the report
- `check_imports.py` quick test that the venv has the main packages
- `verify_outputs.py` list which artifact files exist after a full run

`r/`

- `01_modelling_clustering.R` models and clustering

`artifacts/` created when you run scripts gitignored

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python appendix/check_imports.py
```

## Run everything at once

From the project folder with the venv on and the csv in place:

```bash
python run_all.py
```

This runs the Python steps in order, then R if it is on your PATH, then the appendix code bundle. If you have no R use `python run_all.py --skip-r`. If the Excel step breaks use `python run_all.py --skip-excel`. See `python run_all.py -h`.

## Run order

Run these from the repo folder. The csv and parquet paths use the usual default names so you do not need extra flags. Put `IoT_smart_building_telemetry.csv` in the same folder or pass paths as arguments where the script expects them (see each file).

Step 1 quick profiling

```bash
python python/00_csv_profile.py
```

Step 2 features

```bash
python python/01_prepare_features.py
```

Step 3 time series plots

```bash
python python/02_time_series_patterns.py
```

Step 4 statsmodels

```bash
python python/05_statsmodels_trends.py
```

Step 5 AI evaluation

```bash
python python/03_ai_evaluation.py
```

Step 6 floor map

```bash
python python/04_floorplan_risk_map.py
```

Step 7 delays

```bash
python python/06_operational_delay.py
```

Step 8 risk matrix

```bash
python python/07_risk_matrix.py
```

Step 9 optional Excel starter run 03 and 06 first so KPIs can fill in

```bash
python python/08_excel_starter_workbook.py
```

Step 10 R

```bash
Rscript r/01_modelling_clustering.R
```

## Excel part of the coursework

Use the feature table from step 2. Build pivots with rows and columns like `device_type` `building` `floor` `room` `day_of_week` `hour`. Values can be event counts sums of compromise flags median anomaly score and bytes out. KPI cards can list device counts compromised counts precision recall F1 at a chosen threshold and median delay from the operational script. CSV helpers sit in `artifacts/ai_eval/` and `artifacts/operational/kpi_delay_summary.csv` the manual side in that file is a proxy see the script docstring.

## After the code runs

Finish the Excel workbook with real pivot tables and cards. Lay out the story in your report using the HTML plots. Export the workflow from `design/workflow.mermaid` using mermaid dot live or redraw in PowerPoint.

If the brief wants all code in one appendix file, run `python appendix/build_appendix_code.py` and attach `artifacts/appendix_code.txt` or copy from it into your document.

To see if the pipeline left every output in place, run `python appendix/verify_outputs.py`.
