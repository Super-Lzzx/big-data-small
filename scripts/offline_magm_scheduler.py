#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline reproduction of the chapter-5 MAGM scheduling decision.

This does not replace a real sched_ext scheduler. It consumes chapter-4
predictions and emits the binding decisions that the online Agent would write
to BPF maps.

Input:
  data/processed/thread_predictions.csv

Output:
  data/processed/magm_schedule.csv
  results/scheduler/magm_window_summary.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


FEATURE_COLS = [
    "IPC_norm",
    "MPKI_LLC_norm",
    "MPKI_L1I_norm",
    "MPKI_L1D_norm",
    "MPKI_L2_norm",
    "BrMPKI_norm",
    "MPKI_TLB_norm",
]

PRED_COLS = [f"pred_{c}" for c in FEATURE_COLS]

DIFF_WEIGHTS = {
    "IPC_norm": 2.0,
    "MPKI_L1I_norm": 1.0,
    "MPKI_L1D_norm": 1.0,
    "MPKI_L2_norm": 0.0,
    "MPKI_LLC_norm": 0.0,
    "BrMPKI_norm": 1.0,
    "MPKI_TLB_norm": 0.0,
}

SUM_WEIGHTS = {
    "IPC_norm": 1.0,
    "MPKI_L1I_norm": 2.0,
    "MPKI_L1D_norm": 1.0,
    "MPKI_L2_norm": 2.0,
    "MPKI_LLC_norm": 3.0,
    "BrMPKI_norm": 2.0,
    "MPKI_TLB_norm": 3.0,
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def complementarity_score(a: pd.Series, b: pd.Series, theta: float) -> float:
    score = 0.0
    for feature, pred_col in zip(FEATURE_COLS, PRED_COLS):
        av = float(a[pred_col])
        bv = float(b[pred_col])
        diff = abs(av - bv)
        total = (av + bv) / 2.0
        score += DIFF_WEIGHTS[feature] * diff
        score -= SUM_WEIGHTS[feature] * max(0.0, total - theta)
    return score


def predicted_intensity(row: pd.Series) -> float:
    values = {feature: float(row[f"pred_{feature}"]) for feature in FEATURE_COLS}
    s_fe = 0.75 * values["BrMPKI_norm"] + 0.25 * values["MPKI_L1I_norm"]
    s_core = 0.80 * values["IPC_norm"] + 0.20 * (1.0 - values["MPKI_LLC_norm"])
    s_mem = 0.80 * values["MPKI_LLC_norm"] + 0.20 * values["MPKI_TLB_norm"]
    return max(s_fe, s_core, s_mem)


def cpu_for_core(core_idx: int, sibling: int) -> int:
    return core_idx * 2 + sibling


def schedule_window(
    subdf: pd.DataFrame,
    physical_cores: int,
    theta: float,
    top_k: int,
) -> tuple[list[dict], dict]:
    subdf = subdf.copy()
    subdf["intensity"] = subdf.apply(predicted_intensity, axis=1)
    subdf = subdf.sort_values("intensity", ascending=False).reset_index(drop=True)

    n_run = len(subdf)
    rho = n_run / max(physical_cores, 1)
    decisions = []
    used_threads: set[str] = set()
    mode = "CE" if rho <= 1.0 else "SP"

    if mode == "CE":
        for core_idx, (_, row) in enumerate(subdf.head(physical_cores).iterrows()):
            decisions.append(
                {
                    "LoadType": row["LoadType"],
                    "window_id": int(row["window_id"]),
                    "mode": mode,
                    "thread_key": row["thread_key"],
                    "thread": row["thread"],
                    "pid": int(row["pid"]),
                    "target_cpu": cpu_for_core(core_idx, 0),
                    "paired_with": "",
                    "score": np.nan,
                    "rho": rho,
                    "n_run": n_run,
                }
            )
        return decisions, {"mode": mode, "rho": rho, "n_run": n_run, "pairs": 0, "bound_threads": len(decisions)}

    candidates = subdf.head(min(top_k, len(subdf)))
    edges = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a = candidates.iloc[i]
            b = candidates.iloc[j]
            score = complementarity_score(a, b, theta)
            if score >= 0:
                edges.append((score, i, j))
    edges.sort(reverse=True, key=lambda x: x[0])

    core_idx = 0
    pair_count = 0
    for score, i, j in edges:
        if core_idx >= physical_cores:
            break
        a = candidates.iloc[i]
        b = candidates.iloc[j]
        if a["thread_key"] in used_threads or b["thread_key"] in used_threads:
            continue

        decisions.append(
            {
                "LoadType": a["LoadType"],
                "window_id": int(a["window_id"]),
                "mode": mode,
                "thread_key": a["thread_key"],
                "thread": a["thread"],
                "pid": int(a["pid"]),
                "target_cpu": cpu_for_core(core_idx, 0),
                "paired_with": b["thread_key"],
                "score": score,
                "rho": rho,
                "n_run": n_run,
            }
        )
        decisions.append(
            {
                "LoadType": b["LoadType"],
                "window_id": int(b["window_id"]),
                "mode": mode,
                "thread_key": b["thread_key"],
                "thread": b["thread"],
                "pid": int(b["pid"]),
                "target_cpu": cpu_for_core(core_idx, 1),
                "paired_with": a["thread_key"],
                "score": score,
                "rho": rho,
                "n_run": n_run,
            }
        )
        used_threads.update({a["thread_key"], b["thread_key"]})
        core_idx += 1
        pair_count += 1

    return decisions, {
        "mode": mode,
        "rho": rho,
        "n_run": n_run,
        "pairs": pair_count,
        "bound_threads": len(decisions),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root() / "data" / "processed" / "thread_predictions.csv",
    )
    parser.add_argument("--physical-cores", type=int, default=8)
    parser.add_argument("--theta", type=float, default=0.6)
    parser.add_argument("--top-k", type=int, default=32)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Cannot find {args.input}; run train_thread_predictor.py first")
    df = pd.read_csv(args.input)
    missing = sorted(set(["LoadType", "thread_key", "thread", "pid", "window_id", *PRED_COLS]) - set(df.columns))
    if missing:
        raise ValueError(f"{args.input} is missing required columns: {missing}")

    decisions = []
    summaries = []
    for (load_type, window_id), subdf in df.groupby(["LoadType", "window_id"], sort=True):
        win_decisions, summary = schedule_window(
            subdf,
            physical_cores=args.physical_cores,
            theta=args.theta,
            top_k=args.top_k,
        )
        decisions.extend(win_decisions)
        summary.update({"LoadType": load_type, "window_id": int(window_id)})
        summaries.append(summary)

    root = project_root()
    out_data = root / "data" / "processed" / "magm_schedule.csv"
    out_dir = root / "results" / "scheduler"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "magm_window_summary.csv"

    schedule_df = pd.DataFrame(decisions)
    summary_df = pd.DataFrame(summaries)
    schedule_df.to_csv(out_data, index=False)
    summary_df.to_csv(summary_path, index=False)

    print(f"Windows: {len(summary_df)}")
    print(f"Decisions: {len(schedule_df)}")
    if not summary_df.empty:
        print("Mode counts:")
        print(summary_df["mode"].value_counts().to_string())
        print("Average bound threads per window:", round(summary_df["bound_threads"].mean(), 3))
        print("Average pairs per SP window:", round(summary_df.loc[summary_df["mode"] == "SP", "pairs"].mean(), 3))
    print(f"Saved: {out_data}")
    print(f"Saved: {summary_path}")


if __name__ == "__main__":
    main()
