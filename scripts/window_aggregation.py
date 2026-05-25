import os
import pandas as pd
import itertools

# ------------------------------
# window_aggregation.py
# ------------------------------

# 0. 输出当前工作目录，确认相对路径能找到 CSV
print(">>> 当前工作目录 (cwd):", os.getcwd())

# ------------------------------
# 1. 读取原始数据并生成 window_id
# ------------------------------
try:
    df = pd.read_csv("../data/processed/full_dataset.csv")
    print("1) 成功读取原始数据，共行数：", len(df))
    print("   前 5 行示例：")
    print(df[["ts", "thread", "cpu_cycles", "instructions"]].head().to_string(index=False))
except Exception as e:
    print("ERROR: 无法读取 full_dataset.csv！")
    print("尝试路径：", os.path.abspath("../data/processed/full_dataset.csv"))
    print("异常信息：", e)
    exit(1)

# 计算 window_id：100 ms = 100,000,000 ns
WINDOW_NS = 100_000_000
df["window_id"] = (df["ts"] // WINDOW_NS).astype(int)
print(f"2) 计算 window_id 完成。window_id 范围：{df['window_id'].min()} – {df['window_id'].max()}")

# 添加 IPC 列 = instructions / cpu_cycles
df["IPC"] = df["instructions"] / df["cpu_cycles"]
print("3) 添加 IPC 列完成。部分 IPC 示例：")
print(df[["thread", "IPC"]].dropna().head().to_string(index=False))

# ------------------------------
# 2. 按 (window_id, thread) 聚合所有线程（不区分 LoadType）
# ------------------------------
agg_cols = [
    "IPC",
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]
agg_dict = {col: "mean" for col in agg_cols}

print("4) 开始对 (window_id, thread) 进行聚合 …")
df_agg_all = (
    df
    .groupby(["window_id", "thread"], as_index=False)
    .agg(agg_dict)
)
df_agg_all = df_agg_all.rename(columns={"IPC": "IPC_mean"})
print("   聚合完成。df_agg_all 行数：", len(df_agg_all))
print("   聚合后前 5 行示例：")
print(df_agg_all.head(5).to_string(index=False))

# ------------------------------
# 3. Min–Max 归一化所有数值列
# ------------------------------
num_cols = [
    "IPC_mean",
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]

print("5) 开始 Min–Max 归一化 …")
df_norm_all = df_agg_all.copy()
for col in num_cols:
    vmin, vmax = df_norm_all[col].min(), df_norm_all[col].max()
    df_norm_all[col] = (df_norm_all[col] - vmin) / (vmax - vmin + 1e-10)
print("   归一化完成。数值列范围：")
print(df_norm_all[num_cols].describe().loc[["min", "max"]].to_string())

# ------------------------------
# 4. 定义互补度计算函数（不区分 LoadType）
# ------------------------------
def compute_group_complementarity_norm(
    df_window: pd.DataFrame,
    group_threads: list,
    resource_cols: list,
    alpha: float,
    beta: float
) -> float:
    df_sub = df_window[df_window["thread"].isin(group_threads)]
    if len(df_sub) < len(group_threads):
        return 0.0
    # 资源极差之和
    resource_overlap = sum(df_sub[col].max() - df_sub[col].min() for col in resource_cols)
    # IPC 极差
    ipc_gap = df_sub["IPC_mean"].max() - df_sub["IPC_mean"].min()
    return 1.0 / (1.0 + alpha * resource_overlap + beta * ipc_gap)

# ------------------------------
# 5. 定义贪心法选最优 k 条线程函数
# ------------------------------
def greedy_select_norm(
    df_window: pd.DataFrame,
    candidates: list,
    k: int,
    resource_cols: list,
    alpha: float,
    beta: float
):
    best_pair, best_pair_score = None, -1.0
    # 第一阶段：枚举两两组合
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            pair = [candidates[i], candidates[j]]
            sc = compute_group_complementarity_norm(df_window, pair, resource_cols, alpha, beta)
            if sc > best_pair_score:
                best_pair_score = sc
                best_pair = pair

    group = best_pair.copy()
    remaining = set(candidates) - set(group)
    # 第二阶段：贪心扩展，直到凑够 k 条
    while len(group) < k and remaining:
        best_next, best_next_score = None, -1.0
        for t in remaining:
            sc = compute_group_complementarity_norm(df_window, group + [t], resource_cols, alpha, beta)
            if sc > best_next_score:
                best_next_score = sc
                best_next = t
        group.append(best_next)
        remaining.remove(best_next)

    final_score = compute_group_complementarity_norm(df_window, group, resource_cols, alpha, beta)
    return group, final_score

# ------------------------------
# 6. 批量遍历所有窗口并保存跨类型结果
# ------------------------------
resource_cols_norm = [
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]
k = 4
alpha, beta = 1.0, 1.0  # α、β 可根据后续离线调优更改

print(f"7) 开始遍历每个窗口，挑选最优并发 k={k} 条线程 …")
results = []
window_counter = 0

for win, subdf in df_norm_all.groupby("window_id"):
    window_counter += 1
    candidates = subdf["thread"].tolist()
    if len(candidates) < k:
        continue

    group, sc = greedy_select_norm(subdf, candidates, k, resource_cols_norm, alpha, beta)
    results.append({
        "window_id": win,
        "best_group": group,
        "C_group": sc
    })

    # 每 100 个窗口打印一次进度
    if window_counter % 100 == 0:
        print(f"   已处理窗口数：{window_counter}, 当前 window_id={win}, 候选线程数={len(candidates)}, 互补度={sc:.4f}")

print(f"8) 遍历完成，共为 {len(results)} 个窗口生成了最优线程组和互补度。")

df_results_all = pd.DataFrame(results)
output_path = "../data/processed/all_windows_best_groups_cross_load.csv"
df_results_all.to_csv(output_path, index=False)
print(f"9) 已将结果保存到：{output_path}")
