#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)

from features_io import read_features_dataframe, resolve_features_path
from plotly_report import write_report_html


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def threshold_table(df: pd.DataFrame, thresholds: np.ndarray) -> pd.DataFrame:
    y = df["y_compromise"].astype(int).values
    s = df["anomaly_score"].astype(float).values

    rows = []
    for t in thresholds:
        yhat = (s >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
        prec, rec, f1, _ = precision_recall_fscore_support(y, yhat, average="binary", zero_division=0)
        rows.append(
            {
                "threshold": float(t),
                "tp": int(tp),
                "fp": int(fp),
                "tn": int(tn),
                "fn": int(fn),
                "precision": float(prec),
                "recall": float(rec),
                "f1": float(f1),
                "fpr": float(fp / (fp + tn) if (fp + tn) else 0.0),
                "fnr": float(fn / (fn + tp) if (fn + tp) else 0.0),
            }
        )
    return pd.DataFrame(rows)


def plot_confusion_matrix(df: pd.DataFrame, threshold: float, out_dir: Path) -> None:
    y = df["y_compromise"].astype(int).values
    s = df["anomaly_score"].astype(float).values
    yhat = (s >= threshold).astype(int)
    cm = confusion_matrix(y, yhat, labels=[0, 1])

    fig = px.imshow(
        cm,
        text_auto=True,
        x=["pred_safe", "pred_compromised"],
        y=["true_safe", "true_compromised"],
        color_continuous_scale="Blues",
        title=f"Confusion matrix at or above threshold {threshold:.2f}",
    )
    fig.update_layout(
        height=420,
        width=520,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    write_report_html(fig, out_dir / "confusion_matrix.html")


def plot_roc(df: pd.DataFrame, out_dir: Path) -> None:
    y = df["y_compromise"].astype(int).values
    s = df["anomaly_score"].astype(float).values
    fpr, tpr, thr = roc_curve(y, s)
    auc = roc_auc_score(y, s)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"ROC (AUC={auc:.3f})", line=dict(color="#2E86AB", width=3)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Chance", line=dict(color="#999999", dash="dash")))
    fig.update_layout(
        title="ROC curve. Anomaly score as compromise detector",
        xaxis_title="False Positive Rate",
        yaxis_title="True Positive Rate",
        xaxis=dict(range=[0, 1], showgrid=True),
        yaxis=dict(range=[0, 1], showgrid=True),
        height=520,
        width=560,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    write_report_html(fig, out_dir / "roc_curve.html")


def plot_calibration(df: pd.DataFrame, out_dir: Path) -> None:
    # Treat anomaly_score as a probability-like score (0..1). Calibration checks if it behaves like risk.
    y = df["y_compromise"].astype(int).values
    s = df["anomaly_score"].astype(float).values

    prob_true, prob_pred = calibration_curve(y, s, n_bins=10, strategy="quantile")
    brier = brier_score_loss(y, s)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prob_pred, y=prob_true, mode="lines+markers", name="Model", line=dict(color="#D64550", width=3)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfectly calibrated", line=dict(color="#999999", dash="dash")))
    fig.update_layout(
        title=f"Calibration curve quantile bins. Brier {brier:.3f}",
        xaxis_title="Mean predicted anomaly score",
        yaxis_title="Empirical compromise rate",
        xaxis=dict(range=[0, 1]),
        yaxis=dict(range=[0, 1]),
        height=520,
        width=560,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    write_report_html(fig, out_dir / "calibration_curve.html")


def export_excel_ready_summaries(df: pd.DataFrame, out_dir: Path) -> None:
    # Summaries intentionally simple for PivotTables / KPI cards.
    # You pick the threshold. We dump a grid so you can choose in Excel or here
    thresholds = np.round(np.linspace(0.05, 0.95, 19), 2)
    ttab = threshold_table(df.dropna(subset=["anomaly_score"]), thresholds)
    ttab.to_csv(out_dir / "threshold_tradeoffs.csv", index=False)

    # Event summaries by device/location/time
    base_dims = ["device_type", "building", "floor", "room", "day_of_week", "hour"]
    dims = [c for c in base_dims if c in df.columns]
    summary = (
        df.groupby(dims, dropna=False, as_index=False)
        .agg(
            events=("device_id", "size"),
            compromised_events=("y_compromise", "sum"),
            median_anomaly=("anomaly_score", "median"),
            bytes_out_sum=("bytes_out", "sum"),
        )
    )
    summary.to_csv(out_dir / "excel_pivot_source_events.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate anomaly score against ground truth. ROC confusion matrix calibration"
    )
    ap.add_argument(
        "--features",
        default="artifacts/features.parquet",
        help="Parquet or CSV from 01_prepare_features.py (CSV used if parquet missing)",
    )
    ap.add_argument("--out-dir", default="artifacts/ai_eval", help="Output directory")
    ap.add_argument("--threshold", type=float, default=0.80, help="Decision threshold for confusion matrix visual")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    p = resolve_features_path(args.features)
    print(f"Using features: {p}")
    df = read_features_dataframe(p)
    df = df.dropna(subset=["anomaly_score"]).copy()
    if df["y_compromise"].nunique() < 2:
        raise SystemExit(
            "AI evaluation needs both classes in y_compromise; the table has only one level after filtering."
        )

    y = df["y_compromise"].astype(int).values
    s = df["anomaly_score"].astype(float).values

    metrics = {
        "roc_auc": float(roc_auc_score(y, s)),
        "avg_precision": float(average_precision_score(y, s)),
        "brier": float(brier_score_loss(y, s)),
        "n_events": int(len(df)),
        "compromise_rate": float(df["y_compromise"].mean()),
        "threshold_for_cm": float(args.threshold),
    }
    pd.Series(metrics).to_json(out_dir / "metrics.json", indent=2)

    plot_roc(df, out_dir)
    plot_calibration(df, out_dir)
    plot_confusion_matrix(df, args.threshold, out_dir)
    export_excel_ready_summaries(df, out_dir)
    print(f"Wrote AI evaluation outputs to {out_dir}")


if __name__ == "__main__":
    main()

