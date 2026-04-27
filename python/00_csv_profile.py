#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _parse_iso_z(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    # Expected: 2026-01-31T03:56:35Z
    try:
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts[:-1]).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _to_float(x: str) -> Optional[float]:
    if x is None:
        return None
    x = x.strip()
    if x == "":
        return None
    try:
        return float(x)
    except Exception:
        return None


def _to_int(x: str) -> Optional[int]:
    f = _to_float(x)
    if f is None or math.isnan(f):
        return None
    try:
        return int(f)
    except Exception:
        return None


@dataclass
class NumericSummary:
    n: int = 0
    n_missing: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min_v: float = float("inf")
    max_v: float = float("-inf")

    def add(self, v: Optional[float]) -> None:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            self.n_missing += 1
            return
        self.n += 1
        delta = v - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (v - self.mean)
        self.min_v = min(self.min_v, v)
        self.max_v = max(self.max_v, v)

    def var(self) -> Optional[float]:
        if self.n < 2:
            return None
        return self.m2 / (self.n - 1)

    def std(self) -> Optional[float]:
        v = self.var()
        return None if v is None else math.sqrt(v)


def profile_csv(path: Path) -> Dict[str, Any]:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")

        total = 0
        missing_by_col = Counter()
        n_by_col = Counter()
        categories = defaultdict(Counter)
        numeric_cols = {
            "bytes_in",
            "bytes_out",
            "packets",
            "cpu_load_pct",
            "memory_usage_pct",
            "battery_level_pct",
            "temperature_c",
            "anomaly_score",
        }
        numeric = {c: NumericSummary() for c in numeric_cols}

        compromise = 0
        timestamp_parse_fail = 0
        hours = Counter()
        dows = Counter()

        for row in reader:
            total += 1
            ts = _parse_iso_z(row.get("timestamp_utc", "") or "")
            if ts is None:
                timestamp_parse_fail += 1
            else:
                hours[ts.hour] += 1
                dows[ts.weekday()] += 1  # 0=Mon

            gt = _to_int(row.get("ground_truth_compromise", "") or "")
            if gt == 1:
                compromise += 1

            for col in reader.fieldnames:
                v = row.get(col, "")
                n_by_col[col] += 1
                if v is None or str(v).strip() == "":
                    missing_by_col[col] += 1
                    if col in numeric:
                        numeric[col].add(None)
                else:
                    if col in numeric:
                        numeric[col].add(_to_float(v))

            for cat_col in ["device_type", "protocol", "event_type", "compromise_type", "firmware_integrity"]:
                categories[cat_col][row.get(cat_col, "") or "(missing)"] += 1

    return {
        "path": str(path),
        "rows": total,
        "cols": list(n_by_col.keys()),
        "missing_rate_by_col": {
            c: (missing_by_col[c] / n_by_col[c] if n_by_col[c] else None) for c in n_by_col
        },
        "numeric_summary": {
            c: {
                "n": numeric[c].n,
                "n_missing": numeric[c].n_missing,
                "mean": numeric[c].mean if numeric[c].n else None,
                "std": numeric[c].std(),
                "min": None if numeric[c].min_v == float("inf") else numeric[c].min_v,
                "max": None if numeric[c].max_v == float("-inf") else numeric[c].max_v,
            }
            for c in numeric
        },
        "compromise_rate": (compromise / total if total else None),
        "timestamp_parse_fail": timestamp_parse_fail,
        "hour_hist": dict(sorted(hours.items())),
        "dow_hist": dict(sorted(dows.items())),
        "top_categories": {
            k: categories[k].most_common(10) for k in categories
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fast CSV profiler (no pandas).")
    ap.add_argument("--csv", required=True, help="Path to IoT_smart_building_telemetry.csv")
    args = ap.parse_args()

    p = Path(args.csv)
    prof = profile_csv(p)

    print(f"File: {prof['path']}")
    print(f"Rows: {prof['rows']}")
    print(f"Columns ({len(prof['cols'])}): {', '.join(prof['cols'])}")
    print(f"Compromise rate: {prof['compromise_rate']:.3f}" if prof["compromise_rate"] is not None else "Compromise rate: n/a")
    print(f"Timestamp parse failures: {prof['timestamp_parse_fail']}")

    print("\nMissingness (top 10):")
    miss_sorted = sorted(
        prof["missing_rate_by_col"].items(),
        key=lambda kv: (-kv[1] if kv[1] is not None else 0.0, kv[0]),
    )
    for col, rate in miss_sorted[:10]:
        print(f"- {col}: {rate:.1%}")

    print("\nNumeric summaries:")
    for col, s in sorted(prof["numeric_summary"].items()):
        print(
            f"- {col}: n={s['n']} missing={s['n_missing']} mean={_fmt(s['mean'])} std={_fmt(s['std'])} min={_fmt(s['min'])} max={_fmt(s['max'])}"
        )

    print("\nTop categories (top 10 each):")
    for cat, items in prof["top_categories"].items():
        print(f"- {cat}: " + ", ".join([f"{k} ({v})" for k, v in items]))


def _fmt(x: Any) -> str:
    if x is None:
        return "n/a"
    try:
        return f"{float(x):.3f}"
    except Exception:
        return str(x)


if __name__ == "__main__":
    main()

