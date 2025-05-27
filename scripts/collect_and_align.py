#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
align_thread.py —— 对 raw 数据做归因，并保存到 processed 目录
"""

from pathlib import Path
import pandas as pd

# 1. 定义项目目录和文件路径
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
RAW_DIR       = PROJECT_ROOT / 'data' / 'raw'
PROCESSED_DIR = PROJECT_ROOT / 'data' / 'processed'
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

CPU_CSV   = RAW_DIR / 'cpu.csv'
SCHED_CSV = RAW_DIR / 'sched.csv'
OUT_CSV   = PROCESSED_DIR / 'cpu_thread_attributed.csv'

print(f"加载 CPU 事件数据：{CPU_CSV}")
print(f"加载调度事件数据：{SCHED_CSV}")

# 2. 读取带表头的 CSV
cpu_df   = pd.read_csv(CPU_CSV)
sched_df = pd.read_csv(SCHED_CSV)

# 3. 转换列类型
cpu_df['ts']   = cpu_df['time'].astype('int64')
sched_df['ts'] = sched_df['ts'].astype('int64')

# 4. 排序（可选）
cpu_df   = cpu_df.sort_values(['cpu', 'ts'])
sched_df = sched_df.sort_values(['cpu', 'ts'])

# 5. 最近调度法归因
import pandas as _pd  # 为了返回 pd.Series

def find_last_thread(row):
    ts  = row['ts']
    cpu = row['cpu']
    mask = (sched_df['cpu'] == cpu) & (sched_df['ts'] <= ts)
    matched = sched_df[mask]
    if matched.empty:
        return _pd.Series({'thread': None, 'pid': None})
    last = matched.iloc[-1]
    return _pd.Series({'thread': last['next_comm'], 'pid': last['next_pid']})

cpu_df[['thread', 'pid']] = cpu_df.apply(find_last_thread, axis=1)

# 6. 保存结果
cpu_df.to_csv(OUT_CSV, index=False)
print(f"归因完成，结果保存在 {OUT_CSV}")
