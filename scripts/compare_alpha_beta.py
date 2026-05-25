# 文件名：compare_alpha_beta.py

import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# 1. 中文字体（请确认路径下有该字体文件）
zh_font = FontProperties(fname="/usr/share/fonts/truetype/arphic/ukai.ttc", size=12)
# ------------------------------
# 1. 加载 df_norm_all
# ------------------------------
try:
    df_norm_all = pd.read_csv("../data/processed/df_norm_all.csv")
    print(">>> 成功读取 df_norm_all.csv，行数：", len(df_norm_all))
    print("    前 5 行示例：")
    print(df_norm_all.head(5).to_string(index=False))
except Exception as e:
    print("ERROR: 无法读取 df_norm_all.csv，请检查路径！")
    exit(1)

# ------------------------------
# 2. 定义 (alpha,beta) 组合和并发度 k
# ------------------------------
alphas = [0.5, 1.0, 2.0, 5.0]
betas  = [0.5, 1.0, 2.0, 5.0]
k = 4

resource_cols_norm = [
    "cpu_cycles", "instructions", "cache_misses", "branch_instrs", "branch_misses",
    "L1_icache_miss", "L1_dcache_miss", "ITLB_misses", "L2_cache_miss", "DTLB_misses"
]

# ------------------------------
# 3. 定义互补度计算和贪心选组函数
# ------------------------------
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

# ------------------------------
# 4. 遍历各 (alpha,beta) 计算 C_group
# ------------------------------
results_dict = {}
print("\n>>> 计算不同 (alpha, beta) 下的互补度 …")
for a in alphas:
    for b in betas:
        key = f"alpha={a},beta={b}"
        c_list = []
        for win, subdf in df_norm_all.groupby("window_id"):
            candidates = subdf["thread"].tolist()
            if len(candidates) < k:
                continue
            _, sc = greedy_select_norm(subdf, candidates, k, resource_cols_norm, a, b)
            c_list.append(sc)
        results_dict[key] = c_list
        print(f"  {key} 计算了 {len(c_list)} 个窗口的 C_group")

# ------------------------------
# 5. 绘制并保存直方图到 ../results/alpha_beta 文件夹
# ------------------------------
output_dir = "../results/alpha_beta"
os.makedirs(output_dir, exist_ok=True)
output_png = os.path.join(output_dir, "alpha_beta_hist.png")

plt.figure(figsize=(10, 6))
for key, c_vals in results_dict.items():
    plt.hist(c_vals,
             bins=30,
             alpha=0.4,
             density=True,
             label=key)
plt.xlabel("C_group（互补度）")
plt.ylabel("频率密度")
plt.title(f"k={k} 下，不同 (alpha, beta) 互补度分布对比")
plt.legend(fontsize=8, loc="upper right")
plt.grid(linestyle="--", alpha=0.3)
plt.tight_layout()

plt.savefig(output_png)
print(f"\n>>> 直方图已保存到：{output_png}")

# plt.show()  # 如果需要在本地环境弹窗显示，可取消注释

# ------------------------------
# 6. 打印各组 (alpha,beta) 统计量
# ------------------------------
print("\n>>> 各组 (alpha,beta) 的互补度统计量：")
for key, c_vals in results_dict.items():
    desc = pd.Series(c_vals).describe(percentiles=[0.25, 0.5, 0.75]).round(3)
    print(f"\n{key} 的 C_group 统计量：\n{desc}")
