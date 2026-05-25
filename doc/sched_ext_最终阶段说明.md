# sched_ext 最终阶段说明

当前仓库已经完成：

1. 第 3 章采集与归因数据链路。
2. 第 4 章 XGBoost 下一窗口预测与互补性评分。
3. 第 5 章 MAGM 选核决策。
4. 用户态 `sched_setaffinity` 真实绑核验证。

## 当前机器的限制

当前运行环境为 Ubuntu `6.8.0-111-generic`。该内核没有启用 sched_ext：

- `/sys/kernel/sched_ext` 不存在。
- `/boot/config-$(uname -r)` 中没有 `CONFIG_SCHED_CLASS_EXT=y`。
- `/sys/kernel/btf/vmlinux` 中没有 `sched_ext_ops` / `scx_bpf` 类型符号。

因此，这台机器无法加载真正的 sched_ext BPF 调度器。这个限制来自内核能力，不是用户态代码可以绕过的问题。

## 目前可执行的最终阶段

使用用户态绑核验证：

```bash
python3 scripts/run_magm_scheduler.py --mode affinity --load-type cpu --duration 30
```

或者直接运行：

```bash
python3 scripts/run_live_affinity_validation.py --load-type cpu --duration 30
```

输出：

- `results/scheduler/live_affinity_report.csv`

该文件记录了真实运行负载的 live TID、目标 CPU、绑定前后的 affinity。

## sched_ext 检测

```bash
python3 scripts/check_sched_ext.py
```

如果未来切换到带 sched_ext 的内核，应至少满足：

- `CONFIG_SCHED_CLASS_EXT=y`
- `CONFIG_BPF_SYSCALL=y`
- `CONFIG_DEBUG_INFO_BTF=y`
- `/sys/kernel/sched_ext` 存在
- 内核 BTF 中存在 `sched_ext_ops` 与 `scx_bpf` 相关符号

满足这些条件后，才能继续实现并加载真正的 `struct sched_ext_ops` BPF 调度器。
