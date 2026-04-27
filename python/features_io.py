"""Resolve features.parquet or features.csv and load a DataFrame (shared by step scripts)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_features_path(features_arg: str) -> Path:
    """
    Find features.parquet or fall back to same-stem .csv. Also look under
    PROJECT_ROOT so a cwd of python/ still finds ../artifacts/...
    """
    path = Path(features_arg)
    candidates: list[Path] = [path, PROJECT_ROOT / path]
    if path.suffix.lower() in (".parquet", ".pq"):
        for base in (path, PROJECT_ROOT / path):
            if base.suffix:
                candidates.append(base.with_suffix(".csv"))
    seen: set[str] = set()
    uniq: list[Path] = []
    for c in candidates:
        k = str(c.resolve())
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    for c in uniq:
        if c.is_file():
            return c
    tried = ", ".join(str(c) for c in uniq)
    raise FileNotFoundError(
        f"Feature table not found. Tried: {tried}. "
        "Run: python python/01_prepare_features.py (from the project root)."
    )


def read_features_dataframe(p: Path) -> pd.DataFrame:
    if p.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(p)
    return pd.read_csv(p)
