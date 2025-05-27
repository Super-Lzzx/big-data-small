# 基于 eBPF 的线程互补性分析 & 负载测试综合指南

> 本文档汇总了线程互补性分析的背景与方法，数据采集与归因方案，以及在不同负载类型下进行测试与数据集构建、预测和调度流程。

---

## 1. 背景与目的

在多核处理器系统中，**线程间的互补性**对提升整体性能、优化调度策略至关重要。单独采集调度事件或核心性能事件都无法全面反映每个线程的硬件资源消耗，因此需要**结合 CPU 性能事件与 `sched_switch` 调度事件**，实现线程级别的定量归因。

**主要目标**：

1. 精确归因：将每个采样时刻的 cycles、instructions、cache-misses 等硬件事件，归因到真实运行的线程。
2. 互补性度量：通过对齐后的数据，计算不同线程在同窗口内的相关/负相关系数，揭示线程在多核环境下的互补行为。

---

## 2. 数据采集与归因方案

### 2.1 采集数据类型

* **CPU 核心性能事件**：采集 `cycles`、`instructions`、`cache-misses`、`branch-misses`、L1/L2/ITLB/DTLB-misses。
* **线程调度事件**：eBPF 跟踪 `sched_switch`，记录 `prev_comm/prev_pid/next_comm/next_pid/cpu/ts`。

### 2.2 数据格式示例

* **cpu.csv**

  ```csv
  time,cpu,cpu_cycles,instructions,cache_misses,branch_instrs,branch_misses,L1_icache_miss,L1_dcache_miss,ITLB_misses,L2_cache_miss,DTLB_misses
  1748337509107368166,0,57865159,62028810,...
  ```
* **sched.csv**

  ```csv
  ts,cpu,prev_comm,prev_pid,next_comm,next_pid
  7152822800591,3,kworker/u32:4,18802,swapper/3,0
  ```

### 2.3 对齐与归因

* **最近调度法**：为每条 `cpu.csv` 条目，找到同 `cpu` 上最近的 `sched.csv` 事件，将硬件事件归因到该线程。
* **脚本**：使用 `scripts/align_thread.py` 完成 `data/raw/→data/processed/` 归因。

---

## 3. 典型负载测试场景

### 3.1 CPU 计算型

```bash
stress-ng --cpu 8 --cpu-method matrixprod --timeout 300s
sysbench --test=cpu --cpu-max-prime=20000 --num-threads=8 --time=300 run
```

### 3.2 磁盘 I/O 型

```bash
stress-ng --hdd 4 --hdd-bytes 2G --timeout 300s
fio --name=randrw --ioengine=libaio --direct=1 \
    --rw=randrw --rwmixread=70 --bs=4k --size=1G \
    --numjobs=4 --runtime=300 --time_based
```

### 3.3 内存访问型

```bash
stress-ng --vm 4 --vm-bytes 1G --vm-method memcpy --timeout 300s
sudo memtester 4G 5
```

### 3.4 网络 I/O 型（可选）

```bash
iperf3 -s &
iperf3 -c localhost -P4 -t300
```

### 3.5 混合生产型 (Nginx + 计算)

```bash
sudo systemctl start nginx
ab -n100000 -c100 http://localhost/ &
sysbench --test=cpu --cpu-max-prime=20000 --num-threads=4 --time=300 run &
```

---

## 4. 自动化脚本集成

在 `scripts/collect_and_align.py` 定义：

```python
workloads = {
  "cpu":       ["stress-ng --cpu 8 ..."],
  "io":        ["stress-ng --hdd 4 ..."],
  "mem":       ["stress-ng --vm 4 ..."],
  "net":       ["iperf3 -s","iperf3 -c localhost -P4 -t300"],
  "prod_mixed":["ab -n100000 ...","sysbench ..."]
}
```

**执行**：

```bash
cd scripts && sudo python3 collect_and_align.py
```

---

## 5. 构建数据集

### 5.1 数据标签与特征

* 每条记录必须包含：

  ```text
  [sec, cpu, cpu_cycles, instructions, cache_misses, ..., DTLB_misses, thread, pid, LoadType, Rep]
  ```
* **LoadType**：场景名称（cpu/io/mem/net/prod\_mixed）。
* **Rep**：重复实验序号。

### 5.2 数据清洗与合并

1. 合并所有场景 `data/processed/*.csv` 到一个 DataFrame，并加入 `LoadType`、`Rep` 列。
2. 按 `sec, thread` 聚合 `cpu_cycles`、`instructions` 等性能指标。
3. 填充缺失值并进行归一化或标准化。

### 5.3 保存最终数据集

* 推荐使用 Pandas 将合并后的 DataFrame 导出为 `data/dataset/full_dataset.csv`。

---

## 6. 预测与调度策略

### 6.1 预测模型训练

* **任务**：通过机器学习模型（如逻辑回归、随机森林、神经网络）预测在不同场景下哪对线程具有最高互补度。
* **特征**：线程聚合的 `cpu_cycles`, `cache_misses`, 相关系数矩阵特征（主成分得分、互补度指标等）。
* **标签**：手动或阈值判断得到的“高互补”与“低互补”二分类。

```python
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
X = df[feature_cols]
y = df['label']  # 1=高互补
X_train, X_test, y_train, y_test = train_test_split(X, y, ...)
clf = RandomForestClassifier().fit(X_train, y_train)
```

### 6.2 调度优化建议

* 根据预测结果，为调度器提供规则：

  * **互补线程配对**：将预测为高互补的线程安排在不同核心，以最大化利用率。
  * **负载平衡**：对预测为低互补或冲突的线程，避免同时调度在相邻核或共享缓存核上。

### 6.3 实验验证

1. 部署修改后的调度策略或 SCHED\_DEADLINE、CFS 调度器插件。
2. 在相同负载下采集对比数据，评估系统吞吐和延迟改进。

---

> **总结**：本指南涵盖了从数据采集、归因、测试场景到数据集构建、预测模型和调度优化全流程，为深入研究线程互补性提供了完整框架。
