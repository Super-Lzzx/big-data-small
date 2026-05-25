#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launch a live workload and bind its current tasks using MAGM CPU selections.

This is the user-space validation path: it does not need sched_ext. It starts a
workload, discovers the live processes/threads in the workload process group,
and applies the target CPU sequence exported by final_cpu_selection.csv.

Examples:
  python3 scripts/run_live_affinity_validation.py --load-type cpu --duration 20
  python3 scripts/run_live_affinity_validation.py --load-type memory --duration 20
  python3 scripts/run_live_affinity_validation.py --load-type cpu --duration 20 -- stress-ng --cpu 14 --timeout 20s
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

import pandas as pd


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_command(load_type: str, duration: int) -> list[str]:
    if load_type == "memory":
        return [
            "stress-ng",
            "--vm",
            "8",
            "--vm-bytes",
            "512M",
            "--vm-method",
            "memcpy",
            "--timeout",
            f"{duration}s",
        ]
    if load_type == "mixed":
        return [
            "stress-ng",
            "--cpu",
            "6",
            "--vm",
            "4",
            "--vm-bytes",
            "512M",
            "--io",
            "2",
            "--timeout",
            f"{duration}s",
        ]
    return ["stress-ng", "--cpu", "14", "--timeout", f"{duration}s"]


def load_cpu_plan(path: Path, load_type: str, window_id: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["LoadType"].astype(str) == load_type].copy()
    if df.empty:
        raise ValueError(f"No CPU-selection rows for LoadType={load_type}")

    if window_id == "latest":
        df = df[df["window_id"] == df["window_id"].max()]
    else:
        df = df[df["window_id"] == int(window_id)]
    if df.empty:
        raise ValueError(f"No CPU-selection rows for LoadType={load_type}, window_id={window_id}")

    return df.sort_values(["physical_core", "smt_slot", "target_cpu"]).reset_index(drop=True)


def parse_proc_stat(stat_text: str) -> dict[str, int | str]:
    # /proc stat's comm field is inside parentheses and can contain spaces.
    close = stat_text.rfind(")")
    before = stat_text[: close + 1]
    after = stat_text[close + 2 :].split()
    pid = int(before.split("(", 1)[0].strip())
    comm = before.split("(", 1)[1][:-1]
    return {
        "pid": pid,
        "comm": comm,
        "ppid": int(after[1]),
        "pgrp": int(after[2]),
        "processor": int(after[36]) if len(after) > 36 else -1,
    }


def process_group_pids(pgid: int) -> list[int]:
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = parse_proc_stat((entry / "stat").read_text(encoding="utf-8"))
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            continue
        if stat["pgrp"] == pgid:
            pids.append(int(entry.name))
    return sorted(pids)


def task_tids(pid: int) -> list[int]:
    task_dir = Path("/proc") / str(pid) / "task"
    try:
        return sorted(int(p.name) for p in task_dir.iterdir() if p.name.isdigit())
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return []


def task_comm(tid: int) -> str:
    try:
        return (Path("/proc") / str(tid) / "comm").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return ""


def apply_affinity_to_group(pgid: int, cpu_plan: list[int]) -> pd.DataFrame:
    records = []
    seen: set[int] = set()
    tids = []
    for pid in process_group_pids(pgid):
        for tid in task_tids(pid):
            if tid not in seen:
                seen.add(tid)
                tids.append(tid)

    tids = sorted(tids)
    for idx, tid in enumerate(tids):
        target_cpu = cpu_plan[idx % len(cpu_plan)]
        before = ""
        after = ""
        status = "applied"
        reason = ""
        try:
            before = ",".join(str(x) for x in sorted(os.sched_getaffinity(tid)))
            os.sched_setaffinity(tid, {target_cpu})
            after = ",".join(str(x) for x in sorted(os.sched_getaffinity(tid)))
        except ProcessLookupError:
            status = "skipped"
            reason = "task-exited"
        except PermissionError:
            status = "failed"
            reason = "permission-denied"
        except OSError as exc:
            status = "failed"
            reason = str(exc)
        records.append(
            {
                "tid": tid,
                "comm": task_comm(tid),
                "target_cpu": target_cpu,
                "status": status,
                "reason": reason,
                "affinity_before": before,
                "affinity_after": after,
            }
        )
    return pd.DataFrame(records)


def terminate_process_group(proc: subprocess.Popen, grace: float = 3.0) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        proc.wait(timeout=grace)
        return
    except Exception:
        pass
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=grace)
        except Exception:
            proc.kill()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--load-type", default="cpu", help="cpu, memory, mixed, io, prod_mixed")
    parser.add_argument("--window-id", default="latest")
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    parser.add_argument(
        "--selection-file",
        type=Path,
        default=project_root() / "data" / "processed" / "final_cpu_selection.csv",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        command = default_command(args.load_type, args.duration)

    plan = load_cpu_plan(args.selection_file, args.load_type, args.window_id)
    cpu_plan = plan["target_cpu"].astype(int).tolist()
    if not cpu_plan:
        raise ValueError("CPU plan is empty")

    print("CPU selection plan:")
    print(plan[["LoadType", "window_id", "mode", "physical_core", "smt_slot", "target_cpu", "selected_thread"]].to_string(index=False))
    print("Launching workload:", " ".join(command))

    proc = subprocess.Popen(
        command,
        cwd=project_root(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    pgid = os.getpgid(proc.pid)
    time.sleep(args.settle_seconds)

    report = apply_affinity_to_group(pgid, cpu_plan)
    out_dir = project_root() / "results" / "scheduler"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "live_affinity_report.csv"
    report.to_csv(out_path, index=False)

    print("Affinity application:")
    if report.empty:
        print("No live tasks discovered in workload process group.")
    else:
        print(report.to_string(index=False))
        print(report["status"].value_counts().to_string())
    print(f"Saved: {out_path}")

    remaining = max(0.0, args.duration - args.settle_seconds)
    try:
        proc.wait(timeout=remaining + 2.0)
    except subprocess.TimeoutExpired:
        terminate_process_group(proc)

    print("Workload exited with code:", proc.returncode)


if __name__ == "__main__":
    main()
