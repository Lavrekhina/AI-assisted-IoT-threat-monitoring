#!/usr/bin/env python3
"""
Run the full analysis pipeline from the project root in the right order.
Turn the venv on first. For options run  python run_all.py -h
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def run_step(name: str, args: list[str]) -> None:
    print()
    print(name)
    r = subprocess.run([PY, *args], cwd=ROOT, check=False)
    if r.returncode != 0:
        raise SystemExit(f"Stopped because {name} failed with code {r.returncode}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run all IoT analysis steps in order")
    ap.add_argument("--skip-r", action="store_true", help="Do not run the R script")
    ap.add_argument("--skip-excel", action="store_true", help="Do not run the Excel export")
    args = ap.parse_args()

    steps: list[tuple[str, list[str]]] = [
        ("00 profile csv", [str(ROOT / "python" / "00_csv_profile.py")]),
        ("01 features", [str(ROOT / "python" / "01_prepare_features.py")]),
        ("02 time series plots", [str(ROOT / "python" / "02_time_series_patterns.py")]),
        ("05 statsmodels trends", [str(ROOT / "python" / "05_statsmodels_trends.py")]),
        ("03 AI evaluation", [str(ROOT / "python" / "03_ai_evaluation.py")]),
        ("04 floorplan", [str(ROOT / "python" / "04_floorplan_risk_map.py")]),
        ("06 operational delay", [str(ROOT / "python" / "06_operational_delay.py")]),
        ("07 risk matrix", [str(ROOT / "python" / "07_risk_matrix.py")]),
    ]
    if not args.skip_excel:
        steps.append(("08 excel starter", [str(ROOT / "python" / "08_excel_starter_workbook.py")]))

    for name, cmd in steps:
        run_step(name, cmd)

    if not args.skip_r:
        rscript = shutil.which("Rscript")
        if not rscript:
            print()
            print("R not found on PATH. Install R or add --skip-r. Skipping R step.")
        else:
            print()
            print("R modelling and clustering")
            r = subprocess.run(
                [rscript, str(ROOT / "r" / "01_modelling_clustering.R")],
                cwd=ROOT,
                check=False,
            )
            if r.returncode != 0:
                raise SystemExit(f"R step failed with code {r.returncode}")

    print()
    print("appendix text bundle")
    p = subprocess.run(
        [PY, str(ROOT / "appendix" / "build_appendix_code.py")],
        cwd=ROOT,
        check=False,
    )
    if p.returncode != 0:
        print("appendix build failed you can run appendix/build_appendix_code.py by hand")

    print()
    print("Done. Check outputs with  python appendix/verify_outputs.py")


if __name__ == "__main__":
    main()
