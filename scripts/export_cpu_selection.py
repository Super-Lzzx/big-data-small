#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export readable CPU/core selection results from offline MAGM decisions.

Inputs:
  data/processed/magm_schedule.csv

Outputs:
  data/processed/final_cpu_selection.csv
  data/processed/final_core_pairs.csv
  results/scheduler/final_window_selection.csv
  results/scheduler/cpu_selection_summary.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def thread_label(row: pd.Series) -> str:
    return f"{row['thread']}({int(row['pid'])})"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root() / "data" / "processed" / "magm_schedule.csv",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Cannot find {args.input}; run offline_magm_scheduler.py first")

    df = pd.read_csv(args.input)
    required = {"LoadType", "window_id", "mode", "thread_key", "thread", "pid", "target_cpu"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{args.input} is missing required columns: {missing}")

    df = df.copy()
    df["target_cpu"] = df["target_cpu"].astype(int)
    df["physical_core"] = df["target_cpu"] // 2
    df["smt_slot"] = df["target_cpu"] % 2
    df["selected_thread"] = df.apply(thread_label, axis=1)
    df["pair_id"] = (
        df["LoadType"].astype(str)
        + ":"
        + df["window_id"].astype(str)
        + ":core"
        + df["physical_core"].astype(str)
    )

    selection_cols = [
        "LoadType",
        "window_id",
        "mode",
        "physical_core",
        "smt_slot",
        "target_cpu",
        "selected_thread",
        "thread_key",
        "paired_with",
        "score",
        "rho",
        "n_run",
    ]
    selection = df[selection_cols].sort_values(
        ["LoadType", "window_id", "physical_core", "smt_slot"]
    )

    pair_rows = []
    for (load_type, window_id, physical_core), grp in selection.groupby(
        ["LoadType", "window_id", "physical_core"],
        sort=True,
    ):
        slot0 = grp[grp["smt_slot"] == 0]
        slot1 = grp[grp["smt_slot"] == 1]
        row = {
            "LoadType": load_type,
            "window_id": int(window_id),
            "mode": grp["mode"].iloc[0],
            "physical_core": int(physical_core),
            "cpu_slot0": int(physical_core) * 2,
            "cpu_slot1": int(physical_core) * 2 + 1,
            "slot0_thread": slot0["selected_thread"].iloc[0] if not slot0.empty else "",
            "slot1_thread": slot1["selected_thread"].iloc[0] if not slot1.empty else "",
            "score": grp["score"].dropna().iloc[0] if grp["score"].notna().any() else "",
            "rho": grp["rho"].iloc[0],
            "n_run": int(grp["n_run"].iloc[0]),
        }
        pair_rows.append(row)
    core_pairs = pd.DataFrame(pair_rows)

    # "Final" here means the latest decision window in each workload.
    latest_keys = (
        selection.groupby("LoadType", as_index=False)["window_id"]
        .max()
        .rename(columns={"window_id": "latest_window_id"})
    )
    final_view = selection.merge(
        latest_keys,
        left_on=["LoadType", "window_id"],
        right_on=["LoadType", "latest_window_id"],
        how="inner",
    ).drop(columns=["latest_window_id"])

    summary = (
        selection.groupby(["LoadType", "mode"], as_index=False)
        .agg(
            windows=("window_id", "nunique"),
            selected_threads=("thread_key", "count"),
            physical_cores_used=("physical_core", "nunique"),
            avg_rho=("rho", "mean"),
            avg_score=("score", "mean"),
        )
        .sort_values(["LoadType", "mode"])
    )

    root = project_root()
    processed = root / "data" / "processed"
    results = root / "results" / "scheduler"
    results.mkdir(parents=True, exist_ok=True)

    selection_path = processed / "final_cpu_selection.csv"
    pair_path = processed / "final_core_pairs.csv"
    final_path = results / "final_window_selection.csv"
    summary_path = results / "cpu_selection_summary.csv"

    selection.to_csv(selection_path, index=False)
    core_pairs.to_csv(pair_path, index=False)
    final_view.to_csv(final_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"Selections: {len(selection)}")
    print(f"Core-pair rows: {len(core_pairs)}")
    print("Latest-window final selections:")
    print(final_view[["LoadType", "window_id", "mode", "physical_core", "smt_slot", "target_cpu", "selected_thread"]].to_string(index=False))
    print(f"Saved: {selection_path}")
    print(f"Saved: {pair_path}")
    print(f"Saved: {final_path}")
    print(f"Saved: {summary_path}")


if __name__ == "__main__":
    main()
