# compare_k.py

import os
import pandas as pd
import matplotlib.pyplot as plt

# ——————————————
# 1. 加载已经归一化的 df_norm_all
# ——————————————
try:
    df_norm_all = pd.read_csv("../data/processed/df_norm_all.csv")
    print(">>> 成功读取 df_norm_all.csv，行数：", len(df_norm_all))
except Exception as e:
    print("ERROR: 无法读取 df_norm_all.csv，请检查路径！")
    exit(1)

# ——————————————
# 2. 固定 (alpha, beta)，定义要尝试的 k 列表
# ——————————————
alpha, beta = 1.0, 1.0  # 之前选出的基础值
ks = [2, 3, 4, 5]

resource_cols_norm = [
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]

# ——————————————
# 3. 互补度计算函数和贪心选组函数（同上）
# ——————————————
def compute_group_complementarity_norm(df_window, group_threads, resource_cols, alpha, beta):
    df_sub = df_window[df_window["thread"].isin(group_threads)]
    if len(df_sub) < len(group_threads):
        return 0.0
    resource_overlap = sum(df_sub[col].max() - df_sub[col].min() for col in resource_cols)
    ipc_gap = df_sub["IPC_mean"].max() - df_sub["IPC_mean"].min()
    return 1.0 / (1.0 + alpha * resource_overlap + beta * ipc_gap)

def greedy_select_norm(df_window, candidates, k, resource_cols, alpha, beta):
    best_pair, best_pair_score = None, -1.0
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            pair = [candidates[i], candidates[j]]
            sc = compute_group_complementarity_norm(df_window, pair, resource_cols, alpha, beta)
            if sc > best_pair_score:
                best_pair_score = sc
                best_pair = pair

    group = best_pair.copy()
    remaining = set(candidates) - set(group)
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

# ——————————————
# 4. 分别计算每个 k 下所有窗口的 C_group 并保存到 results_k 字典
# ——————————————
results_k = {}
print(f"\n>>> 开始比较不同 k（固定 alpha={alpha}, beta={beta}）下的互补度 …")
for k in ks:
    c_list = []
    for win, subdf in df_norm_all.groupby("window_id"):
        candidates = subdf["thread"].tolist()
        if len(candidates) < k:
            continue
        _, sc = greedy_select_norm(subdf, candidates, k, resource_cols_norm, alpha, beta)
        c_list.append(sc)
    results_k[k] = c_list
    print(f"  k={k} 时，共计算 {len(c_list)} 个窗口的 C_group")

# ——————————————
# 5. 绘制并保存直方图到 ../results/k_compare
# ——————————————
output_dir = "../results/k_compare"
os.makedirs(output_dir, exist_ok=True)
output_png = os.path.join(output_dir, "k_compare_hist.png")

plt.figure(figsize=(8, 5))
for k, c_vals in results_k.items():
    plt.hist(c_vals, bins=30, alpha=0.5, density=True, label=f"k={k}")
plt.xlabel("C_group（互补度）")
plt.ylabel("频率密度")
plt.title(f"固定 alpha={alpha}, beta={beta} 下，不同 k 的互补度分布对比")
plt.legend()
plt.grid(linestyle="--", alpha=0.3)
plt.tight_layout()
plt.savefig(output_png)
print(f"\n>>> k 不同的直方图已保存到：{output_png}")

# ——————————————
# 6. 打印每个 k 下的关键统计量
# ——————————————
print("\n>>> 各 k 下的互补度统计量：")
for k, c_vals in results_k.items():
    desc = pd.Series(c_vals).describe(percentiles=[0.25, 0.5, 0.75]).round(3)
    print(f"\nk={k} 的 C_group 统计量：\n{desc}")
