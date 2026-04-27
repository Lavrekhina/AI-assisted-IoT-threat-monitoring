#!/usr/bin/env python3
"""Time-series trend and seasonal decomposition using statsmodels (assessment: trend analysis)."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import statsmodels.api as sm
from statsmodels.tsa.filters.hpfilter import hpfilter
from statsmodels.tsa.seasonal import STL


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def hourly_event_series(df: pd.DataFrame) -> pd.Series:
    d = df.dropna(subset=["ts"]).copy()
    d["h"] = d["ts"].dt.floor("H")
    return d.groupby("h").size().astype(float).rename("n_events").sort_index()


def daily_mean_anomaly(df: pd.DataFrame) -> pd.Series:
    d = df.dropna(subset=["ts", "anomaly_score"]).copy()
    d["day"] = d["ts"].dt.floor("D")
    return d.groupby("day")["anomaly_score"].mean().sort_index().astype(float).rename("mean_anomaly")


def regularize_hourly(s: pd.Series) -> pd.Series:
    s = s.sort_index()
    if s.empty:
        return s
    full = pd.date_range(s.index.min().floor("h"), s.index.max().floor("h"), freq="h")
    return s.reindex(full, fill_value=0.0).astype(float)


def regularize_daily(s: pd.Series) -> pd.Series:
    s = s.sort_index()
    if s.empty:
        return s
    full = pd.date_range(s.index.min().normalize(), s.index.max().normalize(), freq="D")
    return s.reindex(full).ffill().bfill().astype(float)


def ols_trend(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    t = np.arange(len(s), dtype=float)
    X = sm.add_constant(t)
    m = sm.OLS(s.values, X, missing="drop").fit()
    return pd.Series(m.fittedvalues, index=s.index, name="ols_trend")


def stl_decompose(s: pd.Series, period: int) -> pd.DataFrame | None:
    s = s.astype(float).ffill().bfill()
    if len(s) < 2 * period:
        return None
    try:
        r = STL(s, period=period, robust=True).fit()
    except Exception:
        return None
    return pd.DataFrame(
        {"observed": s, "trend": r.trend, "seasonal": r.seasonal, "resid": r.resid}
    )


def decompose_event_volume(s: pd.Series) -> tuple[pd.DataFrame, str]:
    s = regularize_hourly(s)
    if s.empty or len(s) < 3:
        return pd.DataFrame(), "insufficient data"
    if len(s) >= 48:
        d = stl_decompose(s, 24)
        if d is not None:
            return d, "STL(period=24) on hourly event counts (zeros for empty hours)"
    s_d = s.resample("D").sum()
    s_d = regularize_daily(s_d)
    if len(s_d) >= 14:
        d = stl_decompose(s_d, 7)
        if d is not None:
            return d, "STL(period=7) on daily event totals"
    s_f = s.astype(float)
    tr = ols_trend(s_f)
    return (
        pd.DataFrame({"observed": s_f, "trend": tr, "seasonal": np.nan, "resid": s_f - tr}),
        "Linear OLS trend on hourly counts (data too short for robust STL)",
    )


def decompose_anomaly(s: pd.Series) -> tuple[pd.DataFrame, str]:
    s = regularize_daily(s)
    if s.empty or len(s) < 3:
        return pd.DataFrame(), "insufficient data"
    if len(s) >= 14:
        d = stl_decompose(s, 7)
        if d is not None:
            return d, "STL(period=7) on daily mean anomaly score"
    tr = ols_trend(s)
    return (
        pd.DataFrame({"observed": s, "trend": tr, "seasonal": np.nan, "resid": s - tr}),
        "Linear OLS trend on daily mean anomaly (too few days for weekly STL)",
    )


def hp_cycle(y: pd.Series) -> pd.Series:
    y = y.dropna().astype(float)
    if len(y) < 4:
        return pd.Series(index=y.index, dtype=float)
    cyc, _t = hpfilter(y, lamb=1600)
    return pd.Series(cyc, index=y.index, name="hp_cycle")


def plot_components(decomp: pd.DataFrame, title: str, out_path: Path) -> None:
    if decomp.empty or "trend" not in decomp.columns:
        return
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Observed", "Trend", "Seasonal", "Residual / innovations"),
        vertical_spacing=0.05,
    )
    fig.add_trace(
        go.Scatter(x=decomp.index, y=decomp["observed"], name="observed", line=dict(color="#2E86AB")),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=decomp.index, y=decomp["trend"], name="trend", line=dict(color="#D64550")),
        row=2,
        col=1,
    )
    if "seasonal" in decomp.columns and decomp["seasonal"].notna().any():
        fig.add_trace(
            go.Scatter(x=decomp.index, y=decomp["seasonal"], name="seasonal", line=dict(color="#6B8E23")),
            row=3,
            col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(x=decomp.index, y=[0.0] * len(decomp), name="n/a", showlegend=False, line=dict(color="#ddd")),
            row=3,
            col=1,
        )
    fig.add_trace(
        go.Scatter(x=decomp.index, y=decomp["resid"], name="resid", line=dict(color="#6C757D")),
        row=4,
        col=1,
    )
    fig.update_layout(height=900, title_text=title, showlegend=True, margin=dict(l=40, r=20, t=80, b=40))
    fig.write_html(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Statsmodels: STL / OLS trend on resampled IoT event and anomaly time series."
    )
    ap.add_argument("--features", default="artifacts/features.parquet", help="Parquet from 01_prepare_features.py")
    ap.add_argument("--out-dir", default="artifacts/trends", help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(args.features)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"])

    h_events = hourly_event_series(df)
    h_events.to_csv(out_dir / "series_hourly_event_count.csv", index=True)
    de1, m1 = decompose_event_volume(h_events)
    plot_components(de1, f"Event volume — {m1}", out_dir / "decomposition_event_volume.html")
    if not de1.empty:
        de1.to_csv(out_dir / "decomposition_event_volume_components.csv", index=True)

    d_ano = daily_mean_anomaly(df)
    d_ano.to_csv(out_dir / "series_daily_mean_anomaly_score.csv", index=True)
    de2, m2 = decompose_anomaly(d_ano)
    plot_components(
        de2,
        f"Mean anomaly score — {m2}",
        out_dir / "decomposition_mean_anomaly_score.html",
    )
    if not de2.empty:
        de2.to_csv(out_dir / "decomposition_mean_anomaly_components.csv", index=True)

    if len(d_ano) >= 6:
        s_d = regularize_daily(d_ano)
        cyc = hp_cycle(s_d)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=s_d.index, y=s_d.values, name="daily mean score", line=dict(color="#2E86AB"))
        )
        fig.add_trace(go.Scatter(x=cyc.index, y=cyc.values, name="HP cycle", line=dict(color="#D64550")))
        fig.update_layout(
            title="Hodrick–Prescott filter on daily mean anomaly score (cycle component)",
            margin=dict(l=40, r=20, t=60, b=40),
        )
        fig.write_html(out_dir / "hpfilter_daily_mean_anomaly.html")
        pd.DataFrame({"daily_mean": s_d, "hp_cycle": cyc}).to_csv(out_dir / "hpfilter_daily_mean_anomaly.csv")

    print(f"Wrote statsmodels outputs to {out_dir} (events: {m1!r}, anomaly: {m2!r})")


if __name__ == "__main__":
    main()
