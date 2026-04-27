#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px


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

    # Stable room ordering per (building,floor)
    room_agg["room_order"] = room_agg.groupby(["building", "floor"])["room"].transform(
        lambda s: pd.Series(pd.Categorical(s, categories=sorted(s.unique()), ordered=True)).cat.codes
    )
    room_agg = room_agg.rename(columns={"room_order": "x"})
    room_agg["y"] = room_agg["floor"].astype("Int64")
    return room_agg


def plot_floorplan(room_agg: pd.DataFrame, out_dir: Path) -> None:
    # Risk heatmap sized by device density
    fig = px.scatter(
        room_agg,
        x="x",
        y="y",
        color="compromise_rate",
        size="devices",
        facet_col="building",
        color_continuous_scale="RdYlBu_r",
        hover_data=["room", "events", "devices", "compromised_events", "mean_anomaly", "bytes_out_sum"],
        title="Floorplan-like risk map: compromise rate by room (size = device density)",
    )
    fig.update_yaxes(autorange="reversed", title="floor")
    fig.update_xaxes(title="room index (ordered)")
    fig.update_layout(margin=dict(l=40, r=20, t=60, b=40))
    fig.write_html(out_dir / "floorplan_risk_map.html")

    fig2 = px.scatter(
        room_agg,
        x="x",
        y="y",
        color="mean_anomaly",
        size="devices",
        facet_col="building",
        color_continuous_scale="Viridis",
        hover_data=["room", "events", "devices", "compromised_events", "compromise_rate", "bytes_out_sum"],
        title="Floorplan-like map: mean anomaly score by room",
    )
    fig2.update_yaxes(autorange="reversed", title="floor")
    fig2.update_xaxes(title="room index (ordered)")
    fig2.update_layout(margin=dict(l=40, r=20, t=60, b=40))
    fig2.write_html(out_dir / "floorplan_mean_anomaly_map.html")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate floorplan-like risk maps from feature table.")
    ap.add_argument("--features", default="artifacts/features.parquet", help="Parquet from 01_prepare_features.py")
    ap.add_argument("--out-dir", default="artifacts/floorplan", help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(args.features)
    room_agg = make_floor_grid(df)
    room_agg.to_csv(out_dir / "room_risk_table.csv", index=False)
    plot_floorplan(room_agg, out_dir)
    print(f"Wrote floorplan outputs to {out_dir}")


if __name__ == "__main__":
    main()

