#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the chapter-3/4 thread-window dataset used by the predictor.

Input:
  data/processed/full_dataset.csv

Outputs:
  data/processed/thread_windows.csv
  data/processed/thread_windows_norm.csv
  data/processed/thread_feature_norm_meta.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


RAW_EVENT_COLS = [
    "cpu_cycles",
    "instructions",
    "cache_misses",
    "branch_instrs",
    "branch_misses",
    "L1_icache_miss",
    "L1_dcache_miss",
    "ITLB_misses",
    "L2_cache_miss",
    "DTLB_misses",
]

FEATURE_COLS = [
    "IPC",
    "MPKI_LLC",
    "MPKI_L1I",
    "MPKI_L1D",
    "MPKI_L2",
    "BrMPKI",
    "MPKI_TLB",
]

NORM_COLS = [f"{c}_norm" for c in FEATURE_COLS]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_full_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Cannot find input dataset: {path}")

    df = pd.read_csv(path)
    required = {"ts", "thread", "pid", "cpu", "LoadType", *RAW_EVENT_COLS}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns: {missing}")

    for col in ["ts", "pid", "cpu", *RAW_EVENT_COLS]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["ts", "thread", "pid", "cpu", "LoadType", *RAW_EVENT_COLS])
    return df


def minmax_clip_normalize(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = df.copy()
    rows = []
    for col in cols:
        s = out[col].replace([np.inf, -np.inf], np.nan)
        lo = float(s.quantile(0.01))
        hi = float(s.quantile(0.99))
        if not np.isfinite(lo):
            lo = float(s.min())
        if not np.isfinite(hi):
            hi = float(s.max())
        if hi <= lo:
            hi = lo + 1e-9

        clipped = s.clip(lo, hi)
        norm_col = f"{col}_norm"
        out[norm_col] = ((clipped - lo) / (hi - lo)).clip(0.0, 1.0)
        rows.append({"feature": col, "clip_min": lo, "clip_max": hi})
    return out, pd.DataFrame(rows)


def add_topdown_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["S_FE"] = 0.75 * out["BrMPKI_norm"] + 0.25 * out["MPKI_L1I_norm"]
    out["S_BE_Core"] = 0.80 * out["IPC_norm"] + 0.20 * (1.0 - out["MPKI_LLC_norm"])
    out["S_BE_Mem"] = 0.80 * out["MPKI_LLC_norm"] + 0.20 * out["MPKI_TLB_norm"]

    # Tie priority follows the thesis: BE-Mem > BE-Core > FE-Bound.
    labels = []
    for fe, core, mem in out[["S_FE", "S_BE_Core", "S_BE_Mem"]].itertuples(index=False):
        if mem >= core and mem >= fe:
            labels.append("BE-Mem")
        elif core >= fe:
            labels.append("BE-Core")
        else:
            labels.append("FE-Bound")
    out["state_label"] = labels
    return out


def build_windows(df: pd.DataFrame, window_ns: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["window_id"] = (df["ts"].astype("int64") // window_ns).astype("int64")
    df["thread"] = df["thread"].astype(str)
    df["LoadType"] = df["LoadType"].astype(str)
    df["thread_key"] = (
        df["LoadType"] + ":pid=" + df["pid"].astype("int64").astype(str) + ":" + df["thread"]
    )

    agg = {col: "sum" for col in RAW_EVENT_COLS}
    agg.update({"cpu": "first", "ts": "min", "thread": "first", "pid": "first"})
    win = (
        df.groupby(["LoadType", "thread_key", "window_id"], as_index=False)
        .agg(agg)
        .sort_values(["LoadType", "thread_key", "window_id"])
        .reset_index(drop=True)
    )

    eps = 1e-9
    inst_k = win["instructions"] / 1000.0 + eps
    win["IPC"] = win["instructions"] / (win["cpu_cycles"] + eps)
    win["MPKI_LLC"] = win["cache_misses"] / inst_k
    win["MPKI_L1I"] = win["L1_icache_miss"] / inst_k
    win["MPKI_L1D"] = win["L1_dcache_miss"] / inst_k
    win["MPKI_L2"] = win["L2_cache_miss"] / inst_k
    win["BrMPKI"] = win["branch_misses"] / inst_k
    win["MPKI_TLB"] = (win["ITLB_misses"] + win["DTLB_misses"]) / inst_k

    win = win.replace([np.inf, -np.inf], np.nan)
    win = win.dropna(subset=FEATURE_COLS)
    win = win[(win["instructions"] > 0) & (win["cpu_cycles"] > 0)]
    win = win.reset_index(drop=True)

    norm, meta = minmax_clip_normalize(win, FEATURE_COLS)
    norm = add_topdown_labels(norm)
    return win, norm, meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root() / "data" / "processed" / "full_dataset.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=project_root() / "data" / "processed",
    )
    parser.add_argument("--window-ms", type=float, default=100.0)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    window_ns = int(args.window_ms * 1_000_000)
    if window_ns <= 0:
        raise ValueError("--window-ms must be positive")

    df = load_full_dataset(args.input)
    raw_windows, norm_windows, meta = build_windows(df, window_ns)

    raw_out = args.out_dir / "thread_windows.csv"
    norm_out = args.out_dir / "thread_windows_norm.csv"
    meta_out = args.out_dir / "thread_feature_norm_meta.csv"

    raw_windows.to_csv(raw_out, index=False)
    norm_windows.to_csv(norm_out, index=False)
    meta.to_csv(meta_out, index=False)

    print(f"Input rows: {len(df)}")
    print(f"Thread-window rows: {len(norm_windows)}")
    print(f"Threads: {norm_windows['thread_key'].nunique()}")
    print("State label counts:")
    print(norm_windows["state_label"].value_counts().to_string())
    print(f"Saved: {raw_out}")
    print(f"Saved: {norm_out}")
    print(f"Saved: {meta_out}")


if __name__ == "__main__":
    main()
