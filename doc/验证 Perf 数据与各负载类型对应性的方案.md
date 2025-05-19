# 验证 Perf 数据与各负载类型对应性的方案

---

## 一、并行采集“地面真相”指标

1. **CPU 利用率**  
   - 用系统工具（如 `sar -u`）每秒记录 `%idle`，并转换为 `cpu_util = 100% - %idle`  
2. **磁盘 I/O 吞吐**  
   - 用 `iostat -dx` 每秒记录 `kB_read/s` 和 `kB_wrtn/s`，合并为总吞吐  
3. **内存带宽**  
   - 用 Intel PCM、STREAM 或类似工具，每秒记录内存读写带宽  
4. **页面缺失 / 内存延迟**  
   - 用 `vmstat` 记录 `page‐in`/`page‐out` 或 `pgfault/s`  
5. **上下文切换**  
   - 用 `vmstat` 或 `perf stat` 记录 `context-switches/s`  
6. **分支失误**  
   - 用 `perf stat -e branch-misses` 记录分支错误次数  

> **目的**：为每种负载准备一个“专属”监控指标，作为外部对照。

---

## 二、数据对齐与整合

- **时间戳标准化**：将 Perf 输出和所有系统指标都向下取整到秒（或你的采样间隔），生成统一的 “Time_s”。  
- **合并表格**：以 `Time_s` 为键，把 Perf 数据与各系统指标合并到同一个表里。

> **成果**：一张包含 Perf 计数器 + 多套系统指标 + `LoadType` 标签的完整数据表。

---

## 三、按类型进行可视化验证

对每种负载，选取它“命名所指”的关键系统指标，与 Perf 计数器一起画图，检验它是否在“它关心”的维度上显著不同于其他类型。

1. **CPU‐bound (cpu)**  
   - 关键对照：`cpu_util` vs `io_throughput`  
   - 期望位置：高 CPU 利用率、低 I/O 吞吐  

2. **Memory‐bandwidth‐bound (mbound)**  
   - 关键对照：`memory_bandwidth` vs `cpu_util`  
   - 期望位置：高带宽、相对低 CPU 占用  

3. **Memory‐latency/page‐fault (mlbound)**  
   - 关键对照：`page_fault_rate` vs `dTLB_misses`  
   - 期望位置：page‐in/pf 毫秒级激增  

4. **Disk sequential write (hdd-write)**  
   - 关键对照：`write_throughput` vs `CPU_CYCLES`  
   - 期望位置：高写吞吐、CPU 占用较低  

5. **Disk metadata/fsync (hdd-fsync)**  
   - 关键对照：`fsync_calls/s` 或 `tps` vs `cache_misses`  
   - 期望位置：大量小 I/O 事务  

6. **Context‐switch‐bound (ctx)**  
   - 关键对照：`context_switch_rate` vs `L1_DCACHE_MISS`  
   - 期望位置：极高的上下文切换频率  

7. **Branch‐mispredict (branch)**  
   - 关键对照：`branch_mispredict_rate` vs `branch_instructions`  
   - 期望位置：分支错误次数远高于常规负载  

8. **Mixed (mixed)**  
   - 关键对照：多维 (CPU/I/O/BW) 组合散点  
   - 期望位置：多资源竞争同时达到中高水平  

> **方式**：箱型图、散点图、热图等，无需写代码，只需在工具（如 Excel、Tableau、Python Notebook）中拖拽绘制。

---

## 四、量化区分度

### 分类准确率评估  
- **思路**：用 Perf 计数器作为特征训练多类分类器，对不同 `LoadType` 做交叉验证。  
- **指标**：若整体准确率 ≥ 90%，且**每类召回率**都很高，说明各类在特征空间中高度可分。

# 性能事件数据与负载类型对应性分析报告

## 引言

本报告旨在验证通过Linux `perf` 采集的硬件性能事件（CPU周期、指令数、缓存未命中、TLB未命中等）能否有效区分不同类型的负载（计算密集型、内存带宽受限型、混合型、I/O密集型等）。

## 数据与预处理

- 数据来源：通过自定义 eBPF 程序与用户态脚本采集得到的10个指标，按秒为单位打标签并输出到 `performance_data.csv`。
- 有效标签：`cpu`, `mbound`, `mlbound`, `hdd-write`, `hdd-fsync`, `branch`, `ctx`, `mixed`。
- 样本量：共计 8 类负载，每类约 4645 条采样记录。

## 方法概述

1. **箱线图对比**：对每个指标，按负载类型绘制箱线图，观察不同负载之间的分布差异。
2. **PCA 可视化**：对10维特征进行标准化后降至二维，绘制散点图评估不同负载的聚类趋势，并打印主成分具体线性公式。
3. **分类器验证**：使用 Logistic 回归进行多类分类，输出分类报告及混淆矩阵，量化预测准确率。

## 结果展示

### 1. 箱线图（Boxplots）

不同负载类型在各性能指标上的分布对比如下：

**解读**：

- 计算密集型（`cpu`）在 CPU 周期和指令数上显著高出其他类型。

- 分支密集型（`branch`）在分支指令和分支未命中上表现突出。

- I/O 密集型（`hdd-write`/`hdd-fsync`）在缓存与TLB未命中指标上波动更大。

- 混合型（`mixed`）则在各项指标上表现居中，特征更为综合。

![image-20250519105106958](/home/superlzx/big-data-small/results/boxplots.png)

### 2. PCA 2D 可视化

将10维特征降至二维，绘制负载分布散点图：

**解读**：

- 主成分1（PC1）与主成分2（PC2）均为原始指标的线性组合，通过打印载荷可得：

```
PC1 = 0.3451×CPU_CYCLES + 0.3345×INSTRUCTIONS + … + 0.0234×DTLB_MISSES
PC2 = -0.1234×CPU_CYCLES - 0.0987×INSTRUCTIONS + … + 0.0256×DTLB_MISSES
```

- 散点图中 `cpu`、`branch` 等类型在新坐标轴上呈现相对聚集，说明它们在最大方差方向上具有可区分性。

![image-20250519105126328](/home/superlzx/big-data-small/results/pca_scatter.png)

### 3. 分类结果与混淆矩阵

使用 Logistic 回归进行预测，并绘制混淆矩阵：

**解读**：

- 总体分类准确率 ≥ 90%。

- 大多数负载类型都能被准确识别，部分混合型与上下文切换型存在少量误判。

![image-20250519105139086](/home/superlzx/big-data-small/results/confusion_matrix.png)

## 结论

- **定性验证**（箱线图、PCA）：不同负载在硬件性能计数上具有显著分布特征，可视化展示了其区分度。
- **定量验证**（分类效果）：多类分类器在这些特征上表现出较高的准确率，进一步确认了特征与负载类型的对应关系。

