import os
import pandas as pd

# ------------------------------
# 1. 读取原始数据并生成 df_norm_all
# ------------------------------
print(">>> 当前工作目录：", os.getcwd())

# 1.1 读取 full_dataset.csv
try:
    df = pd.read_csv("../data/processed/full_dataset.csv")
    print("1) 已成功读取 full_dataset.csv，行数：", len(df))
    print("   前 5 行示例：")
    print(df.head(5).to_string(index=False))
except Exception as e:
    print("ERROR: 无法读取 full_dataset.csv，请检查文件路径是否正确！")
    print("    尝试路径：", os.path.abspath("../data/processed/full_dataset.csv"))
    print("    错误信息：", e)
    exit(1)

# 1.2 生成 window_id 列（100 ms = 100_000_000 ns）
WINDOW_NS = 100_000_000
df["window_id"] = (df["ts"] // WINDOW_NS).astype(int)
print("\n2) 计算 window_id 完成，范围：", df["window_id"].min(), "-", df["window_id"].max())

# 1.3 计算 IPC 列
df["IPC"] = df["instructions"] / df["cpu_cycles"]
print("\n3) 添加 IPC 列完成，部分示例：")
print(df[["thread", "IPC"]].head().to_string(index=False))

# ------------------------------
# 2. 按 (window_id, thread) 聚合（得到 df_agg_all）
# ------------------------------
agg_cols = [
    "IPC",
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]
agg_dict = {col: "mean" for col in agg_cols}

print("\n4) 正在按 (window_id, thread) 聚合 …")
df_agg_all = (
    df
    .groupby(["window_id", "thread"], as_index=False)
    .agg(agg_dict)
)
df_agg_all = df_agg_all.rename(columns={"IPC": "IPC_mean"})
print("   聚合完成，df_agg_all 行数：", len(df_agg_all))
print("   聚合后前 5 行示例：")
print(df_agg_all.head(5).to_string(index=False))

# ------------------------------
# 3. 对 df_agg_all 做 Min–Max 归一化（得到 df_norm_all）
# ------------------------------
num_cols = [
    "IPC_mean",
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]

print("\n5) 开始对 df_agg_all 做 Min–Max 归一化 …")
df_norm_all = df_agg_all.copy()
for col in num_cols:
    vmin, vmax = df_norm_all[col].min(), df_norm_all[col].max()
    df_norm_all[col] = (df_norm_all[col] - vmin) / (vmax - vmin + 1e-10)

print("   归一化完成。各列范围如下：")
print(df_norm_all[num_cols].describe().loc[["min", "max"]].to_string())

print("\n6) df_norm_all 前 5 行示例：")
print(df_norm_all.head(5).to_string(index=False))

# 如果需要，把 df_norm_all 保存到本地 CSV 以备后续加载
output_path = "../data/processed/df_norm_all.csv"
df_norm_all.to_csv(output_path, index=False)
print(f"\n7) 已将 df_norm_all 保存到：{output_path}")
