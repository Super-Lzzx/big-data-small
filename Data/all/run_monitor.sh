#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------------
# 监控 + 多负载采集一体化脚本 (run_monitor.sh)
# 将系统级指标和 run_all.sh 输出都集中到 monitor/ 目录
# -------------------------------------------------------------------

# 输出目录
OUTDIR=monitor
mkdir -p "$OUTDIR"

# 1) 并行启动系统级监控
nohup sar    -u 1               > "$OUTDIR/cpu_util.csv"    2>&1 & SAR_PID=$!
nohup iostat -dx 1             > "$OUTDIR/io_stat.csv"     2>&1 & IOSTAT_PID=$!
nohup vmstat 1                 > "$OUTDIR/vmstat.csv"      2>&1 & VMSTAT_PID=$!
nohup perf stat -a \
    -e context-switches,branch-misses \
    -I 1000 \
    bash -c 'while true; do sleep 1; done' \
    > "$OUTDIR/perf_stat.csv"  2>&1 & PERFSTAT_PID=$!

echo "系统监控启动完毕 (sar, iostat, vmstat, perf stat)…"
echo "监控数据输出到: $OUTDIR/"

# 2) 运行你的多负载采集脚本 run_all.sh
#    run_all.sh 会生成 performance_data.csv
echo "开始多负载采集: run_all.sh"
bash run_all.sh

# 3) 把 run_all.sh 产生的结果移动到 monitor/ 下
if [[ -f performance_data.csv ]]; then
  mv performance_data.csv "$OUTDIR/"
fi

# 4) 停掉所有后台监控进程
kill $SAR_PID $IOSTAT_PID $VMSTAT_PID $PERFSTAT_PID

echo "监控进程已停止。所有数据已汇总到："
ls -1 "$OUTDIR"
