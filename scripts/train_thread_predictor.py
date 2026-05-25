#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Train the chapter-4 multi-output next-window predictor.

The thesis uses seven independent XGBoost regressors. This script uses XGBoost
when the package is installed; otherwise it falls back to sklearn's gradient
boosting regressor so the reproduction pipeline remains runnable offline.

Inputs:
  data/processed/thread_windows_norm.csv

Outputs:
  models/thread_predictors.joblib
  data/processed/thread_predictions.csv
  results/prediction/regression_metrics.csv
  results/prediction/classification_metrics.csv
  results/prediction/confusion_matrix.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
)


# 论文第 4 章使用的 7 维归一化微架构特征，顺序会影响模型输入和状态派生逻辑。
FEATURE_COLS = [
    "IPC_norm",
    "MPKI_LLC_norm",
    "MPKI_L1I_norm",
    "MPKI_L1D_norm",
    "MPKI_L2_norm",
    "BrMPKI_norm",
    "MPKI_TLB_norm",
]

BASE_FEATURES = [c.removesuffix("_norm") for c in FEATURE_COLS]
LABELS = ["FE-Bound", "BE-Core", "BE-Mem"]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def rmse_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def make_model(model_type: str):
    if model_type == "xgboost":
        try:
            from xgboost import XGBRegressor
        except Exception as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("xgboost is not installed") from exc
        return XGBRegressor(
            # 对应论文表 4.3：较低学习率 + 100 棵树，在精度和在线推理开销之间折中。
            n_estimators=100,
            learning_rate=0.05,
            max_depth=5,
            # 下面三项用于抑制 PMU 采样噪声和异常窗口带来的过拟合。
            min_child_weight=3,
            gamma=0.1,
            reg_lambda=1.5,
            # 行采样和列采样增强泛化能力，避免模型过度依赖单一窗口或单一特征。
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            n_jobs=1,
            random_state=42,
        )
    if model_type == "gbr":
        return GradientBoostingRegressor(
            n_estimators=60,
            learning_rate=0.05,
            max_depth=3,
            min_samples_leaf=3,
            subsample=0.8,
            random_state=42,
        )
    if model_type == "linear":
        return LinearRegression()
    raise ValueError(f"Unknown model type: {model_type}")


