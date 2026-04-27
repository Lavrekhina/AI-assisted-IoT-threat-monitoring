#!/usr/bin/env python3
"""
Build a starter .xlsx for the assessment: one sheet of row-level fields for PivotTables,
optional KPI sheet if you have already run 03 + 06, and a short how-to sheet.
Requires: pip install openpyxl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows
except ImportError as e:  # pragma: no cover
    raise SystemExit("Install openpyxl: pip install openpyxl") from e


PIVOT_COLUMNS = [
    "timestamp_utc",
    "ts",
    "device_id",
    "device_type",
    "building",
    "floor",
    "room",
    "firmware_version",
    "protocol",
    "port",
    "event_type",
    "bytes_in",
    "bytes_out",
    "packets",
    "anomaly_score",
    "y_compromise",
    "ground_truth_compromise",
    "hour",
    "day_of_week",
    "dow_name",
    "compromise_type",
]


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_kpi_rows(
    ai_eval_dir: Path, op_dir: Path
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    mj = ai_eval_dir / "metrics.json"
    if mj.exists():
        with mj.open() as f:
            m = json.load(f)
        for k, v in m.items():
            rows.append((k, str(v)))
    else:
        rows.append(
            (
                "note",
                "Run 03_ai_evaluation.py to generate metrics.json, then re-run this script.",
            )
        )
    kpi = op_dir / "kpi_delay_summary.csv"
    if kpi.exists():
        d = pd.read_csv(kpi)
        for _, r in d.iterrows():
            rows.append((str(r.get("metric", "")), str(r.get("value", ""))))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Export starter Excel workbook for PivotTables + KPIs.")
    ap.add_argument("--features", default="artifacts/features.parquet")
    ap.add_argument("--out", default="artifacts/excel/iot_telemetry_pivot_starter.xlsx")
    ap.add_argument("--max-rows", type=int, default=0, help="0 = all rows")
    args = ap.parse_args()

    out_path = Path(args.out)
    _ensure_dir(out_path.parent)

    df = pd.read_parquet(args.features)
    use = [c for c in PIVOT_COLUMNS if c in df.columns]
    df = df[use]
    if args.max_rows and len(df) > args.max_rows:
        df = df.head(args.max_rows)

    wb = Workbook()
    ws = wb.active
    if ws is not None:
        ws.title = "data_for_pivot"
        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"

    whelp = wb.create_sheet("pivot_howto")
    lines = [
        "1. Select any cell on 'data_for_pivot', then Insert → PivotTable (Excel desktop).",
        "2. Rows/columns: device_type, building, floor, room, day_of_week, hour.",
        "3. Values: Count of device_id, Sum of y_compromise, Median of anomaly_score, Sum of bytes_out.",
        "4. Slicers: hour, device_type, compromise_type. Filter to high_anomaly = anomaly_score in top decile in a helper column if needed.",
        "5. KPI cards: on a new sheet, link to =COUNTA(unique device_id) from pivot or use formulas from K_summary.",
        "6. Optional: add threshold columns with =IF([@anomaly_score]>=$T$1,1,0) and compare to y_compromise for FP/FN.",
    ]
    for i, line in enumerate(lines, start=1):
        whelp.cell(row=i, column=1, value=line)

    wk = wb.create_sheet("K_summary")
    wk.cell(row=1, column=1, value="metric")
    wk.cell(row=1, column=2, value="value")
    kpi = load_kpi_rows(Path("artifacts/ai_eval"), Path("artifacts/operational"))
    for i, (a, b) in enumerate(kpi, start=2):
        wk.cell(row=i, column=1, value=a)
        wk.cell(row=i, column=2, value=b)

    wb.save(out_path)
    print(f"Wrote {out_path} ({len(df)} data rows, {len(use)} columns)")


if __name__ == "__main__":
    main()
