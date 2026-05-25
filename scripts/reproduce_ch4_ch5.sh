#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

python3 scripts/build_thread_windows.py
python3 scripts/train_thread_predictor.py
python3 scripts/offline_magm_scheduler.py
python3 scripts/export_cpu_selection.py

echo
echo "Reproduction outputs:"
echo "  data/processed/thread_windows_norm.csv"
echo "  data/processed/thread_predictions.csv"
echo "  data/processed/magm_schedule.csv"
echo "  data/processed/final_cpu_selection.csv"
echo "  data/processed/final_core_pairs.csv"
echo "  results/prediction/regression_metrics.csv"
echo "  results/prediction/classification_metrics.csv"
echo "  results/scheduler/magm_window_summary.csv"
echo "  results/scheduler/final_window_selection.csv"
echo "  results/scheduler/cpu_selection_summary.csv"
