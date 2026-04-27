#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    df = df.copy()
    df["ts"] = ts
    df["date"] = ts.dt.date
    df["hour"] = ts.dt.hour
    df["minute"] = ts.dt.minute
    df["day_of_week"] = ts.dt.dayofweek  # 0=Mon
    df["dow_name"] = ts.dt.day_name()

    # Cyclical encoding (for models + clustering)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7.0)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7.0)
    return df


def clean_and_impute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Normalize obvious types
    numeric_cols = [
        "bytes_in",
        "bytes_out",
        "packets",
        "cpu_load_pct",
        "memory_usage_pct",
        "battery_level_pct",
        "temperature_c",
        "anomaly_score",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in ["floor", "port", "ground_truth_compromise"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    for c in ["signed_firmware", "identity_mismatch"]:
        if c in df.columns:
            # In CSV, booleans are True/False; coerce gracefully
            df[c] = df[c].astype("string").str.lower().map({"true": True, "false": False}).astype("boolean")

    # Basic plausibility constraints (treat implausible as missing)
    if "cpu_load_pct" in df.columns:
        df.loc[(df["cpu_load_pct"] < 0) | (df["cpu_load_pct"] > 100), "cpu_load_pct"] = np.nan
    if "memory_usage_pct" in df.columns:
        df.loc[(df["memory_usage_pct"] < 0) | (df["memory_usage_pct"] > 100), "memory_usage_pct"] = np.nan
    if "battery_level_pct" in df.columns:
        df.loc[(df["battery_level_pct"] < 0) | (df["battery_level_pct"] > 100), "battery_level_pct"] = np.nan
    if "temperature_c" in df.columns:
        df.loc[(df["temperature_c"] < -10) | (df["temperature_c"] > 60), "temperature_c"] = np.nan
    if "anomaly_score" in df.columns:
        df.loc[(df["anomaly_score"] < 0) | (df["anomaly_score"] > 1), "anomaly_score"] = np.nan

    # Device-level smoothing/imputation for telemetry that should be continuous-ish
    df = df.sort_values(["device_id", "timestamp_utc"])
    for c in ["cpu_load_pct", "memory_usage_pct", "battery_level_pct", "temperature_c"]:
        if c not in df.columns:
            continue
        # Median filter via rolling median, then fill gaps using forward/backward fill within device
        df[c + "_roll_med"] = (
            df.groupby("device_id")[c]
            .transform(lambda s: s.rolling(5, center=True, min_periods=1).median())
        )
        df[c] = df[c].fillna(df[c + "_roll_med"])
        df[c] = df.groupby("device_id")[c].transform(lambda s: s.ffill().bfill())

    # Network stats: fill missing with 0 only if clearly a count field; otherwise keep as NA
    for c in ["bytes_in", "bytes_out", "packets"]:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    # Feature engineering: ratios + logs (robust for spikes)
    eps = 1e-6
    if {"bytes_out", "bytes_in"}.issubset(df.columns):
        df["out_in_ratio"] = (df["bytes_out"] + eps) / (df["bytes_in"] + eps)
    if {"bytes_out", "packets"}.issubset(df.columns):
        df["bytes_out_per_packet"] = (df["bytes_out"] + eps) / (df["packets"] + eps)
    if "bytes_out" in df.columns:
        df["log_bytes_out"] = np.log1p(df["bytes_out"])
    if "bytes_in" in df.columns:
        df["log_bytes_in"] = np.log1p(df["bytes_in"])
    if "packets" in df.columns:
        df["log_packets"] = np.log1p(df["packets"])

    return df


def add_outlier_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Per-device robust z-score (median/MAD) to capture spikes/drifts
    def robust_z(s: pd.Series) -> pd.Series:
        med = s.median()
        mad = (s - med).abs().median()
        denom = (1.4826 * mad) if mad and mad > 0 else np.nan
        return (s - med) / denom

    for c in ["bytes_out", "bytes_in", "packets", "out_in_ratio", "bytes_out_per_packet"]:
        if c not in df.columns:
            continue
        z = df.groupby("device_id")[c].transform(robust_z)
        df[f"{c}_rz"] = z
        df[f"{c}_spike"] = (z.abs() >= 4).fillna(False)

    # Protocol misuse heuristic (simple, explainable rules)
    # - unexpected high outbound via plain HTTP on sensitive devices
    # - suspicious ports on badge scanners
    df["protocol_misuse_flag"] = False
    if {"protocol", "device_type", "port"}.issubset(df.columns):
        is_badge = df["device_type"].astype("string").str.lower().eq("badge_scanner")
        df.loc[is_badge & ~df["port"].isin([443, 1812]), "protocol_misuse_flag"] = True

        is_http = df["protocol"].astype("string").str.upper().eq("HTTP")
        df.loc[is_http & (df.get("bytes_out", 0) > df["bytes_out"].quantile(0.95)), "protocol_misuse_flag"] = True

    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Prepare features for IoT threat monitoring story.")
    ap.add_argument("--csv", required=True, help="Path to IoT_smart_building_telemetry.csv")
    ap.add_argument("--out", default="artifacts/features.parquet", help="Output parquet path")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.csv)
    df = add_time_features(df)
    df = clean_and_impute(df)
    df = add_outlier_flags(df)

    # Convenience: binary label
    df["y_compromise"] = df["ground_truth_compromise"].astype("Int64").fillna(0).astype(int)

    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()

