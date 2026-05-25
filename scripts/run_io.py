#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_io.py —— 磁盘 I/O 场景一键采集+归因，结果保存到 stress-results/io
"""
import subprocess
import time
import os
import pandas as pd
import signal
from pathlib import Path

# 脚本所在目录 & 项目根目录
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()

# I/O 场景定义：顺序写 + 随机读写
workloads = {
    "io": [
        # 顺序写压力
        "stress-ng --hdd 4 --hdd-bytes 2G --timeout 300s",
        # 随机读写混合
        "fio --name=randrw --ioengine=libaio --direct=1 \
            --rw=randrw --rwmixread=70 --bs=4k --size=1G \
            --numjobs=4 --runtime=300 --time_based"
    ]
}
collect_seconds = int(os.environ.get("COLLECT_SECONDS", "300"))  # 采集时长（秒）
warmup_seconds = int(os.environ.get("WARMUP_SECONDS", "5"))      # 负载预热时长（秒）

for name, cmds in workloads.items():
    print(f"\n=== 场景：{name} ===")

    # 1. 清理旧文件
    for filename in ("cpu.csv", "sched.csv"):
        fp = SCRIPT_DIR / filename
        if fp.exists():
            fp.unlink()

    # 2. 启动 I/O 负载
    io_procs = []
    for cmd in cmds:
        print(f"启动 I/O 负载: {cmd}")
        p = subprocess.Popen(cmd, cwd=PROJECT_ROOT, shell=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        io_procs.append(p)
    time.sleep(warmup_seconds)  # 等待负载稳定

    # 3. 启动 eBPF 采集：线程调度 & CPU 事件
    sched_bin = PROJECT_ROOT / "Data" / "thread" / "data_thread"
    cpu_bin   = PROJECT_ROOT / "Data" / "cpu" / "data"
    print(f"启动 eBPF 线程调度采集：{sched_bin}")
    sched_proc = subprocess.Popen(["sudo", str(sched_bin)], cwd=SCRIPT_DIR, preexec_fn=os.setsid)
    print(f"启动 eBPF CPU 事件采集：{cpu_bin}")
    cpu_proc   = subprocess.Popen(["sudo", str(cpu_bin)],   cwd=SCRIPT_DIR, preexec_fn=os.setsid)

    print(f"采集 {collect_seconds} 秒 ...")
    time.sleep(collect_seconds)

    # 4. 停止采集程序
    for proc, label in ((sched_proc, "线程调度(eBPF)"), (cpu_proc, "CPU 事件(eBPF)")):
        print(f"停止 {label} 进程 pid={proc.pid}")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        except Exception as e:
            print(f"发送 SIGINT 失败: {e}")
        try:
            proc.wait(timeout=10)
            print(f"{label} 退出，返回码 {proc.returncode}")
        except subprocess.TimeoutExpired:
            print(f"{label} 超时，强制终止")
            proc.terminate()
            proc.wait()

    # 5. 停止 I/O 负载
    for p in io_procs:
        print(f"停止 I/O 负载进程 pid={p.pid}")
        p.terminate()
        try:
            p.wait(timeout=10)
            print(f"I/O 负载 pid={p.pid} 正常退出，返回码 {p.returncode}")
        except subprocess.TimeoutExpired:
            print(f"I/O 负载 pid={p.pid} 超时，强制杀死")
            p.kill()
            p.wait()

    # 6. 移动并保存采集结果到 stress-results/io/
    out_dir = PROJECT_ROOT / "stress-results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"保存采集文件到 {out_dir}")
    os.replace(str(SCRIPT_DIR / 'cpu.csv'),   str(out_dir / 'cpu.csv'))
    os.replace(str(SCRIPT_DIR / 'sched.csv'), str(out_dir / 'sched.csv'))

    # 7. 归因分析
    print("开始归因分析…")
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
    print(f"→ 归因结果保存在 {out}")
