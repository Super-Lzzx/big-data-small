# 基于 eBPF 的 Linux SMT 线程调度优化

## 快速运行

完整演示：

```bash
./scripts/demo_for_teachers.sh
```

现场实时采集后再演示：

```bash
sudo -v
LIVE_COLLECT=1 ./scripts/demo_for_teachers.sh
```

说明：实时采集模式默认采集 `mixed` 混合场景 `10s`，会调用 `sudo` 启动 eBPF/PMU 采集程序，覆盖所选场景的 `stress-results/*/cpu.csv`、`sched.csv`、`attr.csv`，然后重新合并数据、加载已有 XGBoost 模型做推理、生成 MAGM 调度结果并展示。可用 `COLLECT_SECONDS=8` 或 `COLLECT_SECONDS=10` 调整现场采集时长。

重新生成第 4/5 章预测与调度结果：

```bash
./scripts/reproduce_ch4_ch5.sh
```

用户态真实绑核验证：

```bash
python3 scripts/run_magm_scheduler.py --mode affinity --load-type cpu --duration 30
```

检测当前内核是否支持 sched_ext：

```bash
python3 scripts/check_sched_ext.py
```

## 目录总览

```text
Data/                                   第 3 章：eBPF/PMU 采集程序源码
  cpu/
    data.c                              PMU 硬件事件用户态采集程序，生成 cpu.csv
    data.bpf.c                          CPU 性能事件 eBPF 程序
    data.h                              CPU 事件结构体定义
  thread/
    data_thread.c                       sched_switch 用户态 loader，生成 sched.csv
    data_thread.bpf.c                   挂载 sched_switch，采集线程切换事件
    data_thread.h                       调度事件结构体定义

scripts/                                第 3-5 章：数据处理、预测、MAGM 调度、验证脚本
  run_cpu.py                            CPU 密集型负载采集
  run_memory.py                         内存密集型负载采集
  run_io.py                             I/O 密集型负载采集
  run_mixed.py                          混合负载采集
  run_prod_mixed.py                     生产型混合负载采集
  merge_results.py                      合并各场景 attr.csv，生成 full_dataset.csv
  build_thread_windows.py               构建 100ms 线程窗口，计算 7 维特征与状态标签
  train_thread_predictor.py             训练 7 路 XGBoost，预测下一窗口微架构特征
  predict_thread_windows.py             加载已训练模型，对新采集窗口做在线推理
  offline_magm_scheduler.py             实现互补性评分、CE/SP 切换与 MAGM 贪心配对
  export_cpu_selection.py               导出最终 CPU 选择和 SMT 物理核配对表
  apply_cpu_affinity.py                 对 final_cpu_selection.csv 做绑核 dry-run/apply
  run_live_affinity_validation.py       启动 live 负载并执行用户态 sched_setaffinity                     验证
  run_magm_scheduler.py                 最终调度入口，支持 affinity/scx 两种模式
  check_sched_ext.py                    检测当前内核是否支持 sched_ext
  reproduce_ch4_ch5.sh                  一键重跑第 4/5 章预测与调度结果
  demo_for_teachers.sh                  演示入口

sched_ext/                              第 5 章：MAGM sched_ext 原型调度器源码
  magm_scx.bpf.c                        sched_ext BPF 调度器，定义 sched_ext_ops
  magm_scx.c                            用户态 loader，写入 TID->CPU map 并 attach 调度器
  magm_scx.h                            BPF 与用户态共享结构体
  Makefile                              在支持 sched_ext 的机器上编译原型
  README.md                             sched_ext 原型编译、运行和限制说明

data/                                   原始数据、中间数据、处理后数据
  raw/                                  原始 cpu.csv、sched.csv
  processed/                            full_dataset、线程窗口、预测结果、MAGM 选核结果
    thread_windows_norm.csv             XGBoost 训练输入
    thread_predictions.csv              XGBoost 下一窗口预测结果
    magm_schedule.csv                   MAGM 线程到 CPU 决策
    final_cpu_selection.csv             最终选核明细
    final_core_pairs.csv                SMT 物理核配对视图

stress-results/                         各负载场景采集结果
  cpu/ io/ memory/ mixed/ prod_mixed/   每类场景包含 cpu.csv、sched.csv、attr.csv

results/                                预测、调度、验证指标
  prediction/                           第 4 章预测指标：RMSE/MAE、分类指标、混淆矩阵
  scheduler/                            第 5 章 MAGM 选核、绑核验证和 dry-run 报告
  eda/ monitor/ overhead/               数据分析、监控和采集开销图表

models/                                 训练好的 XGBoost 模型
  thread_predictors.joblib              按时间切分训练得到的评估模型
  thread_predictors_full.joblib         使用完整窗口序列重训得到的最终交付模型

demo_results_named/                     中文结果文件
  01_*                                  XGBoost 回归误差指标
  02_*                                  受限状态分类指标
  06-11_*                               MAGM 调度与最终选核结果
  12_*                                  sched_setaffinity 真实绑核验证
  13_*                                  历史 TID 绑核 dry-run 安全检查
  14_*                                  完整数据重训后的最终 XGBoost 模型

doc/                                    设计说明与 sched_ext 状态说明
src/analysis/                           早期分析与绘图脚本
vmlinux/                                eBPF CO-RE 使用的 vmlinux.h
```

