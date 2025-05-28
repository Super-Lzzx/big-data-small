#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_prod_mixed.py —— 生产型混合负载 (Nginx + 计算) 一键采集+归因，结果保存到 stress-results/prod_mixed
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

# 生产型混合场景定义：Nginx + Sysbench CPU (带 timeout 避免卡死)
workloads = {
    "prod_mixed": [
        # 启动 Nginx 服务（不在后台）
        "sudo systemctl start nginx",
        # 并发 100 请求，总请求数 100k，超时 300s
        "timeout 300s ab -n100000 -c100 http://localhost/",
        # CPU 计算负载，超时 300s
        "timeout 300s sysbench --test=cpu --cpu-max-prime=20000 --num-threads=4 --time=300 run"
    ]
}
collect_seconds = 300  # 采集时长（秒）

# 统一停止子进程的工具函数
def stop_process(proc, label, timeout=10):
    print(f"停止 {label} (pid={proc.pid})")
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
    except Exception as e:
        print(f"向 {label} 发送 SIGINT 失败: {e}")
    try:
        proc.wait(timeout=timeout)
        print(f"{label} 已退出，returncode={proc.returncode}")
    except subprocess.TimeoutExpired:
        print(f"{label} 超时，强制终止")
        proc.terminate()
        proc.wait()

for name, cmds in workloads.items():
    print(f"\n=== 场景：{name} ===")

    # 清理旧文件
    for filename in ("cpu.csv", "sched.csv"):
        fp = SCRIPT_DIR / filename
        if fp.exists():
            fp.unlink()

    # 启动负载命令
    procs = []
    for cmd in cmds:
        if cmd.startswith("sudo systemctl"):
            print(f"执行（前台）: {cmd}")
            subprocess.call(cmd, shell=True)
        else:
            print(f"启动负载: {cmd}")
            p = subprocess.Popen(cmd, cwd=PROJECT_ROOT, shell=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 preexec_fn=os.setsid)
            procs.append((p, cmd))
    time.sleep(5)  # 等待负载稳定

    # 启动 eBPF 采集：线程调度 & CPU 事件
    sched_bin = PROJECT_ROOT / "Data" / "thread" / "data_thread"
    cpu_bin   = PROJECT_ROOT / "Data" / "cpu" / "data"
    print(f"启动线程调度采集(eBPF)：{sched_bin}")
    sched_proc = subprocess.Popen(["sudo", str(sched_bin)], cwd=SCRIPT_DIR, preexec_fn=os.setsid)
    print(f"启动 CPU 事件采集(eBPF)：{cpu_bin}")
    cpu_proc   = subprocess.Popen(["sudo", str(cpu_bin)],   cwd=SCRIPT_DIR, preexec_fn=os.setsid)

    # 计时采集
    print(f"采集 {collect_seconds} 秒 ...")
    time.sleep(collect_seconds)

    # 停止采集程序
    stop_process(sched_proc, "线程调度(eBPF)")
    stop_process(cpu_proc,   "CPU 事件(eBPF)")

    # 停止负载
    for proc, cmd in procs:
        stop_process(proc, f"负载 `{cmd}`", timeout=15)

    # 停止 Nginx 服务
    print("停止 Nginx 服务")
    subprocess.call("sudo systemctl stop nginx", shell=True)

    # 移动并保存采集结果
    out_dir = PROJECT_ROOT / "stress-results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"保存采集文件到 {out_dir}")
    os.replace(str(SCRIPT_DIR / 'cpu.csv'),   str(out_dir / 'cpu.csv'))
    os.replace(str(SCRIPT_DIR / 'sched.csv'), str(out_dir / 'sched.csv'))

    # 归因分析
    print("开始归因分析...")
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
