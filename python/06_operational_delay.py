#!/usr/bin/env python3
"""
Operational delay: compare first AI-based alert vs a manual-monitoring proxy.

The public CSV does not include real SOC "manual detection" timestamps. We define
a transparent proxy: first time per device where a human-driven rule would
typically fire (integrity/signature/identity/flagged behaviour). Report these
assumptions in your write-up; replace with real fields if you get them in class.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def manual_rule_mask(df: pd.DataFrame) -> pd.Series:
    """Proxy for 'ops notices something' without using ground_truth_compromise directly."""
    fin = df["firmware_integrity"].astype("string").str.strip().str.lower()
    bad_integrity = fin.notna() & (fin != "ok")

    if "identity_mismatch" in df.columns:
        ident = df["identity_mismatch"]
        if ident.dtype == object or str(ident.dtype) == "boolean":
            ident = ident.astype("string").str.lower().isin(["true", "1", "t", "yes"])
        else:
            ident = ident.fillna(0) != 0
    else:
        ident = pd.Series(False, index=df.index)

    if "signed_firmware" in df.columns:
        sf = df["signed_firmware"]
        if sf.dtype == object or str(sf.dtype) == "boolean":
            unsigned = sf.astype("string").str.lower().isin(["false", "0", "no", "f"])
        else:
            unsigned = ~sf.fillna(1).astype(bool)
    else:
        unsigned = pd.Series(False, index=df.index)

    if "protocol_misuse_flag" in df.columns:
        misuse = df["protocol_misuse_flag"]
        if misuse.dtype == object or str(misuse.dtype) == "boolean":
            misuse = misuse.fillna(False)
            if misuse.dtype == object:
                misuse = misuse.astype("string").str.lower().eq("true")
        misuse = misuse.astype(bool)
    else:
        misuse = pd.Series(False, index=df.index)

    return bad_integrity | ident | unsigned | misuse


def per_device_milestones(
    df: pd.DataFrame, ai_threshold: float
) -> pd.DataFrame:
    rows = []
    df = df.sort_values("ts")
    for dev, g in df.groupby("device_id", sort=False):
        g = g.reset_index(drop=True)
        t_comp = g.loc[g["y_compromise"] == 1, "ts"]
        if t_comp.empty:
            continue
        t_comp = pd.Timestamp(t_comp.min())
        t_ai = g.loc[g["anomaly_score"] >= ai_threshold, "ts"]
        t_ai = pd.Timestamp(t_ai.min()) if not t_ai.empty else pd.NaT
        man = g.loc[manual_rule_mask(g), "ts"]
        t_man = pd.Timestamp(man.min()) if not man.empty else pd.NaT

        d_type = g["device_type"].iloc[0] if "device_type" in g.columns else None
        bld = g["building"].iloc[0] if "building" in g.columns else None

        # Minutes from each signal to the first known compromise (positive = signalled before compromise)
        def minutes_signal_to_compromise(
            t_signal: pd.Timestamp, t_c: pd.Timestamp
        ) -> float | None:
            if t_signal is None or pd.isna(t_signal) or t_c is None or pd.isna(t_c):
                return None
            return float((t_c - t_signal).total_seconds() / 60.0)

        rows.append(
            {
                "device_id": dev,
                "device_type": d_type,
                "building": bld,
                "first_compromise_ts": t_comp,
                "first_ai_alert_ts": t_ai,
                "first_manual_proxy_ts": t_man,
                "minutes_from_ai_alert_to_first_compromise": minutes_signal_to_compromise(
                    t_ai, t_comp
                )
                if pd.notna(t_ai)
                else None,
                "minutes_from_manual_proxy_to_first_compromise": minutes_signal_to_compromise(
                    t_man, t_comp
                )
                if pd.notna(t_man)
                else None,
            }
        )
    return pd.DataFrame(rows)


def plot_timeline(m: pd.DataFrame, out_path: Path) -> None:
    if m.empty:
        return
    m = m.copy()
    m = m.sort_values("first_compromise_ts")
    # at most 20 devices for readability
    m = m.head(20)
    m["y"] = m["device_id"]
    # Long format for scatter
    points = []
    for _, r in m.iterrows():
        if pd.notna(r["first_ai_alert_ts"]):
            points.append(
                (r["device_id"], r["first_ai_alert_ts"], "AI alert (score≥thr)", r.get("device_type", ""))
            )
        if pd.notna(r["first_manual_proxy_ts"]):
            points.append(
                (r["device_id"], r["first_manual_proxy_ts"], "Manual rule proxy", r.get("device_type", ""))
            )
        points.append(
            (r["device_id"], r["first_compromise_ts"], "First label=compromised", r.get("device_type", ""))
        )
    if not points:
        return
    dfp = pd.DataFrame(points, columns=["device_id", "ts", "milestone", "device_type"])
    fig = px.scatter(
        dfp,
        x="ts",
        y="device_id",
        color="milestone",
        title="Detection milestones (per device) — up to 20 devices with compromise",
    )
    fig.update_layout(
        xaxis_title="Time (UTC)",
        margin=dict(l=40, r=20, t=60, b=40),
        legend_title_text="",
    )
    fig.write_html(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="AI vs manual-proxy detection timing for compromised devices.")
    ap.add_argument("--features", default="artifacts/features.parquet", help="Parquet from 01_prepare_features.py")
    ap.add_argument("--out-dir", default="artifacts/operational", help="Output directory")
    ap.add_argument("--ai-threshold", type=float, default=0.5, help="anomaly_score threshold for an AI 'alert'")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(args.features)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    if "y_compromise" not in df.columns:
        df["y_compromise"] = df.get("ground_truth_compromise", 0).fillna(0).astype(int)

    m = per_device_milestones(df, args.ai_threshold)
    m.to_csv(out_dir / "device_detection_milestones.csv", index=False)

    c_ai = "minutes_from_ai_alert_to_first_compromise"
    c_m = "minutes_from_manual_proxy_to_first_compromise"
    if not m.empty and m.get(c_ai) is not None and m[c_ai].notna().any():
        s = m[c_ai].dropna()
        s2 = m[c_m].dropna() if c_m in m.columns else pd.Series(dtype=float)
        kpi = pd.DataFrame(
            {
                "metric": [
                    "median_minutes_from_ai_alert_to_first_compromise",
                    "median_minutes_from_manual_proxy_to_first_compromise",
                    "n_compromised_devices",
                ],
                "value": [
                    float(s.median()) if len(s) else np.nan,
                    float(s2.median()) if len(s2) else np.nan,
                    float(len(m)),
                ],
            }
        )
        kpi.to_csv(out_dir / "kpi_delay_summary.csv", index=False)

    # Box compare
    if not m.empty:
        mlong = m.melt(
            id_vars=["device_id", "device_type"],
            value_vars=[c_ai, c_m] if c_m in m.columns else [c_ai],
            var_name="channel",
            value_name="lead_minutes",
        )
        mlong = mlong.dropna(subset=["lead_minutes"])
        if not mlong.empty:
            fig = px.box(
                mlong,
                x="channel",
                y="lead_minutes",
                color="channel",
                points="all",
                title="Lead time (minutes) from signal to first labelled compromise (same device)",
            )
            fig.add_hline(
                0, line_dash="dash", line_color="#999", annotation_text="0 = at compromise time; positive = before"
            )
            fig.write_html(out_dir / "delay_boxplot_ai_vs_manual.html")

    plot_timeline(m, out_dir / "detection_milestones_timeline.html")
    print(f"Wrote operational delay tables to {out_dir}")


if __name__ == "__main__":
    main()