## 论文第 3 章：eBPF 数据采集与线程画像

第 3 章主要对应“底层数据如何采集、如何归因到线程、如何形成窗口级微架构画像”。

### 3.1 PMU 性能事件采集

代码位置：`Data/cpu/`

- `Data/cpu/data.c`：用户态 PMU 采集程序，采集 cycles、instructions、cache misses、branch misses、L1/L2 cache misses、ITLB/DTLB misses 等硬件事件。
- `Data/cpu/data.bpf.c`：CPU 性能事件采集相关 eBPF 程序。
- `Data/cpu/data.h`：CPU 事件结构体定义。
- `Data/cpu/Makefile`：构建采集程序。

含义：为论文中的 IPC、MPKI、BrMPKI、TLB MPKI 等微架构指标提供原始计数。

### 3.2 调度事件采集

代码位置：`Data/thread/`

- `Data/thread/data_thread.bpf.c`：挂载 `tracepoint/sched/sched_switch`，采集线程上下文切换事件。
- `Data/thread/data_thread.c`：用户态 loader，从 ring buffer 读取事件并写出 `sched.csv`。
- `Data/thread/data_thread.h`：调度事件结构体定义。
- `Data/thread/Makefile`：构建线程调度采集程序。

含义：记录线程在哪些时间窗口运行，为 PMU 事件按线程归因提供依据。

### 3.3 多负载采集与数据合并

代码位置：`scripts/`

- `scripts/run_cpu.py`：CPU 密集型负载采集。
- `scripts/run_memory.py`：内存密集型负载采集。
- `scripts/run_io.py`：I/O 密集型负载采集。
- `scripts/run_mixed.py`：混合负载采集。
- `scripts/run_prod_mixed.py`：生产型混合负载采集。
- `scripts/merge_results.py`：合并各场景 `attr.csv`，生成 `data/processed/full_dataset.csv`。
- `scripts/collect_and_align.py`：早期 CPU 事件与调度事件对齐归因脚本。

主要输入输出：

```text
stress-results/*/cpu.csv
stress-results/*/sched.csv
stress-results/*/attr.csv
data/processed/full_dataset.csv
```

### 3.4 线程窗口画像构建

代码位置：`scripts/build_thread_windows.py`

输入：

```text
data/processed/full_dataset.csv
```

功能：

- 按论文设定的 `100ms` 时间窗口聚合线程数据。
- 计算 7 维微架构特征：`IPC`、`MPKI_LLC`、`MPKI_L1I`、`MPKI_L1D`、`MPKI_L2`、`BrMPKI`、`MPKI_TLB`。
- 对特征做归一化，形成 XGBoost 输入。
- 根据 Top-Down 思想生成 `FE-Bound`、`BE-Core`、`BE-Mem` 状态标签。

