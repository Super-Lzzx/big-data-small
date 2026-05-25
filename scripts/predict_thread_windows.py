#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run next-window prediction with an already trained model.

This is the live-demo inference path: it does not retrain XGBoost. It loads
models/thread_predictors.joblib, builds N=hist_len sliding-window sequences from
the latest thread_windows_norm.csv, and writes thread_predictions.csv for MAGM.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    mean_absolute_error,
)

from train_thread_predictor import (
    BASE_FEATURES,
    FEATURE_COLS,
    LABELS,
    build_sequences,
    derive_state_from_matrix,
    project_root,
    rmse_score,
)


def main() -> None:
    root = project_root()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=root / "data" / "processed" / "thread_windows_norm.csv",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=root / "models" / "thread_predictors.joblib",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Cannot find {args.input}; run build_thread_windows.py first")
    if not args.model_path.exists():
        raise FileNotFoundError(f"Cannot find {args.model_path}; train the predictor first")

    bundle = joblib.load(args.model_path)
    hist_len = int(bundle["hist_len"])
    x_cols = list(bundle["x_cols"])
    models = bundle["models"]

    df = pd.read_csv(args.input)
    seq = build_sequences(df, hist_len)
    if seq.empty:
        raise ValueError("Not enough per-thread history to build prediction sequences")

    missing_x = sorted(set(x_cols) - set(seq.columns))
    if missing_x:
        raise ValueError(f"Input sequences are missing model features: {missing_x}")

    y_cols = [f"y_{c}" for c in FEATURE_COLS]
    x = seq[x_cols].to_numpy(dtype=float)
    pred = np.zeros((len(seq), len(y_cols)), dtype=float)
    latency_us = []

    for idx, y_col in enumerate(y_cols):
        if y_col not in models:
            raise ValueError(f"Model bundle is missing regressor for {y_col}")
        start = time.perf_counter()
        pred[:, idx] = models[y_col].predict(x)
        elapsed = time.perf_counter() - start
        latency_us.append(elapsed / max(len(x), 1) * 1_000_000)

    pred = np.clip(pred, 0.0, 1.0)
    y_true = seq[y_cols].to_numpy(dtype=float)
    state_pred = derive_state_from_matrix(pred)
    state_true = seq["state_true"].to_numpy()

    rows = []
    for idx, feature in enumerate(BASE_FEATURES):
        rows.append(
            {
                "feature": feature,
                "RMSE": rmse_score(y_true[:, idx], pred[:, idx]),
                "MAE": mean_absolute_error(y_true[:, idx], pred[:, idx]),
            }
        )
    rows.append(
        {
            "feature": "AVG",
            "RMSE": rmse_score(y_true, pred),
            "MAE": mean_absolute_error(y_true, pred),
        }
    )
    reg_metrics = pd.DataFrame(rows)

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

    pred_df = seq[
        ["LoadType", "thread_key", "thread", "pid", "cpu", "window_id", "state_true"]
    ].copy()
    pred_df["split"] = "live"
    for col, values in zip(FEATURE_COLS, y_true.T):
        pred_df[f"true_{col}"] = values
    for col, values in zip(FEATURE_COLS, pred.T):
        pred_df[f"pred_{col}"] = values
    pred_df["state_pred"] = state_pred

    out_data = root / "data" / "processed"
    out_results = root / "results" / "prediction"
    out_results.mkdir(parents=True, exist_ok=True)

    pred_path = out_data / "thread_predictions.csv"
    reg_path = out_results / "regression_metrics.csv"
    cls_path = out_results / "classification_metrics.csv"
    cm_path = out_results / "confusion_matrix.csv"

    pred_df.to_csv(pred_path, index=False)
    reg_metrics.to_csv(reg_path, index=False)
    cls_metrics.to_csv(cls_path, index=False)
    pd.DataFrame(
        confusion_matrix(state_true, state_pred, labels=LABELS),
        index=[f"true_{x}" for x in LABELS],
        columns=[f"pred_{x}" for x in LABELS],
    ).to_csv(cm_path)

    print(f"Loaded model: {args.model_path}")
    print(f"Model type: {bundle.get('model_type')}")
    print(f"Hist len: {hist_len}")
    print(f"Prediction sequences: {len(seq)}")
    print(f"Mean prediction latency: {np.mean(latency_us):.3f} us/sample")
    print("Regression metrics:")
    print(reg_metrics.round(4).to_string(index=False))
    print("Classification metrics:")
    print(cls_metrics.round(4).to_string(index=False))
    print(f"Saved: {pred_path}")
    print(f"Saved: {reg_path}")
    print(f"Saved: {cls_path}")
    print(f"Saved: {cm_path}")


if __name__ == "__main__":
    main()
