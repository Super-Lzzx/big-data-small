# eBPF 采集程序记录

## 概述

本项目包含五个 eBPF 采集程序，每个程序通过 perf_event 机制采集特定的 CPU 事件。这些程序的数据由 eBPF 代码在内核态捕获，并通过 perf_event_output 发送到用户态进行分析。

## 各采集程序的功能

### first_event

采集内容：CPU 周期（cpu_cycles）,指令数（instructions）,缓存未命中（cache_misses）,分支指令（branch_instructions）,分支未命中（branch_misses）

用途：监测 CPU 活动，评估指令执行情况。分析缓存未命中情况，找出热点代码片段。分支预测准确率评估。

### second_event

采集内容：L1 指令缓存未命中（l1_icache_misses）,L1 数据缓存未命中（l1_dcache_misses）

用途：分析 L1 缓存性能，找出访问热点。评估数据局部性，优化数据访问模式。

### third_event

采集内容：L2 缓存未命中（l2_cache_misses）

用途：分析二级缓存的效率，发现缓存优化方向。监测 L2 缓存的占用情况，判断缓存压力。

### forth_event

采集内容：指令 TLB（iTLB）未命中（itlb_misses）

用途：监测指令地址转换的开销。发现页表缺失情况，优化内存管理策略。

### fifth_event

采集内容：数据 TLB（dTLB）未命中（dtlb_misses）

用途：监测数据地址转换的开销。分析内存访问模式，优化 TLB 命中率。

### all

所有采集的指标的集合