#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------------
# 监控 + 多负载采集一体化脚本 (run_monitor.sh)
# 将系统级指标和 run_all.sh 输出都集中到 data/monitor/ 目录
# -------------------------------------------------------------------

# 脚本所在目录 & 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 输出目录：data/monitor
OUTDIR="$PROJECT_ROOT/data/monitor"
mkdir -p "$OUTDIR"

echo "→ 输出目录：$OUTDIR"

# 1) 并行启动系统级监控
nohup sar -u 1                     > "$OUTDIR/cpu_util.csv"    2>&1 & SAR_PID=$!
nohup iostat -dx 1                 > "$OUTDIR/io_stat.csv"     2>&1 & IOSTAT_PID=$!
nohup vmstat 1                     > "$OUTDIR/vmstat.csv"      2>&1 & VMSTAT_PID=$!
nohup perf stat -a \
    -e context-switches,branch-misses \
    -I 1000 \
    bash -c 'while true; do sleep 1; done' \
    > "$OUTDIR/perf_stat.csv"      2>&1 & PERFSTAT_PID=$!

echo "系统监控启动完毕 (sar, iostat, vmstat, perf stat)…"

# 2) 运行多负载采集脚本 run_all.sh
echo "开始多负载采集：run_all.sh"
bash "$SCRIPT_DIR/run_all.sh"

# 3) 把 run_all.sh 产生的结果移动到 data/monitor/
if [[ -f performance_data.csv ]]; then
  mv performance_data.csv "$OUTDIR/"
  echo "已移动 performance_data.csv → $OUTDIR/"
fi

# 4) 停掉所有后台监控进程
kill "$SAR_PID" "$IOSTAT_PID" "$VMSTAT_PID" "$PERFSTAT_PID" || true
echo "监控进程已停止。"

echo
echo "====== data/monitor/ 目录下的文件列表 ======"
ls -1 "$OUTDIR"
