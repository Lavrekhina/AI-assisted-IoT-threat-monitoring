#!/usr/bin/env python3
"""Join all project Python and R source into one text file for your report appendix."""
from __future__ import annotations

import argparse
from pathlib import Path

ORDER_PY = [
    "python/00_csv_profile.py",
    "python/01_prepare_features.py",
    "python/features_io.py",
    "python/plotly_report.py",
    "python/02_time_series_patterns.py",
    "python/03_ai_evaluation.py",
    "python/04_floorplan_risk_map.py",
    "python/05_statsmodels_trends.py",
    "python/06_operational_delay.py",
    "python/07_risk_matrix.py",
    "python/08_excel_starter_workbook.py",
]
ORDER_R = [
    "r/01_modelling_clustering.R",
]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build one text file with full code for the coursework appendix"
    )
    ap.add_argument(
        "out",
        nargs="?",
        default="artifacts/appendix_code.txt",
        help="output path default is under artifacts",
    )
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    parts = []
    for rel in ORDER_PY + ORDER_R:
        p = root / rel
        if not p.is_file():
            print(f"skip missing {rel}")
            continue
        rel_s = str(rel).replace("\\", "/")
        parts.append(f"file {rel_s}\n\n")
        parts.append(p.read_text(encoding="utf-8"))
        if not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.append("\n")

    out.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {out} ({len(''.join(parts))} bytes)")


if __name__ == "__main__":
    main()
