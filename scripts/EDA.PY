#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eda.py —— 探索性数据分析（EDA）：统计、箱线图、相关性热图（中文标签）
"""
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.font_manager import FontProperties

# 中文字体（请确保系统安装了该字体）
zh_font = FontProperties(fname="/usr/share/fonts/truetype/arphic/ukai.ttc", size=12)

# 1. 项目根目录 & 数据路径
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
DATA_CSV = PROJECT_ROOT / 'data' / 'processed' / 'full_dataset.csv'

# 2. 加载数据
print(f"加载数据：{DATA_CSV}")
df = pd.read_csv(DATA_CSV)
print("\n各场景样本量：")
print(df['LoadType'].value_counts(), "\n")

# 3. 基本统计描述
features = [
    'cpu_cycles','instructions','cache_misses','branch_instrs','branch_misses',
    'L1_icache_miss','L1_dcache_miss','ITLB_misses','L2_cache_miss','DTLB_misses'
]
# 中文标签映射
cn_names = {
    'cpu_cycles': 'CPU 周期',
    'instructions': '指令数',
    'cache_misses': '缓存未命中',
    'branch_instrs': '分支指令',
    'branch_misses': '分支未命中',
    'L1_icache_miss': 'L1 指令缓存未命中',
    'L1_dcache_miss': 'L1 数据缓存未命中',
    'ITLB_misses': 'iTLB 未命中',
    'L2_cache_miss': 'L2 缓存未命中',
    'DTLB_misses': 'dTLB 未命中'
}

print("各指标统计描述：")
print(df[features]
      .describe()
      .round(2)
      .rename(index={
          'count': '样本数', 'mean': '均值', 'std': '标准差',
          'min': '最小值', '25%': '25%分位', '50%': '50%分位',
          '75%': '75%分位', 'max': '最大值'
      })
      .to_string(), "\n")

# 4. 创建输出目录
OUT_DIR = PROJECT_ROOT / 'results' / 'eda'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 5. 箱线图：每个指标按 LoadType 对比（中文标题）
for feat in features:
    plt.figure(figsize=(8, 4))
    sns.boxplot(x='LoadType', y=feat, data=df, palette='Set3', dodge=False)
    plt.title(f"{cn_names[feat]} 箱线图（按负载类型）", fontproperties=zh_font)
    plt.xlabel("负载类型", fontproperties=zh_font)
    plt.ylabel(cn_names[feat], fontproperties=zh_font)
    plt.xticks(rotation=45, fontproperties=zh_font)
    plt.tight_layout()
    out_file = OUT_DIR / f"box_{feat}.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"已保存箱线图：{out_file}")

# 6. 相关性热图（中文标题及标签）
corr = df[features].corr()
plt.figure(figsize=(10, 8))
sns.heatmap(
    corr, annot=True, fmt='.2f', cmap='coolwarm',
    xticklabels=[cn_names[f] for f in features],
    yticklabels=[cn_names[f] for f in features]
)
plt.title('硬件事件指标相关性热图', fontproperties=zh_font)
plt.xticks(fontproperties=zh_font, rotation=45)
plt.yticks(fontproperties=zh_font)
plt.tight_layout()
out_corr = OUT_DIR / 'corr_heatmap.png'
plt.savefig(out_corr, dpi=300)
plt.close()
print(f"已保存相关性热图：{out_corr}")

# 7. 保存描述统计到 CSV（带中文行名）
desc = df[features].describe().round(2)
desc = desc.rename(index={
    'count': '样本数', 'mean': '均值', 'std': '标准差',
    'min': '最小值', '25%': '25%分位', '50%': '50%分位',
    '75%': '75%分位', 'max': '最大值'
})
desc.to_csv(OUT_DIR / 'stats_summary.csv', encoding='utf-8-sig')
print(f"已保存统计描述：{OUT_DIR / 'stats_summary.csv'}")

print("EDA 完成，所有图表与统计已输出到 results/eda/ 目录。")
