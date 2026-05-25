#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export demo result files with presentation-friendly Chinese file names.

This script reads demo_results_pretty/ and writes demo_results_named/.
It does not rename pipeline files under data/, results/, or models/, so the
reproduction scripts keep working.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import joblib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "demo_results_pretty"
DST = ROOT / "demo_results_named"


FILE_MAP = {
    "prediction/regression_metrics.csv": "01_XGBoost预测_回归误差指标.csv",
    "prediction/regression_metrics.txt": "01_XGBoost预测_回归误差指标_对齐版.txt",
    "prediction/classification_metrics.csv": "02_XGBoost预测_受限状态分类指标.csv",
    "prediction/classification_metrics.txt": "02_XGBoost预测_受限状态分类指标_对齐版.txt",
    "prediction/confusion_matrix.csv": "03_XGBoost预测_状态混淆矩阵.csv",
    "prediction/confusion_matrix.txt": "03_XGBoost预测_状态混淆矩阵_对齐版.txt",
    "processed/thread_windows_norm.csv": "04_线程画像_100ms窗口7维特征.csv",
    "processed/thread_windows_norm.txt": "04_线程画像_100ms窗口7维特征_对齐版.txt",
    "processed/thread_predictions.csv": "05_XGBoost预测_下一窗口特征明细.csv",
    "processed/thread_predictions.txt": "05_XGBoost预测_下一窗口特征明细_对齐版.txt",
    "processed/magm_schedule.csv": "06_MAGM调度_线程到CPU决策.csv",
    "processed/magm_schedule.txt": "06_MAGM调度_线程到CPU决策_对齐版.txt",
    "processed/final_cpu_selection.csv": "07_最终选核_线程逻辑CPU明细.csv",
    "processed/final_cpu_selection.txt": "07_最终选核_线程逻辑CPU明细_对齐版.txt",
    "processed/final_core_pairs.csv": "08_最终选核_SMT物理核配对.csv",
    "processed/final_core_pairs.txt": "08_最终选核_SMT物理核配对_对齐版.txt",
    "scheduler/magm_window_summary.csv": "09_MAGM调度_窗口级统计.csv",
    "scheduler/magm_window_summary.txt": "09_MAGM调度_窗口级统计_对齐版.txt",
    "scheduler/final_window_selection.csv": "10_最终选核_各场景最后窗口.csv",
    "scheduler/final_window_selection.txt": "10_最终选核_各场景最后窗口_对齐版.txt",
    "scheduler/cpu_selection_summary.csv": "11_最终选核_场景汇总统计.csv",
    "scheduler/cpu_selection_summary.txt": "11_最终选核_场景汇总统计_对齐版.txt",
    "scheduler/live_affinity_report.csv": "12_真实验证_sched_setaffinity绑核结果.csv",
    "scheduler/live_affinity_report.txt": "12_真实验证_sched_setaffinity绑核结果_对齐版.txt",
    "scheduler/affinity_dry_run_report.csv": "13_安全检查_历史TID绑核DryRun.csv",
    "scheduler/affinity_dry_run_report.txt": "13_安全检查_历史TID绑核DryRun_对齐版.txt",
}


README_TEXT = """# 中文命名演示结果

本目录用于给老师或答辩现场展示。文件名已经按实验流程重新命名，并保留了序号。

## 推荐展示顺序

1. `01_XGBoost预测_回归误差指标_对齐版.txt`
2. `02_XGBoost预测_受限状态分类指标_对齐版.txt`
3. `08_最终选核_SMT物理核配对_对齐版.txt`
4. `10_最终选核_各场景最后窗口_对齐版.txt`
5. `12_真实验证_sched_setaffinity绑核结果_对齐版.txt`

## 文件命名说明

- `01-05`：第 4 章线程画像与 XGBoost 预测结果。
- `06-11`：第 5 章 MAGM 调度与最终选核结果。
- `12`：用户态真实绑核验证结果。
- `13`：历史 TID 安全 dry-run 检查。
- `14`：使用完整数据重新训练得到的最终 XGBoost 模型。

`*.csv` 适合用表格软件打开，`*_对齐版.txt` 适合直接用编辑器或终端展示。
"""


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(f"Cannot find {SRC}; run scripts/format_demo_results.py first")
    DST.mkdir(parents=True, exist_ok=True)

    for rel_src, dst_name in FILE_MAP.items():
        src_file = SRC / rel_src
        if src_file.exists():
            shutil.copy2(src_file, DST / dst_name)

    full_model = ROOT / "models" / "thread_predictors_full.joblib"
    if full_model.exists():
        shutil.copy2(full_model, DST / "14_最终模型_XGBoost全量训练模型.joblib")
        meta = joblib.load(full_model)
        model_info = [
            "# 最终模型说明",
            "",
            f"- 模型类型：{meta.get('model_type')}",
            f"- 训练范围：{meta.get('training_scope')}",
            f"- 历史窗口长度：{meta.get('hist_len')}",
            f"- 总训练序列数：{meta.get('total_sequences')}",
            f"- 输入特征：{', '.join(meta.get('feature_cols', []))}",
            f"- 数据来源：{meta.get('source')}",
            "",
            "该模型是在评估流程完成后，使用全部可用窗口序列重新训练得到的最终交付模型。",
        ]
        (DST / "14_最终模型_XGBoost全量训练模型说明.md").write_text(
            "\n".join(model_info) + "\n",
            encoding="utf-8",
        )

    (DST / "README.md").write_text(README_TEXT, encoding="utf-8")

    print(f"Generated named demo results under: {DST}")
    for path in sorted(DST.iterdir()):
        if path.is_file():
            print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
