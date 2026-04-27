#!/usr/bin/env python3
"""
Risk matrix. Device type and firmware against compromise rate and mean model score.

Use the CSV in Excel or the heatmaps in the report when you talk about patching and net splits.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from features_io import read_features_dataframe, resolve_features_path
from plotly_report import write_report_html


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def build_matrix(df: pd.DataFrame, min_events: int) -> pd.DataFrame:
    g = (
        df.groupby(["device_type", "firmware_version"], dropna=False, as_index=False)
        .agg(
            events=("device_id", "size"),
            n_devices=("device_id", "nunique"),
            compromised_events=("y_compromise", "sum"),
            mean_anomaly_score=("anomaly_score", "mean"),
        )
    )
    g["compromise_rate"] = g["compromised_events"] / g["events"].replace(0, float("nan"))
    g = g[g["events"] >= min_events].sort_values(["device_type", "firmware_version"])
    return g


def heatmap_figure(
    pivot: pd.DataFrame,
    pivot_n: pd.DataFrame,
    title: str,
    colorscale: str,
    zmin: float | None,
    zmax: float | None,
    cell_format: str,
) -> go.Figure:
    text: list[list[str]] = []
    for i in range(len(pivot.index)):
        row: list[str] = []
        for j in range(len(pivot.columns)):
            zv = pivot.iloc[i, j]
            nv = pivot_n.iloc[i, j] if pivot_n is not None and pivot_n.shape == pivot.shape else float("nan")
            if pd.isna(zv):
                row.append("")
            else:
                if cell_format == "pct":
                    label = f"{zv:.0%}"
                else:
                    label = f"{zv:.2f}"
                if pd.notna(nv):
                    label = f"{label}<br>(n={int(nv)})"
                row.append(label)
        text.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[str(c) for c in pivot.columns],
            y=[str(r) for r in pivot.index],
            text=text,
            texttemplate="%{text}",
            colorscale=colorscale,
            zmin=zmin,
            zmax=zmax,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Firmware",
        yaxis_title="Device type",
        height=520,
        width=720,
        margin=dict(l=64, r=32, t=100, b=120),
    )
    fig.update_xaxes(tickangle=-45)
    return fig


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Device type and firmware risk matrix. Event counts and rates"
    )
    ap.add_argument(
        "--features",
        default="artifacts/features.parquet",
        help="Parquet or CSV from 01_prepare_features.py (CSV used if parquet missing)",
    )
    ap.add_argument("--out-dir", default="artifacts/risk_matrix", help="Output directory")
    ap.add_argument(
        "--min-events",
        type=int,
        default=3,
        help="Do not show cells with fewer than this many events",
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    p = resolve_features_path(args.features)
    print(f"Using features: {p}")
    df = read_features_dataframe(p)
    if "y_compromise" not in df.columns:
        df["y_compromise"] = df.get("ground_truth_compromise", 0).fillna(0).astype(int)

    m = build_matrix(df, args.min_events)
    m.to_csv(out_dir / "device_type_firmware_risk_matrix.csv", index=False)

    if m.empty:
        print("No rows after min events filter. Try a lower min events value")
        return

    pr = m.pivot_table(index="device_type", columns="firmware_version", values="compromise_rate", aggfunc="first")
    pn = m.pivot_table(index="device_type", columns="firmware_version", values="events", aggfunc="first")
    fig1 = heatmap_figure(
        pr,
        pn,
        "Compromise rate by device type and firmware",
        "Reds",
        0.0,
        1.0,
        "pct",
    )
    write_report_html(fig1, out_dir / "heatmap_compromise_rate.html")

    ps = m.pivot_table(index="device_type", columns="firmware_version", values="mean_anomaly_score", aggfunc="first")
    fig2 = heatmap_figure(
        ps,
        pn,
        "Mean AI anomaly score by device type and firmware",
        "Viridis",
        0.0,
        1.0,
        "score",
    )
    write_report_html(fig2, out_dir / "heatmap_mean_anomaly_score.html")

    print(f"Wrote {len(m)} matrix rows to {out_dir}")


if __name__ == "__main__":
    main()
