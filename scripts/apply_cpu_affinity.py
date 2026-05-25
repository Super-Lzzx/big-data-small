#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply offline MAGM CPU-selection decisions with sched_setaffinity.

By default this script is a dry run. Add --apply to actually bind live
Linux tasks/threads to the target logical CPUs from final_cpu_selection.csv.

Examples:
  python3 scripts/apply_cpu_affinity.py
  python3 scripts/apply_cpu_affinity.py --load-type prod_mixed
  python3 scripts/apply_cpu_affinity.py --load-type prod_mixed --window-id latest --apply
  python3 scripts/apply_cpu_affinity.py --load-type prod_mixed --apply --no-strict-comm
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_thread_key(thread_key: str) -> tuple[int | None, str]:
    parts = str(thread_key).split(":", 2)
    if len(parts) < 3 or not parts[1].startswith("pid="):
        return None, ""
    try:
        pid = int(parts[1].removeprefix("pid="))
    except ValueError:
        pid = None
    return pid, parts[2]


def proc_comm(tid: int) -> str | None:
    comm_path = Path("/proc") / str(tid) / "comm"
    try:
        return comm_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except PermissionError:
        return None


def current_affinity(tid: int) -> str:
    try:
        return ",".join(str(cpu) for cpu in sorted(os.sched_getaffinity(tid)))
    except ProcessLookupError:
        return ""
    except PermissionError:
        return "permission-denied"


def choose_rows(df: pd.DataFrame, load_type: str | None, window_id: str) -> pd.DataFrame:
    out = df.copy()
    if load_type:
        out = out[out["LoadType"].astype(str) == load_type]
    if out.empty:
        return out

    if window_id == "latest":
        latest = out.groupby("LoadType")["window_id"].transform("max")
        out = out[out["window_id"] == latest]
    else:
        out = out[out["window_id"] == int(window_id)]
    return out.sort_values(["LoadType", "window_id", "target_cpu"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root() / "data" / "processed" / "final_cpu_selection.csv",
    )
    parser.add_argument("--load-type", default=None, help="Example: cpu, io, memory, mixed, prod_mixed")
    parser.add_argument("--window-id", default="latest", help="'latest' or a numeric window id")
    parser.add_argument("--apply", action="store_true", help="Actually call sched_setaffinity")
    parser.add_argument(
        "--no-strict-comm",
        action="store_true",
        help="Do not require /proc/<tid>/comm to match the recorded thread name",
    )
    parser.add_argument(
        "--include-kernel",
        action="store_true",
        help="Try pid 0 / kernel-like rows too. Normally these are skipped.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Cannot find {args.input}; run export_cpu_selection.py first")

    df = pd.read_csv(args.input)
    required = {"LoadType", "window_id", "thread_key", "target_cpu"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{args.input} is missing columns: {missing}")

    rows = choose_rows(df, args.load_type, args.window_id)
    if rows.empty:
        print("No rows selected. Check --load-type and --window-id.")
        return

    cpu_count = os.cpu_count() or 0
    report_rows = []
    strict_comm = not args.no_strict_comm

    for _, row in rows.iterrows():
        tid, recorded_comm = parse_thread_key(row["thread_key"])
        target_cpu = int(row["target_cpu"])
        status = "dry-run"
        live_comm = ""
        before = ""
        after = ""
        reason = ""

        if tid is None:
            status = "skipped"
            reason = "cannot-parse-tid"
        elif tid == 0 and not args.include_kernel:
            status = "skipped"
            reason = "pid-0"
        elif target_cpu < 0 or target_cpu >= cpu_count:
            status = "skipped"
            reason = f"target-cpu-out-of-range-{target_cpu}"
        else:
            live_comm = proc_comm(tid) or ""
            if not live_comm:
                status = "skipped"
                reason = "task-not-live"
            elif strict_comm and live_comm != recorded_comm[:15]:
                # /proc comm is capped at 15 bytes on Linux.
                status = "skipped"
                reason = f"comm-mismatch-live={live_comm}-recorded={recorded_comm[:15]}"
            else:
                before = current_affinity(tid)
                if args.apply:
                    try:
                        os.sched_setaffinity(tid, {target_cpu})
                        after = current_affinity(tid)
                        status = "applied"
                    except ProcessLookupError:
                        status = "skipped"
                        reason = "task-exited"
                    except PermissionError:
                        status = "failed"
                        reason = "permission-denied"
                    except OSError as exc:
                        status = "failed"
                        reason = str(exc)
                else:
                    after = str(target_cpu)

        report_rows.append(
            {
                "LoadType": row["LoadType"],
                "window_id": int(row["window_id"]),
                "tid": tid,
                "recorded_comm": recorded_comm,
                "live_comm": live_comm,
                "target_cpu": target_cpu,
                "status": status,
                "reason": reason,
                "affinity_before": before,
                "affinity_after": after,
                "mode": row.get("mode", ""),
                "physical_core": row.get("physical_core", ""),
                "smt_slot": row.get("smt_slot", ""),
            }
        )

    report = pd.DataFrame(report_rows)
    out_dir = project_root() / "results" / "scheduler"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "applied" if args.apply else "dry_run"
    out_path = out_dir / f"affinity_{suffix}_report.csv"
    report.to_csv(out_path, index=False)

    print("Selected rows:", len(rows))
    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    print(report["status"].value_counts(dropna=False).to_string())
    if "reason" in report:
        reasons = report[report["reason"].astype(str) != ""]["reason"].value_counts()
        if not reasons.empty:
            print("Reasons:")
            print(reasons.to_string())
    print("Preview:")
    print(
        report[
            [
                "LoadType",
                "window_id",
                "tid",
                "recorded_comm",
                "live_comm",
                "target_cpu",
                "status",
                "reason",
            ]
        ].head(30).to_string(index=False)
    )
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
