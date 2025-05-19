# eBPF 采集方法开销对比

以下结果基于**空闲状态下**对比三种监控方式（Perf、Ptrace、eBPF），采集时长 180 s，采样间隔 100 ms。

## 1. 实验环境

- **目标机**：16 CPU 空闲系统
- **采集方式**：
  - **Perf**：`perf stat` 系统级统计
  - **Ptrace**：在 Perf 前加 `strace -c -e trace=all`
  - **eBPF**：基于Libbpf 的自定义 eBPF 程序
- **采样**：采样间隔 100 ms，输出 10 项硬件计数器
- **度量**：
  - **Real 开销 (s)** = 实时时间 – 基准 180 s
  - **CPU 占用 (%)** = (Usr(s) + Sys(s)) / Real(s) × 100%

------

## 2. 结果图示

### 2.1 CPU 占用率对比



![已上传的图片](/home/superlzx/big-data-small/results/overhead_time.png)

> **说明**：
>
> - eBPF 方法CPU占用约 **0.56%**，略低于 Perf/Ptrace
> - 说明 eBPF 在系统开销方面具有优势

------

### 2.2 实际时间开销对比



![已上传的图片](/home/superlzx/big-data-small/results/overhead_cpu.png)

> **说明**：
>
> - Ptrace 实际多用时约 **0.03 s**，Perf/eBPF 均约 **0.02 s**
> - eBPF 并未在实时时间开销上输给 Perf

------

## 3. 数据表

| 模式   | Usr(s) | Sys(s) | Real(s) | Overhead(s) | CPU_pct |
| ------ | ------ | ------ | ------- | ----------- | ------- |
| Perf   | 0.230  | 0.690  | 180.020 | 0.020       | 0.51%   |
| Ptrace | 0.240  | 0.790  | 180.020 | 0.020       | 0.57%   |
| eBPF   | 0.260  | 0.750  | 180.020 | 0.020       | 0.56%   |