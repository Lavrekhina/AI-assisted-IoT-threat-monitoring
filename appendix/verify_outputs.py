#!/usr/bin/env python3
"""See which expected output files exist after you run the pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    checks = [
        ("features", ROOT / "artifacts" / "features.parquet"),
        ("plots html", list((ROOT / "artifacts" / "plots").glob("*.html"))),
        ("ai eval", ROOT / "artifacts" / "ai_eval" / "roc_curve.html"),
        ("floorplan", ROOT / "artifacts" / "floorplan" / "floorplan_risk_map.html"),
        ("trends", ROOT / "artifacts" / "trends" / "decomposition_event_volume.html"),
        ("operational", ROOT / "artifacts" / "operational" / "device_detection_milestones.csv"),
        ("risk matrix", ROOT / "artifacts" / "risk_matrix" / "heatmap_compromise_rate.html"),
        ("excel starter", ROOT / "artifacts" / "excel" / "iot_telemetry_pivot_starter.xlsx"),
        ("r outputs", ROOT / "artifacts" / "r" / "rf_metrics.csv"),
        ("appendix text", ROOT / "artifacts" / "appendix_code.txt"),
    ]

    missing = []
    for label, path_or_list in checks:
        if isinstance(path_or_list, list):
            ok = len(path_or_list) > 0
            p = f"{len(path_or_list)} files" if ok else "no files"
        else:
            ok = path_or_list.is_file()
            p = str(path_or_list.relative_to(ROOT)) if ok else "missing"
        mark = "ok " if ok else "no "
        line = f"{mark}  {label}  {p}"
        print(line)
        if not ok:
            missing.append(label)

    if missing:
        print("Run the README steps for", ", ".join(missing))
    else:
        print("Looks complete. You can move on to the write up and Excel polish")


if __name__ == "__main__":
    main()
