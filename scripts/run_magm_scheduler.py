#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified entry point for the final scheduling stage.

On kernels with sched_ext support, --mode scx launches the prototype scheduler
under sched_ext/.  On the current Ubuntu 6.8 kernel in this workspace,
sched_ext is not available, so the script falls back to the user-space
sched_setaffinity validation path.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=project_root())


def sched_ext_available() -> bool:
    return subprocess.call(
        [sys.executable, "scripts/check_sched_ext.py"],
        cwd=project_root(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


def run_scx() -> int:
    binary = project_root() / "sched_ext" / "magm_scx"
    plan = project_root() / "data" / "processed" / "final_cpu_selection.csv"
    if not binary.exists():
        print("sched_ext is available, but sched_ext/magm_scx is not built.")
        print("Build it on the target machine with: cd sched_ext && make")
        return 2
    if not plan.exists():
        print("Cannot find data/processed/final_cpu_selection.csv.")
        print("Run scripts/offline_magm_scheduler.py and scripts/export_cpu_selection.py first.")
        return 2
    return run([str(binary), str(plan)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "scx", "affinity"], default="auto")
    parser.add_argument("--load-type", default="cpu")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--window-id", default="latest")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.mode in {"auto", "scx"} and sched_ext_available():
        return run_scx()

    if args.mode == "scx":
        print("sched_ext is not available on this kernel. Run scripts/check_sched_ext.py for details.")
        return 1

    cmd = [
        sys.executable,
        "scripts/run_live_affinity_validation.py",
        "--load-type",
        args.load_type,
        "--duration",
        str(args.duration),
        "--window-id",
        args.window_id,
    ]
    if args.command:
        cmd.extend(args.command)
    return run(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
