#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [[ "${LIVE_COLLECT:-0}" == "1" ]]; then
    DEMO_SCENES="${DEMO_SCENES:-mixed}"
    COLLECT_SECONDS="${COLLECT_SECONDS:-10}"
    WARMUP_SECONDS="${WARMUP_SECONDS:-2}"

    echo "============================================================"
    echo "Live Collect: 实时采集新数据并重新生成第 4/5 章结果"
    echo "============================================================"
    echo "场景: ${DEMO_SCENES}"
    echo "采集时长: ${COLLECT_SECONDS}s, 预热: ${WARMUP_SECONDS}s"
    echo "注意: 该模式会调用 sudo eBPF 采集程序，并覆盖对应 stress-results 场景结果。"
    echo

    if ! sudo -n true 2>/dev/null; then
        echo "错误: 当前终端无法免密 sudo，不能启动 eBPF/PMU 采集程序。"
        echo "请先在现场终端运行一次 sudo -v，或配置当前用户对采集程序的 sudo 权限后再执行。"
        exit 1
    fi

    run_collect() {
        local scene="$1"
        local script="$2"
        sudo -n env COLLECT_SECONDS="$COLLECT_SECONDS" WARMUP_SECONDS="$WARMUP_SECONDS" python3 "$script"
        sudo -n chown -R "$(id -u)":"$(id -g)" "$PROJECT_ROOT/stress-results/$scene"
    }

    IFS=',' read -r -a scenes <<< "$DEMO_SCENES"
    for scene in "${scenes[@]}"; do
        case "$scene" in
            cpu)
                run_collect "$scene" scripts/run_cpu.py
                ;;
            memory)
                run_collect "$scene" scripts/run_memory.py
                ;;
            io)
                run_collect "$scene" scripts/run_io.py
                ;;
            mixed)
                run_collect "$scene" scripts/run_mixed.py
                ;;
            prod_mixed)
                run_collect "$scene" scripts/run_prod_mixed.py
                ;;
            "")
                ;;
            *)
                echo "未知场景: $scene"
                exit 1
                ;;
        esac
    done

    MERGE_SCENES="$DEMO_SCENES" python3 scripts/merge_results.py
    python3 scripts/build_thread_windows.py
    python3 scripts/predict_thread_windows.py
    python3 scripts/offline_magm_scheduler.py
    python3 scripts/export_cpu_selection.py
fi

echo "============================================================"
echo "Demo 1/5: XGBoost 预测模型结果"
echo "============================================================"
python3 - <<'PY'
import joblib
import pandas as pd

model = joblib.load("models/thread_predictors.joblib")
print("模型类型:", model.get("model_type"))
print("历史窗口长度:", model.get("hist_len"))
print("\n回归指标 RMSE/MAE:")
print(pd.read_csv("results/prediction/regression_metrics.csv").round(4).to_string(index=False))
print("\n状态分类指标:")
print(pd.read_csv("results/prediction/classification_metrics.csv").round(4).to_string(index=False))
PY

echo
echo "============================================================"
echo "Demo 2/5: MAGM 最终选核结果，展示最后窗口"
echo "============================================================"
python3 - <<'PY'
import pandas as pd

df = pd.read_csv("results/scheduler/final_window_selection.csv")
cols = ["LoadType", "window_id", "mode", "physical_core", "smt_slot", "target_cpu", "selected_thread"]
for load_type, sub in df.groupby("LoadType"):
    print(f"\n场景: {load_type}")
    print(sub[cols].to_string(index=False))
PY

echo
echo "============================================================"
echo "Demo 3/5: SMT 物理核配对视图"
echo "============================================================"
python3 - <<'PY'
import pandas as pd

df = pd.read_csv("data/processed/final_core_pairs.csv")
latest = df[df["window_id"].eq(df.groupby("LoadType")["window_id"].transform("max"))]
cols = ["LoadType", "window_id", "mode", "physical_core", "cpu_slot0", "slot0_thread", "cpu_slot1", "slot1_thread", "score"]
print(latest[cols].to_string(index=False))
PY

echo
echo "============================================================"
echo "Demo 4/5: sched_ext 内核能力检测"
echo "============================================================"
set +e
python3 scripts/check_sched_ext.py
set -e

echo
echo "============================================================"
echo "Demo 5/5: 用户态真实绑核验证，启动 live stress-ng"
echo "============================================================"
python3 scripts/run_magm_scheduler.py --mode affinity --load-type "${DEMO_AFFINITY_LOAD_TYPE:-mixed}" --duration 8

echo
echo "============================================================"
echo "Demo 收尾: 刷新中文展示结果目录"
echo "============================================================"
python3 scripts/format_demo_results.py
python3 scripts/export_named_demo_results.py

echo
echo "============================================================"
echo "演示完成"
echo "关键输出文件:"
echo "  results/prediction/regression_metrics.csv"
echo "  results/prediction/classification_metrics.csv"
echo "  results/scheduler/final_window_selection.csv"
echo "  data/processed/final_core_pairs.csv"
echo "  results/scheduler/live_affinity_report.csv"
echo
echo "中文展示目录:"
echo "  demo_results_pretty/"
echo "  demo_results_named/"
echo
echo "推荐打开:"
echo "  demo_results_named/README.md"
echo "  demo_results_named/01_XGBoost预测_回归误差指标_对齐版.txt"
echo "  demo_results_named/02_XGBoost预测_受限状态分类指标_对齐版.txt"
echo "  demo_results_named/08_最终选核_SMT物理核配对_对齐版.txt"
echo "  demo_results_named/12_真实验证_sched_setaffinity绑核结果_对齐版.txt"
echo "============================================================"
