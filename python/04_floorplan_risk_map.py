#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px

from features_io import read_features_dataframe, resolve_features_path
from plotly_report import write_report_html


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def make_floor_grid(df: pd.DataFrame) -> pd.DataFrame:
    """
    Creates a simple "floorplan-like" map:
    - x axis: room index within each (building, floor)
    - y axis: floor
    We keep it explainable and reproducible without needing real coordinates.
    """
    d = df.copy()
    for c in ["building", "room"]:
        d[c] = d[c].astype("string")

    # Aggregate risk per room
    room_agg = (
        d.groupby(["building", "floor", "room"], as_index=False)
        .agg(
            events=("device_id", "size"),
            devices=("device_id", "nunique"),
            compromised_events=("y_compromise", "sum"),
            compromise_rate=("y_compromise", "mean"),
            mean_anomaly=("anomaly_score", "mean"),
            bytes_out_sum=("bytes_out", "sum"),
        )
    )

    # Stable room order inside each building and floor
    def _room_index_within_floor(s: pd.Series) -> pd.Series:
        cat = pd.Categorical(s, categories=sorted(s.unique()), ordered=True)
        # Index must match the group so .transform() aligns; default RangeIndex(0, n) would only fill the first (building, floor) block.
        return pd.Series(cat.codes, index=s.index, dtype="float64")

    room_agg["x"] = room_agg.groupby(["building", "floor"])["room"].transform(_room_index_within_floor)
    room_agg["y"] = room_agg["floor"].astype("Int64")
    return room_agg


def plot_floorplan(room_agg: pd.DataFrame, out_dir: Path) -> None:
    # Dots size follows device count
    fig = px.scatter(
        room_agg,
        x="x",
        y="y",
        color="compromise_rate",
        size="devices",
        facet_col="building",
        color_continuous_scale="RdYlBu_r",
        hover_data=["room", "events", "devices", "compromised_events", "mean_anomaly", "bytes_out_sum"],
        title="Floorplan style risk map. Compromise rate by room. Dot size is device count",
    )
    fig.update_yaxes(autorange="reversed", title="floor")
    fig.update_xaxes(title="room index (ordered)")
    fig.update_layout(height=500, margin=dict(l=48, r=32, t=100, b=64))
    write_report_html(fig, out_dir / "floorplan_risk_map.html")

    fig2 = px.scatter(
        room_agg,
        x="x",
        y="y",
        color="mean_anomaly",
        size="devices",
        facet_col="building",
        color_continuous_scale="Viridis",
        hover_data=["room", "events", "devices", "compromised_events", "compromise_rate", "bytes_out_sum"],
        title="Floorplan style map. Mean anomaly score by room",
    )
    fig2.update_yaxes(autorange="reversed", title="floor")
    fig2.update_xaxes(title="room index (ordered)")
    fig2.update_layout(height=500, margin=dict(l=48, r=32, t=100, b=64))
    write_report_html(fig2, out_dir / "floorplan_mean_anomaly_map.html")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate floorplan style risk maps from feature table")
    ap.add_argument(
        "--features",
        default="artifacts/features.parquet",
        help="Parquet (or .csv) from 01_prepare_features.py; .csv is used if .parquet is missing",
    )
    ap.add_argument("--out-dir", default="artifacts/floorplan", help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    found = resolve_features_path(args.features)
    print(f"Using features: {found}")
    df = read_features_dataframe(found)
    room_agg = make_floor_grid(df)
    room_agg.to_csv(out_dir / "room_risk_table.csv", index=False)
    plot_floorplan(room_agg, out_dir)
    print(f"Wrote floorplan outputs to {out_dir}")


if __name__ == "__main__":
    main()