输出：

```text
data/processed/thread_windows.csv
data/processed/thread_windows_norm.csv
data/processed/thread_feature_norm_meta.csv
```

## 论文第 4 章：XGBoost 资源受限状态预测

第 4 章对应“用历史窗口预测下一窗口线程微架构状态”。

### 4.1 训练与预测代码

代码位置：`scripts/train_thread_predictor.py`

输入：

```text
data/processed/thread_windows_norm.csv
```

核心含义：

- 使用历史 `N=5` 个窗口作为输入。
- 预测下一窗口的 7 维归一化微架构特征。
- 使用 7 个独立 XGBoost 回归器，分别预测 7 个目标维度。
- 预测后再派生 `FE-Bound`、`BE-Core`、`BE-Mem` 状态标签，用于分类指标评估。

代码中的 XGBoost 参数与论文表 4.3 对应：

```python
n_estimators=100
learning_rate=0.05
max_depth=5
min_child_weight=3
gamma=0.1
reg_lambda=1.5
subsample=0.8
colsample_bytree=0.8
objective="reg:squarederror"
```

输出：

```text
models/thread_predictors.joblib
models/thread_predictors_full.joblib
data/processed/thread_predictions.csv
results/prediction/regression_metrics.csv
results/prediction/classification_metrics.csv
results/prediction/confusion_matrix.csv
```

### 4.2 预测结果含义

- `thread_predictors.joblib`：按时间切分训练得到的评估模型，用于生成测试集指标。
- `thread_predictors_full.joblib`：使用完整窗口序列重新训练得到的最终交付模型。
- `thread_predictions.csv`：每个测试窗口的真实特征、预测特征和预测状态。
- `regression_metrics.csv`：逐特征 RMSE/MAE。
- `classification_metrics.csv`：受限状态 precision、recall、F1。
- `confusion_matrix.csv`：状态预测混淆矩阵。

## 论文第 5 章：MAGM 调度与 sched_ext 原型

第 5 章对应“根据预测结果计算互补性，并把线程放到合适的 SMT 核上”。

### 5.1 互补性评分与 MAGM 选核

代码位置：`scripts/offline_magm_scheduler.py`

输入：

```text
data/processed/thread_predictions.csv
```

核心含义：

- `complementarity_score()` 实现论文中的“差异即收益、相同即惩罚”思想。
- `predicted_intensity()` 根据预测特征计算线程受限强度。
- `rho = n_run / physical_cores` 判断负载状态。
- `CE` 模式：低负载时尽量把线程分散到不同物理核。
- `SP` 模式：高负载时按互补性得分进行 SMT sibling 贪心配对。

输出：

```text
data/processed/magm_schedule.csv
results/scheduler/magm_window_summary.csv
```

### 5.2 最终 CPU 选择视图

代码位置：`scripts/export_cpu_selection.py`

输入：

```text
data/processed/magm_schedule.csv
```

功能：

- 将 MAGM 线程决策展开为 `physical_core`、`smt_slot`、`target_cpu`。
- 生成答辩时更直观的物理核配对表。

输出：

```text
data/processed/final_cpu_selection.csv
data/processed/final_core_pairs.csv
results/scheduler/final_window_selection.csv
results/scheduler/cpu_selection_summary.csv
```

### 5.3 当前机器可运行的用户态绑核验证

代码位置：

- `scripts/apply_cpu_affinity.py`
- `scripts/run_live_affinity_validation.py`
- `scripts/run_magm_scheduler.py`

含义：

- 当前内核不支持 sched_ext，因此用 `sched_setaffinity` 验证 MAGM 选核结果。
- `run_live_affinity_validation.py` 会启动 live 负载，并把当前真实运行的线程绑定到 MAGM 给出的 CPU。
- `apply_cpu_affinity.py` 可对历史 TID 做 dry-run 安全检查，避免 PID 复用或线程已退出导致误绑。

输出：

```text
results/scheduler/live_affinity_report.csv
results/scheduler/affinity_dry_run_report.csv
```

