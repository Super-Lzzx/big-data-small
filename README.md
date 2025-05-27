big-data-small/
├── README.md                # 项目概览和使用说明
├── docs/                    # 设计文档与综合指南
│   └── comprehensive_thread_complementarity_guide.md
├── scripts/                 # 一键式运行脚本
│   ├── collect_and_align.py
│   ├── run_all.sh
│   ├── run_monitor.sh
│   └── measure_overhead.sh
├── src/analysis/            # 分析与可视化代码
│   ├── align_thread.py
│   ├── analyze_loads.py
│   └── overhead.py
├── data/                    # 原始与中间数据
│   ├── raw/                 # 采集原始 CSV
│   │   ├── cpu.csv
│   │   └── sched.csv
│   ├── processed/           # 归因后结果
│   │   └── cpu_thread_attr.csv
│   ├── monitor/             # 系统监控数据
│   │   ├── cpu_util.csv
│   │   ├── io_stat.csv
│   │   ├── vmstat.csv
│   │   └── performance_data.csv
│   └── overhead/            # 硬件事件开销数据
│       └── monitor_overhead.csv
├── Data/                     # 采集程序二进制
│   ├── cpu/
│   │   └── data
│   └── thread/
│       └── data_thread
├── results/                 # 各场景最终结果和图表
│   ├── cpu/
│   ├── io/
│   ├── memory/
│   └── prod_mixed/
└── stress-results/          # 压力测试工具专用输出
    ├── cpu/
    ├── io/
    └── mem/
