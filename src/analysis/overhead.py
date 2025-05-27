#!/usr/bin/env python3
# overhead.py

import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from pathlib import Path

# overhead.py —— 绘制监控开销对比图，改用新目录结构

def main():
    # —— 中文字体设置 ——
    zh_font = FontProperties(fname="/usr/share/fonts/truetype/arphic/ukai.ttc", size=12)

    # 1. 定义项目根目录 & 数据文件路径
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    csv_path = PROJECT_ROOT / 'data' / 'overhead' / 'monitor_overhead.csv'
    if not csv_path.exists():
        raise FileNotFoundError(f"Cannot find monitor overhead CSV: {csv_path}")
    df = pd.read_csv(csv_path)

    # 翻译模式名称（可选）
    name_map = {
        'perf':    'Perf',
        'ptrace':  'Ptrace',
        'ebpf':    'eBPF'
    }
    if 'mode' in df.columns:
        df['模式'] = df['mode'].map(name_map)
    else:
        df['模式'] = df['模式'] if '模式' in df.columns else df.iloc[:,0]

    # 2. 准备输出目录
    out_dir = PROJECT_ROOT / 'results'
    out_dir.mkdir(exist_ok=True)

    # —— 绘制真实时间开销柱状图 ——
    fig1, ax1 = plt.subplots(figsize=(6, 4))
    ax1.bar(df['模式'], df['Overhead(s)'], color='skyblue')
    ax1.set_title('监控方式真实时间开销对比', fontproperties=zh_font)
    ax1.set_xlabel('采集模式', fontproperties=zh_font)
    ax1.set_ylabel('开销（秒）', fontproperties=zh_font)
    fig1.tight_layout()
    out1 = out_dir / 'overhead_time.png'
    fig1.savefig(out1)

    # —— 绘制 CPU 占用柱状图 ——
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.bar(df['模式'], df['CPU_pct'], color='salmon')
    ax2.set_title('监控方式 CPU 占用对比', fontproperties=zh_font)
    ax2.set_xlabel('采集模式', fontproperties=zh_font)
    ax2.set_ylabel('CPU 占用率（%）', fontproperties=zh_font)
    fig2.tight_layout()
    out2 = out_dir / 'overhead_cpu.png'
    fig2.savefig(out2)

    print("✅ 已生成对比图：")
    print(f"  • 时间开销图：{out1}")
    print(f"  • CPU 占用图：{out2}")

if __name__ == '__main__':
    main()
