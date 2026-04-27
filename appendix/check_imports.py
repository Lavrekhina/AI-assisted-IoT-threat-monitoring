#!/usr/bin/env python3
"""Try importing the libraries the project needs. Run after pip install -r requirements.txt."""
from __future__ import annotations

MODULES = [
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "sklearn",
    "plotly",
    "pyarrow",
    "openpyxl",
    "bs4",
]


def main() -> None:
    failed = []
    for name in MODULES:
        try:
            __import__(name)
            print("ok   ", name)
        except ImportError as e:
            print("bad  ", name, str(e))
            failed.append(name)
    if failed:
        print("Fix with pip for", " ".join(failed))
    else:
        print("All main Python dependencies import cleanly")


if __name__ == "__main__":
    main()
