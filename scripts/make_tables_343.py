#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成论文第 3.4.3 小节所需的三张表：
- 表 3.5：数据集规模与覆盖情况（按 LoadType）
- 表 3.6：不同 LoadType 下关键指标统计
- 表 3.7：SMT 线程组合构建情况

使用的数据文件：
- ../data/processed/cpu_thread_attributed.csv
- ../data/processed/all_windows_best_groups_cross_load.csv
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ===================== 配置区 =====================

CPU_THREAD_FILE = Path("../data/processed/full_dataset.csv")
SMT_GROUP_FILE = Path("../data/processed/all_windows_best_groups_cross_load.csv")

# 时间窗长度（单位：秒）——根据你实际的窗口长度改
WINDOW_DURATION_S = 0.1  # 100ms 就写 0.1，10ms 就写 0.01


# ===================== 帮助函数 =====================

def find_first_existing_column(df: pd.DataFrame, candidates):
    """在 DataFrame 中按候选列表顺序寻找第一个存在的列名。"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ===================== 表 3.5：数据集规模与覆盖情况 =====================

def build_table_35():
    if not CPU_THREAD_FILE.exists():
        raise FileNotFoundError(f"找不到线程级数据文件：{CPU_THREAD_FILE}")

    df = pd.read_csv(CPU_THREAD_FILE)
    print("cpu_thread_attributed 列名：", df.columns.tolist())

    # 1）线程 ID
    tid_col = find_first_existing_column(df, ["tid", "thread_id", "thread"])
    if tid_col is None:
        df["tid"] = np.arange(len(df))
        tid_col = "tid"
        print("警告：未找到 tid/thread_id 列，临时用行号代替线程 ID。")
    elif tid_col != "tid":
        df = df.rename(columns={tid_col: "tid"})
        tid_col = "tid"

    # 2）用 LoadType 作为场景列
    scene_source_col = find_first_existing_column(
        df,
        ["scene", "LoadType", "load_type", "cgroup", "C_group", "comm", "workload", "group"]
    )
    if scene_source_col is None:
        df["scene"] = "all"
        print("提示：未找到 LoadType/scene，所有样本归为场景 'all'。")
    else:
        if scene_source_col != "scene":
            df = df.rename(columns={scene_source_col: "scene"})
        # 可以这里统一改成更好看的名字，比如 cpu → cpu-stress
        df["scene"] = df["scene"].astype(str).replace({
            "cpu": "cpu-stress",
            "mem": "mem-stress",
            "io": "io-stress",
            "mixed": "mixed-stress",
        })

    # 3）时间窗长度
    df["win_duration_s"] = float(WINDOW_DURATION_S)

    # 4）按场景统计
    group = df.groupby("scene", dropna=False)

    table_35 = group.agg(
        线程数=("tid", "nunique"),
        时间窗样本数=("tid", "size"),
        累计运行时长_s=("win_duration_s", "sum")
    ).reset_index()

    table_35 = table_35.rename(columns={
        "scene": "场景类型",
        "累计运行时长_s": "累计运行时长 / s"
    })
    table_35["累计运行时长 / s"] = table_35["累计运行时长 / s"].round(1)

    # 5）增加“合计”行
    total_row = {
        "场景类型": "合计",
        "线程数": int(table_35["线程数"].sum()),
        "时间窗样本数": int(table_35["时间窗样本数"].sum()),
        "累计运行时长 / s": float(table_35["累计运行时长 / s"].sum().round(1)),
    }
    table_35 = pd.concat([table_35, pd.DataFrame([total_row])], ignore_index=True)

    out_path = Path("table_3_5_dataset_scale.csv")
    table_35.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n表 3.5 已写入：{out_path}")
    print(table_35)


# ===================== 表 3.6：关键指标统计 =====================

def build_table_36():
    if not CPU_THREAD_FILE.exists():
        raise FileNotFoundError(f"找不到线程级数据文件：{CPU_THREAD_FILE}")

    df = pd.read_csv(CPU_THREAD_FILE)
    print("\n用于指标统计的列名：", df.columns.tolist())

    # 事件列映射（用你现在的 header）
    rename_map = {
        "instructions": "instructions",
        "cpu_cycles": "cpu_cycles",
        "cache_misses": "cache_misses",
        "L1_icache_miss": "L1_icache_miss",
        "L1_dcache_miss": "L1_dcache_miss",
        "L2_cache_miss": "L2_cache_miss",
        "branch_instrs": "branch_instrs",
        "branch_misses": "branch_misses",
        "ITLB_misses": "ITLB_misses",
        "DTLB_misses": "DTLB_misses",
        "LoadType": "scene",
        "scene": "scene",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "scene" in df.columns:
        df["scene"] = df["scene"].astype(str).replace({
            "cpu": "cpu-stress",
            "mem": "mem-stress",
            "io": "io-stress",
            "mixed": "mixed-stress",
        })
    else:
        df["scene"] = "all"

    # 缺的事件列补 0
    for col in [
        "instructions", "cpu_cycles", "cache_misses",
        "L1_icache_miss", "L1_dcache_miss", "L2_cache_miss",
        "branch_instrs", "branch_misses"
    ]:
        if col not in df.columns:
            df[col] = 0

    eps = 1e-9
    inst_k = df["instructions"] / 1000.0 + eps

    df["IPC"] = df["instructions"] / (df["cpu_cycles"] + eps)
    df["MPKI_LLC"] = df["cache_misses"] / inst_k
    df["MPKI_L1I"] = df["L1_icache_miss"] / inst_k
    df["MPKI_L1D"] = df["L1_dcache_miss"] / inst_k
    df["MPKI_L2"] = df["L2_cache_miss"] / inst_k
    df["BrMPKI"] = df["branch_misses"] / inst_k

    metrics = ["IPC", "MPKI_L1I", "MPKI_L1D", "MPKI_L2", "MPKI_LLC", "BrMPKI"]

    g = df.groupby("scene", dropna=False)

    rows = []
    for scene_val, grp in g:
        row = {
            "场景类型": scene_val,
            "样本数": int(len(grp)),
        }
        for m in metrics:
            s = grp[m].replace([np.inf, -np.inf], np.nan).dropna()
            row[m + "_均值"] = float(s.mean()) if len(s) > 0 else np.nan
            row[m + "_中位数"] = float(s.median()) if len(s) > 0 else np.nan
        rows.append(row)

    table_36 = pd.DataFrame(rows)

    table_36_simple = table_36[[
        "场景类型",
        "样本数",
        "IPC_均值",
        "IPC_中位数",
        "MPKI_LLC_均值",
        "MPKI_L1I_均值",
        "MPKI_L1D_均值",
        "BrMPKI_均值",
    ]]

    for col in table_36_simple.columns:
        if "均值" in col or "中位数" in col:
            table_36_simple[col] = table_36_simple[col].round(3)

    out_path = Path("table_3_6_metric_stats.csv")
    table_36_simple.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n表 3.6 已写入：{out_path}")
    print(table_36_simple)


# ===================== 表 3.7：SMT 线程组合构建结果 =====================

def build_table_37():
    if not SMT_GROUP_FILE.exists():
        raise FileNotFoundError(f"找不到 SMT 组合文件：{SMT_GROUP_FILE}")

    df_pair = pd.read_csv(SMT_GROUP_FILE)
    print("\nall_windows_best_groups_cross_load 列名：", df_pair.columns.tolist())
    print(df_pair.head())

    # 统一列名
    col_map = {}
    if "window_id" in df_pair.columns:
        col_map["window_id"] = "window_id"
    if "best_group" in df_pair.columns:
        col_map["best_group"] = "best_group"
    if "C_group" in df_pair.columns:
        col_map["C_group"] = "score"
    elif "score" in df_pair.columns:
        col_map["score"] = "score"

    df_pair = df_pair.rename(columns=col_map)

    if "window_id" not in df_pair.columns:
        df_pair["window_id"] = np.arange(len(df_pair))
    if "score" not in df_pair.columns:
        last_col = df_pair.columns[-1]
        df_pair = df_pair.rename(columns={last_col: "score"})

    if "best_group" not in df_pair.columns:
        df_pair["best_group"] = ""
    df_pair["best_group"] = df_pair["best_group"].astype(str)
    df_pair["组合中线程数"] = df_pair["best_group"].str.count("Thread")

    # 只统计真正的 SMT 组合
    df_pair_valid = df_pair[df_pair["组合中线程数"] >= 2].copy()

    g2 = df_pair_valid.groupby("组合中线程数", dropna=False)

    table_37 = g2.agg(
        窗口数=("window_id", "size"),
        平均得分=("score", "mean"),
        得分最小值=("score", "min"),
        得分最大值=("score", "max"),
    ).reset_index()

    table_37[["平均得分", "得分最小值", "得分最大值"]] = table_37[
        ["平均得分", "得分最小值", "得分最大值"]
    ].round(3)

    out_path = Path("table_3_7_smt_groups.csv")
    table_37.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n表 3.7 已写入：", out_path)
    print(table_37)


# ===================== 主入口 =====================

if __name__ == "__main__":
    print("开始生成 3.4.3 三张表 ...")
    build_table_35()
    build_table_36()
    build_table_37()
    print("\n全部完成。")