### 5.4 sched_ext 原型代码

代码位置：`sched_ext/`

- `sched_ext/magm_scx.bpf.c`：sched_ext BPF 调度器原型，定义 `struct sched_ext_ops magm_ops`，实现 `select_cpu` 和 `enqueue`。
- `sched_ext/magm_scx.c`：用户态 loader，读取 `final_cpu_selection.csv`，把 `TID -> target_cpu` 写入 BPF map，并 attach 调度器。
- `sched_ext/magm_scx.h`：BPF 与用户态共享结构。
- `sched_ext/Makefile`：在支持 sched_ext 的机器上编译。
- `sched_ext/README.md`：sched_ext 原型的编译、运行和限制说明。

当前实现与论文规则的关系：

- MAGM 规则计算在 `scripts/offline_magm_scheduler.py` 中完成。
- sched_ext 原型负责在内核调度路径中执行已经生成的 `TID -> CPU` 决策。
- 它是论文 sched_ext 落地部分的原型执行器，还不是完整在线闭环版本。

在支持 sched_ext 的机器上运行：

```bash
cd sched_ext
make
sudo ./magm_scx ../data/processed/final_cpu_selection.csv
```

目标机器至少需要：

```text
CONFIG_SCHED_CLASS_EXT=y
/sys/kernel/sched_ext 存在
/sys/kernel/btf/vmlinux 中包含 sched_ext_ops / scx_bpf 符号
```

## 论文第 6 章：实验结果与演示整理

第 6 章对应“指标展示、结果汇总、答辩演示文件整理”。

### 6.1 一键复现实验结果

代码位置：

- `scripts/reproduce_ch4_ch5.sh`：重新生成第 4/5 章预测与调度结果。
- `scripts/demo_for_teachers.sh`：一键演示 XGBoost、MAGM、sched_ext 检测、live 绑核验证。

### 6.2 结果格式化

代码位置：

- `scripts/format_demo_results.py`：把结果表格转换为中文列名和等宽文本。
- `scripts/export_named_demo_results.py`：把展示结果复制成中文文件名和编号。

推荐展示目录：

```text
demo_results_named/
```

常用展示文件：

```text
demo_results_named/01_XGBoost预测_回归误差指标_对齐版.txt
demo_results_named/02_XGBoost预测_受限状态分类指标_对齐版.txt
demo_results_named/08_最终选核_SMT物理核配对_对齐版.txt
demo_results_named/10_最终选核_各场景最后窗口_对齐版.txt
demo_results_named/12_真实验证_sched_setaffinity绑核结果_对齐版.txt
demo_results_named/13_安全检查_历史TID绑核DryRun.csv
demo_results_named/14_最终模型_XGBoost全量训练模型说明.md
```

## 当前 sched_ext 状态

当前机器不支持真正加载 sched_ext 调度器。检测命令：

```bash
python3 scripts/check_sched_ext.py
```

当前阻塞点：

- `/sys/kernel/sched_ext` 不存在。
- `/boot/config-$(uname -r)` 中没有 `CONFIG_SCHED_CLASS_EXT=y`。
- 内核 BTF 中没有 `sched_ext_ops` / `scx_bpf` 相关符号。

因此，本机实验使用用户态 `sched_setaffinity` 验证调度结果；`sched_ext/` 目录中的代码用于迁移到支持 sched_ext 的内核上编译运行。

## 推荐答辩说明顺序

1. 第 3 章：说明 `Data/` 和 `scripts/build_thread_windows.py` 如何形成 100ms 线程画像。
2. 第 4 章：说明 `scripts/train_thread_predictor.py` 如何用 XGBoost 预测下一窗口 7 维特征。
3. 第 5 章：说明 `scripts/offline_magm_scheduler.py` 如何实现 CE/SP 与 MAGM 配对。
4. 第 5 章落地：说明当前机器用 `sched_setaffinity` 验证，支持 sched_ext 的机器可用 `sched_ext/magm_scx.*`。
5. 第 6 章：展示 `demo_results_named/` 中的预测指标、选核结果和绑核验证结果。
