# MAGM sched_ext 原型

这个目录保存论文中 sched_ext 落地部分的原型代码。当前开发机器没有启用 `sched_ext`，所以这里的代码用于迁移到支持 `CONFIG_SCHED_CLASS_EXT=y` 的内核上编译和运行。

## 文件

- `magm_scx.bpf.c`：真正的 sched_ext BPF 调度器，定义 `struct sched_ext_ops magm_ops`。
- `magm_scx.c`：用户态 loader，读取 MAGM 生成的 `final_cpu_selection.csv`，写入 `TID -> CPU` BPF map，并 attach 调度器。
- `magm_scx.h`：BPF 和用户态共享结构。
- `Makefile`：在支持 sched_ext 的机器上生成 skeleton 并编译 loader。

## 目标机器要求

- Linux 内核启用 `CONFIG_SCHED_CLASS_EXT=y`
- `/sys/kernel/sched_ext` 存在
- `/sys/kernel/btf/vmlinux` 中包含 `sched_ext_ops` 和 `scx_bpf` 符号
- 已安装 `clang`、`bpftool`、`libbpf-dev`、`libelf-dev`、`zlib1g-dev`

可以先运行仓库中的检测脚本：

```bash
python3 scripts/check_sched_ext.py
```

## 编译

```bash
cd sched_ext
make
```

如果目标机的 BTF 路径不同：

```bash
make VMLINUX_BTF=/path/to/vmlinux.btf
```

## 运行

先在仓库根目录生成 MAGM 选核结果：

```bash
python3 scripts/build_thread_windows.py
python3 scripts/train_thread_predictor.py
python3 scripts/offline_magm_scheduler.py
python3 scripts/export_cpu_selection.py
```

然后在支持 sched_ext 的机器上加载调度器：

```bash
cd sched_ext
sudo ./magm_scx ../data/processed/final_cpu_selection.csv
```

按 `Ctrl+C` 会 detach 调度器。

## 说明

当前实现是原型：它把 `final_cpu_selection.csv` 中的历史 TID 映射写入 BPF map，并在 `select_cpu` 阶段优先返回 MAGM 指定的目标 CPU。若任务不在 map 中，则回退到 sched_ext 默认选核逻辑。

生产化版本还应继续补齐：

- 在线采集当前 live TID，而不是使用离线 CSV 中的历史 TID。
- 周期性刷新 BPF map，对应论文中的窗口级闭环控制。
- 使用 per-CPU DSQ 或更严格的迁移策略强化绑定语义。
- 在 loader 中接入 XGBoost 在线预测和 MAGM 配对决策。
