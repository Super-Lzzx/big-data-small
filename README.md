# 项目目录结构

- **big-data-small/**  
  项目根目录，包含所有脚本、文档、数据和结果。

  - **README.md**  
    项目概览和使用说明。

  - **docs/**  
    设计文档与综合指南。  
    - **comprehensive_thread_complementarity_guide.md**  
      线程互补性分析 & 负载测试综合指南。

  - **scripts/**  
    自动化运行脚本目录。  
    - **collect_and_align.py**  
      自动化采集（eBPF + perf）并归因脚本。  
    - **run_all.sh**  
      多负载采集脚本（依次执行各种 `stress-ng`/`sysbench` 等命令）。  
    - **run_monitor.sh**  
      系统监控（sar/iostat/vmstat/perf stat）+ 多负载采集一体化脚本。  
    - **measure_overhead.sh**  
      perf stat 硬件事件开销测量脚本。

  - **src/analysis/**  
    分析与可视化 Python 代码。  
    - **align_thread.py**  
      将 `data/raw/` 中的 CPU 事件与调度事件做归因，输出到 `data/processed/`。  
    - **analyze_loads.py**  
      负载特征分析脚本（箱线图、PCA、分类验证等）。  
    - **overhead.py**  
      绘制 perf stat 开销对比图（时间与 CPU 占用率）。

  - **data/**  
    存放原始与中间数据。  
    - **raw/**  
      采集程序输出的原始 CSV 文件：  
      - **cpu.csv**  
        CPU 性能事件原始数据（每秒/每毫秒采样）。  
      - **sched.csv**  
        eBPF 跟踪的 `sched_switch` 原始调度事件。  
    - **processed/**  
      数据归因后和清洗后的结果：  
      - **cpu_thread_attr.csv**  
        将 CPU 事件归因到线程后的完整表格。  
    - **monitor/**  
      系统级监控数据（sar/iostat/vmstat/perf stat）：  
      - **cpu_util.csv**  
        SAR 采集的 CPU 利用率。  
      - **io_stat.csv**  
        iostat 采集的 I/O 统计。  
      - **vmstat.csv**  
        vmstat 输出。  
      - **performance_data.csv**  
        多负载采集脚本 `run_all.sh` 生成的原始数据。  
    - **overhead/**  
      perf stat 硬件事件开销数据：  
      - **monitor_overhead.csv**  
        不同监控模式（perf/ptrace/ebpf）的时间 & CPU 占用汇总。

  - **bin/**  
    采集程序二进制目录（原 `Data/` 重命名）：  
    - **cpu/**  
      - **data**  
        用户态 perf 采集可执行文件。  
    - **thread/**  
      - **data_thread**  
        eBPF 线程调度采集可执行文件。

  - **results/**  
    各场景实验结果和生成的图表：  
    - **cpu/**  
      纯 CPU 场景的 CSV & 图表。  
    - **io/**  
      纯 I/O 场景的 CSV & 图表。  
    - **memory/**  
      纯内存场景的 CSV & 图表。  
    - **prod_mixed/**  
      生产型混合场景的 CSV & 图表。

  - **stress-results/**  
    压力测试工具（stress-ng/fio/sysbench 等）原始输出：  
    - **cpu/**  
    - **io/**  
    - **mem/**  