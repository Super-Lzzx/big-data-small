#!/usr/bin/env bash
set -euo pipefail

# 脚本目录 & 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

################################################################################
# 配置区域
################################################################################
# 原始和对齐后的 CSV 都放到 data/monitor 下
RAW_DIR="$PROJECT_ROOT/data/monitor"
OUT_RAW="$RAW_DIR/performance_data.raw.csv"   # 原始逗号分隔 CSV
OUT_ALIGNED="$RAW_DIR/performance_data.csv"   # 最终对齐的表格

DURATION=60                          # 每种负载运行时长（秒）
SAMPLE_INTERVAL=1                    # data 程序中同步改为 1 秒采样
REPEATS=5                            # 重复次数

# 你的用户态程序可执行文件
DATA_BIN="$PROJECT_ROOT/Data/cpu/data"
################################################################################

# 确保输出目录存在
mkdir -p "$RAW_DIR"

# 1. 初始化原始 CSV —— 删除旧文件，写入表头（新增 Rep 列以标识重复次数）
if [[ -f $OUT_RAW ]]; then
  rm "$OUT_RAW"
fi

cat << 'EOF' > "$OUT_RAW"
Time,CPU,CPU_CYCLES,INSTRUCTIONS,CACHE_MISSES,BRANCH_INSTRS,BRANCH_MISSES,L1_ICACHE_MISS,L1_DCACHE_MISS,ITLB_MISSES,L2_CACHE_MISS,DTLB_MISSES,LoadType,Rep
EOF

echo "Initialized raw CSV: $OUT_RAW"

# 2. 按照建议的 8 种负载类型及其 stress-ng 参数
labels=( cpu mbound mlbound hdd-write hdd-fsync ctx branch mixed )
cmds=(
  "--cpu 4"
  "--vm 2 --vm-bytes 90% --vm-hang 0"
  "--page-faults 2"
  "--hdd 2 --hdd-bytes 1G --hdd-opts write"
  "--hdd 2 --hdd-bytes 500M --hdd-opts fsync"
  "--ctx 4"
  "--branch 4"
  "--cpu 4 --io 4 --vm 2 --vm-bytes 2G"
)

# 3. 多次重复采集
for rep in $(seq 1 $REPEATS); do
  echo "=== Starting repetition #$rep ==="
  for idx in "${!labels[@]}"; do
    label=${labels[$idx]}
    params=${cmds[$idx]}

    echo "--- LoadType: $label (${params}) for ${DURATION}s ---"

    # 3.1 后台启动 stress-ng（容错）
    stress-ng $params --timeout ${DURATION}s > /dev/null 2>&1 || true &
    STRESS_PID=$!

    # 3.2 同步运行 data 程序并采集（管道失败不退出）
    timeout ${DURATION}s "$DATA_BIN" | \
      awk -v load="$label" -v rep="$rep" -v interval="$SAMPLE_INTERVAL" '
        BEGIN { OFS = "," }
        /^[0-9]+/ {
          cmd = "date +\"%Y-%m-%d %H:%M:%S\""; cmd | getline t; close(cmd)
          printf "%s,%s", t, $1
          for(i = 2; i <= NF; i++) printf ",%s", $i
          printf ",%s,%s\n", load, rep
        }
      ' >> "$OUT_RAW" || true

    # 3.3 等待 stress-ng 退出
    wait $STRESS_PID

    echo "+++ Completed: LoadType=$label Rep=$rep +++"
  done
done

echo
echo "Raw data collection finished: $OUT_RAW"

# 4. 备份原始 CSV 并对齐写回
BACKUP="${OUT_RAW%.csv}.backup.csv"
mv "$OUT_RAW" "$BACKUP"
column -s, -t "$BACKUP" > "$OUT_ALIGNED"

echo "Backed up raw CSV to $BACKUP"
echo "Aligned table saved to $OUT_ALIGNED"
echo "All done."
