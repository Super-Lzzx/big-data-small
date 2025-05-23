# 基于 eBPF 的线程互补性分析方案设计文档

## 1. 背景与目的

在多核处理器系统中，**线程间的互补性**对于提升系统整体性能、优化调度策略具有重要意义。仅采集调度行为无法量化线程对核心资源的实际消耗，而单独采集核心性能事件又无法定位到具体线程。因此，**结合 CPU 核心性能事件与线程调度事件**，实现线程级别的定量归因，是分析和优化线程互补性的有效方法。

------

## 2. 数据采集方案

本方案采用 eBPF 工具链，分别采集以下两类数据：

- **（1）CPU核心性能事件数据**：通过 perf_event 机制，定期记录每个 CPU 核心的 cycles、instructions、cache-misses、branch-misses、L1/L2/DTLB/ITLB-misses 等硬件性能事件统计。
- **（2）线程调度事件数据**：通过跟踪 `sched_switch` 事件，实时记录每个核心上线程的切入与切出时刻，以及对应的 PID/线程名等信息。

### 数据格式举例

#### CPU核心性能数据（简化版）

| time                | cpu  | cycles   | instructions | ...  |
| ------------------- | ---- | -------- | ------------ | ---- |
| 2025-05-16 15:39:39 | 0    | 87008510 | 66730525     | ...  |

#### 线程调度事件数据

| ts (ns)        | cpu  | prev_comm | prev_pid | next_comm | next_pid |
| -------------- | ---- | --------- | -------- | --------- | -------- |
| 27939446819484 | 0    | swapper   | 0        | code      | 4571     |

## 3. 数据对齐与归因分析方法

### 3.1 对齐原理

- **窗口归因法**：以CPU性能事件采样时刻为基准窗口，将窗口内活跃的线程与性能计数对应。
- **最近调度法**：每条CPU性能数据，归因给同一CPU核上最近一次发生的 `sched_switch` 事件中的活跃线程。
- **比例归因法（可选，精细化分析）**：统计一个采样窗口内各线程实际运行时间的占比，将该窗口的性能指标按比例分配给不同线程。

### 3.2 示例代码片段

```python
import pandas as pd

cpu_df = pd.read_csv('cpu.csv', sep='\s+', header=None, names=[
    'time', 'cpu', 'cycles', 'instructions', 'event3', 'event4', 'event5', 'event6', 'event7', 'event8', 'event9', 'event10', 'role', 'flag'
])
sched_df = pd.read_csv('sched.csv')  # ts, cpu, prev_comm, prev_pid, next_comm, next_pid

# 转为纳秒时间戳
cpu_df['ts'] = pd.to_datetime(cpu_df['time']).astype('int64')

def find_last_thread(row):
    ts = row['ts']
    cpu = row['cpu']
    match = sched_df[(sched_df['cpu']==cpu) & (sched_df['ts']<=ts)]
    if match.empty:
        return pd.Series({'thread': None, 'pid': None})
    last = match.iloc[-1]
    return pd.Series({'thread': last['next_comm'], 'pid': last['next_pid']})

cpu_df[['thread', 'pid']] = cpu_df.apply(find_last_thread, axis=1)
cpu_df.to_csv('cpu_thread_attributed.csv', index=False)

```

## 4. 为什么不只用调度事件进行分析？

- **调度事件（sched_switch）仅能反映线程的切换行为**，但无法直接获得每个线程在调度期间消耗的 cycles、指令数、cache misses 等关键性能数据。
- **CPU核心性能数据能定量反映资源消耗**，但无法直接映射到具体线程。
- 只有将**调度事件与性能事件结合**，才能**准确评估每个线程在各核上的真实硬件利用率**，进而挖掘和解释线程间的互补关系、性能瓶颈与调度优化空间。

------

## 5. 方法优势总结

- **精确归因**：实现线程-核心-性能三者一一对应，支持定量分析各线程对系统瓶颈的贡献。
- **细粒度分析**：支持窗口/时间片级别的互补性度量，适用于 SMT/NUMA 等复杂多核系统。
- **可扩展性强**：可灵活拓展支持更多 eBPF 性能事件或自定义线程调度行为分析。
- **论文应用价值**：方法学清晰、实验数据解释性强、便于支持实际调度优化与多线程算法评估。

------

## 6. 参考建议

如需进一步提升分析精度，可考虑：

- 采样窗口自适应（窗口大小动态调整）
- 结合上下文切换（context switch）原因、线程优先级等信息
- 可视化线程在多核下的协作与竞争关系