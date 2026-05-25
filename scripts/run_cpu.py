#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_cpu.py —— 纯 CPU 场景一键采集+归因，结果保存到 stress-results/cpu
"""

import subprocess, time, os, pandas as pd, signal
from pathlib import Path

# 脚本目录 & 项目根目录
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()

# 场景定义
workloads = {
    "cpu": [
        "stress-ng --cpu 8 --cpu-method matrixprod --timeout 300s"
    ]
}
collect_seconds = int(os.environ.get("COLLECT_SECONDS", "300"))  # 采集时长（秒）
warmup_seconds = int(os.environ.get("WARMUP_SECONDS", "5"))      # 负载预热时长（秒）

for name, cmds in workloads.items():
    print(f"\n=== 场景：{name} ===")

    # 1. 清理旧文件
    for f in ("cpu.csv", "sched.csv"):
        fp = SCRIPT_DIR / f
        if fp.exists():
            fp.unlink()

    # 2. 启动负载
    procs = []
    for cmd in cmds:
        p = subprocess.Popen(cmd.split(), cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
    time.sleep(warmup_seconds)  # 等待负载稳定

    # 3. 启动采集
    sched_bin = PROJECT_ROOT / "Data" / "thread" / "data_thread"
    cpu_bin   = PROJECT_ROOT / "Data" / "cpu" / "data"
    sched_proc = subprocess.Popen(["sudo", str(sched_bin)], cwd=SCRIPT_DIR, preexec_fn=os.setsid)
    cpu_proc   = subprocess.Popen(["sudo", str(cpu_bin)],   cwd=SCRIPT_DIR, preexec_fn=os.setsid)
    print(f"采集 {collect_seconds} 秒 ...")
    time.sleep(collect_seconds)

    # 4. 停止采集
    os.killpg(os.getpgid(sched_proc.pid), signal.SIGINT)
    os.killpg(os.getpgid(cpu_proc.pid),   signal.SIGINT)
    for proc in (sched_proc, cpu_proc):
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait()

    # 5. 停止负载
    for p in procs:
        p.terminate()
        p.wait()

    # 6. 移动并保存到 stress-results/{name}/
    out_dir = PROJECT_ROOT / "stress-results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    os.replace(str(SCRIPT_DIR / 'cpu.csv'),   str(out_dir / 'cpu.csv'))
    os.replace(str(SCRIPT_DIR / 'sched.csv'), str(out_dir / 'sched.csv'))

    # 7. 归因分析
    cpu_df   = pd.read_csv(out_dir / 'cpu.csv')
    sched_df = pd.read_csv(out_dir / 'sched.csv')
    cpu_df['ts']   = cpu_df['time'].astype('int64')
    sched_df['ts'] = sched_df['ts'].astype('int64')
    cpu_df   = cpu_df.sort_values(['cpu','ts'])
    sched_df = sched_df.sort_values(['cpu','ts'])

    import pandas as _pd
    def find_last_thread(row):
        ts, cpu = row['ts'], row['cpu']
        m = sched_df[(sched_df['cpu']==cpu) & (sched_df['ts']<=ts)]
        if m.empty:
            return _pd.Series({'thread':None,'pid':None})
        last = m.iloc[-1]
        return _pd.Series({'thread':last['next_comm'],'pid':last['next_pid']})

    cpu_df[['thread','pid']] = cpu_df.apply(find_last_thread, axis=1)
    out = out_dir / 'attr.csv'
    cpu_df.to_csv(out, index=False)
    print(f"→ 结果保存在 {out}")
