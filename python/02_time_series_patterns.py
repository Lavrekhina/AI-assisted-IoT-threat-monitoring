#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def plot_operational_rhythm(df: pd.DataFrame, out_dir: Path) -> None:
    # Building rhythm: events heatmap by day-of-week x hour (overall and by device type)
    base = (
        df.dropna(subset=["ts"])
        .groupby(["dow_name", "hour"], as_index=False)
        .size()
        .rename(columns={"size": "events"})
    )
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    base["dow_name"] = pd.Categorical(base["dow_name"], categories=dow_order, ordered=True)
    base = base.sort_values(["dow_name", "hour"])

    fig = px.density_heatmap(
        base,
        x="hour",
        y="dow_name",
        z="events",
        color_continuous_scale="Blues",
        title="Building operational rhythm (events by hour × day)",
    )
    fig.update_layout(margin=dict(l=40, r=20, t=60, b=40))
    fig.write_html(out_dir / "rhythm_events_heatmap.html")

    # Compromise rhythm overlay
    comp = df[df["y_compromise"] == 1]
    if len(comp) > 0:
        comp2 = (
            comp.dropna(subset=["ts"])
            .groupby(["dow_name", "hour"], as_index=False)
            .size()
            .rename(columns={"size": "comp_events"})
        )
        comp2["dow_name"] = pd.Categorical(comp2["dow_name"], categories=dow_order, ordered=True)
        fig2 = px.density_heatmap(
            comp2,
            x="hour",
            y="dow_name",
            z="comp_events",
            color_continuous_scale="Reds",
            title="Compromised events rhythm (hour × day)",
        )
        fig2.update_layout(margin=dict(l=40, r=20, t=60, b=40))
        fig2.write_html(out_dir / "rhythm_compromises_heatmap.html")


def plot_device_drifts(df: pd.DataFrame, out_dir: Path) -> None:
    # Example drift: bytes_out per device over time, highlighting spikes
    df = df.dropna(subset=["ts"]).copy()
    df["date_hour"] = df["ts"].dt.floor("H")
    agg = (
        df.groupby(["device_id", "device_type", "date_hour"], as_index=False)
        .agg(
            bytes_out=("bytes_out", "sum"),
            anomaly_score=("anomaly_score", "mean"),
            compromised=("y_compromise", "max"),
        )
    )
    # Keep top-N most outbound devices for a readable plot
    top_devices = agg.groupby("device_id")["bytes_out"].sum().sort_values(ascending=False).head(10).index
    agg = agg[agg["device_id"].isin(top_devices)]

    fig = px.line(
        agg,
        x="date_hour",
        y="bytes_out",
        color="device_id",
        facet_row="device_type",
        title="Top outbound devices — hourly bytes_out (spikes/drifts)",
    )
    fig.update_layout(margin=dict(l=40, r=20, t=60, b=40))
    fig.write_html(out_dir / "timeseries_top_outbound_devices.html")


def plot_anomaly_distributions(df: pd.DataFrame, out_dir: Path) -> None:
    # Density / histogram for anomaly score split by ground truth
    d = df[["anomaly_score", "y_compromise", "device_type"]].dropna(subset=["anomaly_score"]).copy()
    d["label"] = np.where(d["y_compromise"] == 1, "compromised", "safe")

    fig = px.histogram(
        d,
        x="anomaly_score",
        color="label",
        marginal="box",
        nbins=40,
        barmode="overlay",
        opacity=0.6,
        title="Anomaly-score distribution: safe vs compromised",
        color_discrete_map={"safe": "#2E86AB", "compromised": "#D64550"},
    )
    fig.update_layout(margin=dict(l=40, r=20, t=60, b=40))
    fig.write_html(out_dir / "anomaly_score_hist_safe_vs_comp.html")

    # By device type (small multiples)
    fig2 = px.histogram(
        d,
        x="anomaly_score",
        color="label",
        facet_col="device_type",
        facet_col_wrap=3,
        nbins=30,
        barmode="overlay",
        opacity=0.6,
        title="Anomaly-score distribution by device type",
        color_discrete_map={"safe": "#2E86AB", "compromised": "#D64550"},
    )
    fig2.update_layout(margin=dict(l=40, r=20, t=60, b=40))
    fig2.write_html(out_dir / "anomaly_score_hist_by_device_type.html")


def main() -> None:
    ap = argparse.ArgumentParser(description="Time-series patterns & narrative plots.")
    ap.add_argument("--features", default="artifacts/features.parquet", help="Parquet from 01_prepare_features.py")
    ap.add_argument("--out-dir", default="artifacts/plots", help="Output directory for html plots")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(args.features)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")

    plot_operational_rhythm(df, out_dir)
    plot_device_drifts(df, out_dir)
    plot_anomaly_distributions(df, out_dir)
    print(f"Wrote plots to {out_dir}")


if __name__ == "__main__":
    main()

