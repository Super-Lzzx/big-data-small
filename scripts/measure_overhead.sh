#!/usr/bin/env bash
set -euo pipefail

# 脚本目录 & 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 三种采集模式
MODES=(perf ptrace ebpf)
# 采集总时长（秒）
DURATION=180
# 采样间隔（毫秒）
INTERVAL_MS=100

# 硬件计数器时序数据输出目录 → data/overhead
OUTDIR="$PROJECT_ROOT/data/overhead"
# eBPF loader 可执行（thread 采集程序）
LOAD_BIN="$PROJECT_ROOT/Data/thread/data_thread"
# perf 采集程序
PERF_BIN="$PROJECT_ROOT/Data/cpu/data"

# 监控自身开销汇总文件
MON_CSV="$OUTDIR/monitor_overhead.csv"
# perf 事件列表
EVENTS="cycles,instructions,cache-misses,branch-instructions,branch-misses,L1-icache-load-misses,L1-dcache-load-misses,iTLB-load-misses,dTLB-load-misses"

mkdir -p "$OUTDIR"

# 写入监控开销表头
printf 'mode,Usr(s),Sys(s),Real(s)\n' > "$MON_CSV"

# 确保采集可执行文件存在
for BIN in "$LOAD_BIN" "$PERF_BIN"; do
  if [[ ! -x "$BIN" ]]; then
    echo "Error: 找不到可执行文件 '$BIN'" >&2
    exit 1
  fi
done

for mode in "${MODES[@]}"; do
  echo
  echo ">>> 模式：$mode，采集空闲 ${DURATION}s，采样间隔 ${INTERVAL_MS}ms"

  # 硬件计数器时序 CSV
  hwfile="$OUTDIR/${mode}.csv"
  printf 'sec,cycles,instructions,cache-misses,branch-instructions,branch-misses,L1I_miss,L1D_miss,iTLB_miss,dTLB_miss,elapsed_ms\n' \
    > "$hwfile"

  # ptrace 模式要加 strace 前缀
  PREFIX=""
  if [[ "$mode" == "ptrace" ]]; then
    PREFIX="strace -c -e trace=all -o /dev/null -- "
  fi

  # ebpf 模式：后台启动 loader
  if [[ "$mode" == "ebpf" ]]; then
    echo "  启动 eBPF loader 后台进程..."
    sudo "$LOAD_BIN" &
    EBPF_PID=$!
    sleep 1
  fi

  # perf stat + time 采样，并把 perf 原始输出（stderr）也 tee 到日志
  echo "  运行：${PREFIX}/usr/bin/time -o $MON_CSV -a -f '${mode},%U,%S,%e,%P' $PERF_BIN stat -a -e $EVENTS -I $INTERVAL_MS -x, -o stats.tmp -- sleep $DURATION"
  eval "${PREFIX}/usr/bin/time -o \"$MON_CSV\" -a -f '${mode},%U,%S,%e,%P' \
       \"$PERF_BIN\" stat -a -e \"$EVENTS\" -I $INTERVAL_MS -x, -o stats.tmp -- sleep \"$DURATION\" \
       2>&1 | tee \"$OUTDIR/${mode}_perf_raw.log\""

  # 停止 ebpf loader
  if [[ "$mode" == "ebpf" ]]; then
    echo "  杀掉 eBPF loader (PID $EBPF_PID)"
    sudo kill "$EBPF_PID" || true
  fi

  # 解析 stats.tmp，按最后一个事件输出每秒一行
  declare -A vals
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    IFS=',' read -ra cols <<< "$line"
    sec="${cols[0]%.*}"
    cnt="${cols[1]}"
    evn="${cols[3]}"
    case "$evn" in
      cycles)                vals[0]=$cnt ;;
      instructions)          vals[1]=$cnt ;;
      cache-misses)          vals[2]=$cnt ;;
      branch-instructions)   vals[3]=$cnt ;;
      branch-misses)         vals[4]=$cnt ;;
      L1-icache-load-misses) vals[5]=$cnt ;;
      L1-dcache-load-misses) vals[6]=$cnt ;;
      iTLB-load-misses)      vals[7]=$cnt ;;
      dTLB-load-misses)      vals[8]=$cnt ;;
      *) continue ;;
    esac

    # 当遇到最后一个事件时，输出整行
    if [[ "$evn" == "dTLB-load-misses" ]]; then
      printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
        "$sec" \
        "${vals[0]:-0}" "${vals[1]:-0}" "${vals[2]:-0}" "${vals[3]:-0}" "${vals[4]:-0}" \
        "${vals[5]:-0}" "${vals[6]:-0}" "${vals[7]:-0}" "${vals[8]:-0}" \
        "$INTERVAL_MS" \
        >> "$hwfile"
    fi
  done < stats.tmp
  rm -f stats.tmp

  # 格式对齐并预览
  column -t -s, "$hwfile" > "${hwfile}.tmp"
  mv "${hwfile}.tmp" "$hwfile"
  echo "  [HWC] 已保存 → $hwfile"
  head -n 6 "$hwfile"
done

# 生成带 Overhead(s) 和 CPU_pct 的完整监控开销表
awk -F, -v D="$DURATION" 'BEGIN {
    OFS=","; 
    print "mode,Usr(s),Sys(s),Real(s),Overhead(s),CPU_pct"
}
NR>1 {
    usr=$2; sys=$3; real=$4;
    overhead=real - D;
    cpu_pct=(usr + sys) / real * 100;
    printf "%s,%.3f,%.3f,%.3f,%.3f,%.2f\n", $1, usr, sys, real, overhead, cpu_pct;
}' "$MON_CSV" > "${MON_CSV}.tmp" && mv "${MON_CSV}.tmp" "$MON_CSV"

# 修正权限归属
OWNER_UID=${SUDO_UID:-$(id -u)}
OWNER_GID=${SUDO_GID:-$(id -g)}
chmod -R a+r "$OUTDIR"
chown -R $OWNER_UID:$OWNER_GID "$OUTDIR"

# 输出最终结果
echo
echo "=== monitor_overhead.csv ==="
column -t -s, "$MON_CSV"
echo
echo "脚本执行完毕，所有文件请见目录：$OUTDIR/"
