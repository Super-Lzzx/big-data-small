#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create presentation-friendly result tables.

The original CSV files remain unchanged. This script writes:
  demo_results_pretty/**/*.csv  with Chinese explanations in headers
  demo_results_pretty/**/*.txt  aligned plain-text tables
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "demo_results"
DST = ROOT / "demo_results_pretty"


COLUMN_MAP = {
    "LoadType": "LoadType(负载场景)",
    "window_id": "window_id(时间窗口ID)",
    "mode": "mode(调度模式:CE独占/SP配对)",
    "thread_key": "thread_key(线程唯一标识)",
    "thread": "thread(线程名)",
    "pid": "pid(线程/进程ID)",
    "target_cpu": "target_cpu(目标逻辑CPU)",
    "paired_with": "paired_with(配对线程)",
    "score": "score(互补性得分)",
    "rho": "rho(平滑负载率)",
    "n_run": "n_run(可运行线程数)",
    "physical_core": "physical_core(物理核编号)",
    "smt_slot": "smt_slot(SMT槽位)",
    "selected_thread": "selected_thread(被选线程)",
    "cpu_slot0": "cpu_slot0(SMT槽0逻辑CPU)",
    "cpu_slot1": "cpu_slot1(SMT槽1逻辑CPU)",
    "slot0_thread": "slot0_thread(SMT槽0线程)",
    "slot1_thread": "slot1_thread(SMT槽1线程)",
    "feature": "feature(预测特征)",
    "RMSE": "RMSE(均方根误差)",
    "MAE": "MAE(平均绝对误差)",
    "label": "label(状态标签)",
    "precision": "precision(精确率)",
    "recall": "recall(召回率)",
    "f1": "f1(F1分数)",
    "support": "support(样本数)",
    "tid": "tid(实时线程ID)",
    "comm": "comm(实时线程名)",
    "status": "status(执行状态)",
    "reason": "reason(跳过/失败原因)",
    "affinity_before": "affinity_before(绑定前CPU集合)",
    "affinity_after": "affinity_after(绑定后CPU集合)",
    "pairs": "pairs(配对数量)",
    "bound_threads": "bound_threads(已绑定线程数)",
    "windows": "windows(窗口数量)",
    "selected_threads": "selected_threads(被选线程数)",
    "physical_cores_used": "physical_cores_used(使用物理核数)",
    "avg_rho": "avg_rho(平均负载率)",
    "avg_score": "avg_score(平均互补得分)",
}


FEATURE_VALUE_MAP = {
    "IPC": "IPC(每周期指令数)",
    "MPKI_LLC": "MPKI_LLC(末级缓存每千指令未命中)",
    "MPKI_L1I": "MPKI_L1I(L1指令缓存每千指令未命中)",
    "MPKI_L1D": "MPKI_L1D(L1数据缓存每千指令未命中)",
    "MPKI_L2": "MPKI_L2(L2缓存每千指令未命中)",
    "BrMPKI": "BrMPKI(分支预测失败每千指令数)",
    "MPKI_TLB": "MPKI_TLB(TLB每千指令未命中)",
    "AVG": "AVG(平均值)",
}


LABEL_VALUE_MAP = {
    "FE-Bound": "FE-Bound(前端受限)",
    "BE-Core": "BE-Core(后端核心受限)",
    "BE-Mem": "BE-Mem(后端访存受限)",
    "macro_avg": "macro_avg(宏平均)",
    "accuracy": "accuracy(准确率)",
}


MODE_VALUE_MAP = {
    "CE": "CE(物理核独占)",
    "SP": "SP(SMT互补配对)",
}


def prettify_values(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "feature" in out.columns:
        out["feature"] = out["feature"].map(lambda x: FEATURE_VALUE_MAP.get(str(x), x))
    if "label" in out.columns:
        out["label"] = out["label"].map(lambda x: LABEL_VALUE_MAP.get(str(x), x))
    if "mode" in out.columns:
        out["mode"] = out["mode"].map(lambda x: MODE_VALUE_MAP.get(str(x), x))
    return out


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={col: COLUMN_MAP.get(col, col) for col in df.columns})


def format_float_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{x:.6f}")
    return out.fillna("")


def write_pretty_table(src_file: Path) -> None:
    rel = src_file.relative_to(SRC)
    out_csv = (DST / rel).with_suffix(".csv")
    out_txt = (DST / rel).with_suffix(".txt")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(src_file)
    pretty = rename_columns(prettify_values(df))
    pretty = format_float_columns(pretty)

    # utf-8-sig helps common spreadsheet software open Chinese headers cleanly.
    pretty.to_csv(out_csv, index=False, encoding="utf-8-sig")
    out_txt.write_text(pretty.to_string(index=False), encoding="utf-8")


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(f"Cannot find {SRC}; run demo generation first")
    for csv_file in sorted(SRC.rglob("*.csv")):
        write_pretty_table(csv_file)

    readme = DST / "README.md"
    readme.write_text(
        "# 展示版结果\n\n"
        "本目录由 `scripts/format_demo_results.py` 生成。\n\n"
        "- `*.csv`：带中文含义的表头，适合用 WPS/Excel/LibreOffice 打开。\n"
        "- `*.txt`：等宽对齐文本，适合直接在编辑器或终端展示。\n\n"
        "原始结果仍保留在 `demo_results/`。\n",
        encoding="utf-8",
    )
    print(f"Generated pretty result tables under: {DST}")
    print("Files:")
    for path in sorted(DST.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