def choose_model_type(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import xgboost  # noqa: F401
        return "xgboost"
    except Exception:
        # 没有安装 xgboost 时使用 sklearn 的 GBR，保证离线复现实验仍能跑通。
        return "gbr"


def derive_state_from_matrix(values: np.ndarray) -> np.ndarray:
    # 将连续的 7 维预测向量重新映射为 Top-Down 受限状态标签，用于分类指标评估。
    ipc = values[:, 0]
    mpki_llc = values[:, 1]
    mpki_l1i = values[:, 2]
    brmpki = values[:, 5]
    mpki_tlb = values[:, 6]

    s_fe = 0.75 * brmpki + 0.25 * mpki_l1i
    s_core = 0.80 * ipc + 0.20 * (1.0 - mpki_llc)
    s_mem = 0.80 * mpki_llc + 0.20 * mpki_tlb

    labels = []
    for fe, core, mem in zip(s_fe, s_core, s_mem):
        if mem >= core and mem >= fe:
            labels.append("BE-Mem")
        elif core >= fe:
            labels.append("BE-Core")
        else:
            labels.append("FE-Bound")
    return np.array(labels)


def build_sequences(df: pd.DataFrame, hist_len: int) -> pd.DataFrame:
    rows = []
    sort_cols = ["LoadType", "thread_key", "window_id"]
    df = df.sort_values(sort_cols).reset_index(drop=True)

    for thread_key, grp in df.groupby("thread_key", sort=False):
        grp = grp.sort_values("window_id").reset_index(drop=True)
        if len(grp) <= hist_len:
            continue
        feature_values = grp[FEATURE_COLS].to_numpy(dtype=float)
        for pos in range(hist_len, len(grp)):
            # 使用连续 hist_len 个历史窗口预测当前位置窗口，默认 hist_len=5 对应论文 N=5。
            # reshape(-1) 将 [历史窗口数, 7 维特征] 展平成 XGBoost 可接受的一维输入。
            hist = feature_values[pos - hist_len : pos].reshape(-1)
            target = feature_values[pos]
            row = {
                "thread_key": thread_key,
                "LoadType": grp.loc[pos, "LoadType"],
                "thread": grp.loc[pos, "thread"],
                "pid": int(grp.loc[pos, "pid"]),
                "cpu": int(grp.loc[pos, "cpu"]),
                "window_id": int(grp.loc[pos, "window_id"]),
                "state_true": grp.loc[pos, "state_label"],
                "seq_pos": pos,
                "seq_len": len(grp),
            }
            for i, val in enumerate(hist):
                row[f"x_{i}"] = val
            for col, val in zip(FEATURE_COLS, target):
                # 每个 y_* 都会训练一个独立回归器，最终拼接成 7 维下一窗口预测向量。
                row[f"y_{col}"] = val
            rows.append(row)
    return pd.DataFrame(rows)


def add_split_column(seq: pd.DataFrame) -> pd.DataFrame:
    seq = seq.copy()
    split = []
    for _, row in seq.iterrows():
        # 按每个线程自身的时间顺序切分，避免随机划分造成未来窗口信息泄漏。
        ratio = row["seq_pos"] / max(row["seq_len"] - 1, 1)
        if ratio < 0.8:
            split.append("train")
        elif ratio < 0.9:
            split.append("valid")
        else:
            split.append("test")
    seq["split"] = split
    return seq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=project_root() / "data" / "processed" / "thread_windows_norm.csv",
    )
    parser.add_argument("--hist-len", type=int, default=5)
    parser.add_argument(
        "--model",
        choices=["auto", "xgboost", "gbr", "linear"],
        default="auto",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Cannot find {args.input}; run build_thread_windows.py first")
    df = pd.read_csv(args.input)
    missing = sorted(set(FEATURE_COLS + ["thread_key", "window_id", "state_label"]) - set(df.columns))
    if missing:
        raise ValueError(f"{args.input} is missing required columns: {missing}")

    seq = build_sequences(df, args.hist_len)
    if seq.empty:
        raise ValueError("Not enough per-thread history to build prediction sequences")
    seq = add_split_column(seq)

    x_cols = [c for c in seq.columns if c.startswith("x_")]
    y_cols = [f"y_{c}" for c in FEATURE_COLS]

    train = seq[seq["split"].isin(["train", "valid"])]
    test = seq[seq["split"] == "test"]
    if train.empty or test.empty:
        raise ValueError("Train/test split is empty; collect longer per-thread series")

    model_type = choose_model_type(args.model)
    models = {}
    pred = np.zeros((len(test), len(y_cols)), dtype=float)
    latency_us = []

    x_train = train[x_cols].to_numpy(dtype=float)
    x_test = test[x_cols].to_numpy(dtype=float)

    for idx, y_col in enumerate(y_cols):
        # 独立多路预测：7 个目标维度分别训练 7 个回归模型
        model = make_model(model_type)
        model.fit(x_train, train[y_col].to_numpy(dtype=float))
        models[y_col] = model

        start = time.perf_counter()
        pred[:, idx] = model.predict(x_test)
        elapsed = time.perf_counter() - start
        latency_us.append(elapsed / max(len(x_test), 1) * 1_000_000)

    # 训练目标是归一化特征，预测值裁剪回 [0, 1]，便于后续互补性评分直接使用。
    pred = np.clip(pred, 0.0, 1.0)
    y_true = test[y_cols].to_numpy(dtype=float)
    state_pred = derive_state_from_matrix(pred)
    state_true = test["state_true"].to_numpy()

    # 回归层面：逐维输出 RMSE/MAE，并额外给出所有特征的平均误差。
    rows = []
    for idx, feature in enumerate(BASE_FEATURES):
        rmse = rmse_score(y_true[:, idx], pred[:, idx])
        mae = mean_absolute_error(y_true[:, idx], pred[:, idx])
        rows.append({"feature": feature, "RMSE": rmse, "MAE": mae})
    rows.append(
        {
            "feature": "AVG",
            "RMSE": rmse_score(y_true, pred),
            "MAE": mean_absolute_error(y_true, pred),
        }
    )
    reg_metrics = pd.DataFrame(rows)

    # 语义层面：把预测向量派生为 FE-Bound / BE-Core / BE-Mem 后评估分类效果。
    report = classification_report(
        state_true,
        state_pred,
        labels=LABELS,
        output_dict=True,
        zero_division=0,
    )
    cls_rows = []
    for label in LABELS:
        cls_rows.append(
            {
                "label": label,
                "precision": report[label]["precision"],
                "recall": report[label]["recall"],
                "f1": report[label]["f1-score"],
                "support": report[label]["support"],
            }
        )
    cls_rows.append(
        {
            "label": "macro_avg",
            "precision": report["macro avg"]["precision"],
            "recall": report["macro avg"]["recall"],
            "f1": report["macro avg"]["f1-score"],
            "support": report["macro avg"]["support"],
        }
    )
    cls_rows.append(
        {
            "label": "accuracy",
            "precision": accuracy_score(state_true, state_pred),
            "recall": accuracy_score(state_true, state_pred),
            "f1": accuracy_score(state_true, state_pred),
            "support": len(state_true),
        }
    )
    cls_metrics = pd.DataFrame(cls_rows)

    # 保存测试集逐窗口明细，供后续 MAGM 调度脚本读取 pred_* 特征列。
    pred_df = test[
        ["LoadType", "thread_key", "thread", "pid", "cpu", "window_id", "state_true", "split"]
    ].copy()
    for col, values in zip(FEATURE_COLS, y_true.T):
        pred_df[f"true_{col}"] = values
    for col, values in zip(FEATURE_COLS, pred.T):
        pred_df[f"pred_{col}"] = values
    pred_df["state_pred"] = state_pred

    root = project_root()
    out_data = root / "data" / "processed"
    out_results = root / "results" / "prediction"
    out_models = root / "models"
    out_results.mkdir(parents=True, exist_ok=True)
    out_models.mkdir(parents=True, exist_ok=True)

    pred_path = out_data / "thread_predictions.csv"
    reg_path = out_results / "regression_metrics.csv"
    cls_path = out_results / "classification_metrics.csv"
    cm_path = out_results / "confusion_matrix.csv"
    model_path = out_models / "thread_predictors.joblib"
    full_model_path = out_models / "thread_predictors_full.joblib"

    pred_df.to_csv(pred_path, index=False)
    reg_metrics.to_csv(reg_path, index=False)
    cls_metrics.to_csv(cls_path, index=False)
    pd.DataFrame(
        confusion_matrix(state_true, state_pred, labels=LABELS),
        index=[f"true_{x}" for x in LABELS],
        columns=[f"pred_{x}" for x in LABELS],
    ).to_csv(cm_path)
    # joblib 中保留模型、特征顺序和历史窗口长度，方便在线/离线预测阶段一致加载。
    joblib.dump(
        {
            "model_type": model_type,
            "hist_len": args.hist_len,
            "feature_cols": FEATURE_COLS,
            "x_cols": x_cols,
            "models": models,
            "training_scope": "train_valid_split",
            "train_sequences": int(len(train)),
            "test_sequences": int(len(test)),
            "mean_prediction_latency_us": float(np.mean(latency_us)),
        },
        model_path,
    )

    # 最终交付模型：在评估完成后，用全部历史序列重新训练一份模型，供演示/部署加载。
    full_models = {}
    x_all = seq[x_cols].to_numpy(dtype=float)
    for y_col in y_cols:
        model = make_model(model_type)
        model.fit(x_all, seq[y_col].to_numpy(dtype=float))
        full_models[y_col] = model
    joblib.dump(
        {
            "model_type": model_type,
            "hist_len": args.hist_len,
            "feature_cols": FEATURE_COLS,
            "x_cols": x_cols,
            "models": full_models,
            "training_scope": "full_dataset",
            "total_sequences": int(len(seq)),
            "source": str(args.input),
        },
        full_model_path,
    )

    print(f"Model type: {model_type}")
    print(f"Sequences: total={len(seq)}, train+valid={len(train)}, test={len(test)}")
    print(f"Mean prediction latency: {np.mean(latency_us):.3f} us/sample")
    print("Regression metrics:")
    print(reg_metrics.round(4).to_string(index=False))
    print("Classification metrics:")
    print(cls_metrics.round(4).to_string(index=False))
    print(f"Saved: {model_path}")
    print(f"Saved full-data model: {full_model_path}")
    print(f"Saved: {pred_path}")
    print(f"Saved: {reg_path}")
    print(f"Saved: {cls_path}")
    print(f"Saved: {cm_path}")


if __name__ == "__main__":
    main()
