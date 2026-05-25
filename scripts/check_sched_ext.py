#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check whether the current kernel can run a sched_ext scheduler.

This script is intentionally conservative: if any required kernel-visible
sched_ext surface is missing, it exits non-zero and explains the blocker.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def read_config_flag(flag: str) -> str | None:
    config = Path(f"/boot/config-{platform.release()}")
    if not config.exists():
        return None
    prefix = f"{flag}="
    for line in config.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1]
    return None


def btf_has_sched_ext() -> bool:
    btf = Path("/sys/kernel/btf/vmlinux")
    if not btf.exists():
        return False
    try:
        out = subprocess.run(
            ["bpftool", "btf", "dump", "file", str(btf), "format", "c"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "sched_ext_ops" in out and "scx_bpf" in out


def main() -> int:
    release = platform.release()
    sched_ext_sysfs = Path("/sys/kernel/sched_ext")
    config_scx = read_config_flag("CONFIG_SCHED_CLASS_EXT")
    config_bpf = read_config_flag("CONFIG_BPF_SYSCALL")
    config_btf = read_config_flag("CONFIG_DEBUG_INFO_BTF")
    has_btf_scx = btf_has_sched_ext()

    print(f"Kernel: {release}")
    print(f"CPU count: {os.cpu_count()}")
    print(f"/sys/kernel/sched_ext: {'present' if sched_ext_sysfs.exists() else 'missing'}")
    print(f"CONFIG_SCHED_CLASS_EXT: {config_scx or 'missing'}")
    print(f"CONFIG_BPF_SYSCALL: {config_bpf or 'missing'}")
    print(f"CONFIG_DEBUG_INFO_BTF: {config_btf or 'missing'}")
    print(f"Kernel BTF sched_ext symbols: {'present' if has_btf_scx else 'missing'}")

    blockers = []
    if config_scx != "y":
        blockers.append("CONFIG_SCHED_CLASS_EXT is not enabled")
    if not sched_ext_sysfs.exists():
        blockers.append("/sys/kernel/sched_ext is missing")
    if not has_btf_scx:
        blockers.append("kernel BTF does not expose sched_ext/scx symbols")
    if config_bpf != "y":
        blockers.append("CONFIG_BPF_SYSCALL is not enabled")
    if config_btf != "y":
        blockers.append("CONFIG_DEBUG_INFO_BTF is not enabled")

    if blockers:
        print("\nResult: sched_ext is NOT available on this kernel.")
        print("Blockers:")
        for item in blockers:
            print(f"  - {item}")
        print("\nUse the existing user-space affinity validation path on this machine,")
        print("or boot a kernel with sched_ext enabled to run a real scx scheduler.")
        return 1

    print("\nResult: sched_ext appears available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
