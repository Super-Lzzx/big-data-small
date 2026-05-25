#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_results.py — 合并 stress-results 下所有场景的 attr.csv，生成 data/processed/full_dataset.csv
并额外生成对齐格式的全文本表格 data/processed/full_dataset_aligned.txt
"""
import os
import pandas as pd
from pathlib import Path

# 脚本所在目录 & 项目根目录
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
SR_DIR = PROJECT_ROOT / 'stress-results'

# 1. 收集所有场景目录
if not SR_DIR.exists():
    print(f'错误：未找到目录 {SR_DIR}，请确保在项目根目录下存在 stress-results。')
    exit(1)
requested = os.environ.get("MERGE_SCENES", "").strip()
if requested:
    allowed = {x.strip() for x in requested.split(",") if x.strip()}
    scenes = [p.name for p in SR_DIR.iterdir() if p.is_dir() and p.name in allowed]
else:
    scenes = [p.name for p in SR_DIR.iterdir() if p.is_dir()]
if not scenes:
    print('警告：stress-results 下没有子目录场景。')
    exit(1)
print('检测到场景：', scenes)

# 2. 读取每个场景的 attr.csv 并添加 LoadType 标签
dfs = []
for scene in scenes:
    f = SR_DIR / scene / 'attr.csv'
    if not f.exists():
        print(f'警告：{f} 不存在，跳过')
        continue
    df = pd.read_csv(f)
    df['LoadType'] = scene
    dfs.append(df)

if not dfs:
    print('没有可合并的数据，退出。')
    exit(1)

# 3. 合并所有 DataFrame
full = pd.concat(dfs, ignore_index=True)

# 4. 保存原始 CSV 到 data/processed/full_dataset.csv
OUT_DIR = PROJECT_ROOT / 'data' / 'processed'
OUT_DIR.mkdir(parents=True, exist_ok=True)
out_csv = OUT_DIR / 'full_dataset.csv'
full.to_csv(out_csv, index=False)
print(f'已生成原始 CSV：{out_csv}')

# 5. 写入对齐的纯文本表格到 full_dataset_aligned.txt
out_txt = OUT_DIR / 'full_dataset_aligned.txt'
with open(out_txt, 'w', encoding='utf-8') as f:
    # to_string 自动对齐列
    f.write(full.to_string(index=False))
print(f'已生成对齐文本：{out_txt}')

print(f'共 {len(full)} 条样本，来自 {len(dfs)} 个场景。')
