// SPDX-License-Identifier: GPL-2.0
/*
 * MAGM sched_ext prototype.
 *
 * This BPF scheduler consumes a userspace-provided TID -> target CPU map.  It is
 * intended to be built and loaded on kernels with CONFIG_SCHED_CLASS_EXT=y.
 * The current development machine may not expose sched_ext in BTF, so this file
 * is kept as the portable implementation that can be moved to an scx-capable
 * host.
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#include "magm_scx.h"

#ifndef SCX_SLICE_DFL
#define SCX_SLICE_DFL 20000000ULL
#endif

#ifndef SCX_DSQ_GLOBAL
#define SCX_DSQ_GLOBAL ((u64)1 << 63)
#endif

char LICENSE[] SEC("license") = "GPL";

/*
 * Written by userspace from final_cpu_selection.csv or another online MAGM
 * decision source.  Key is Linux TID (task_struct::pid), value is logical CPU.
 */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 65536);
    __type(key, u32);
    __type(value, u32);
} target_cpu_by_tid SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, u32);
    __type(value, struct magm_stat);
} stats SEC(".maps");

/*
 * sched_ext kfuncs.  They are resolved from the target kernel BTF, so the
 * build host must expose sched_ext symbols through /sys/kernel/btf/vmlinux.
 */
extern s32 scx_bpf_select_cpu_dfl(struct task_struct *p, s32 prev_cpu,
                                  u64 wake_flags, bool *is_idle) __ksym;
extern void scx_bpf_dsq_insert(struct task_struct *p, u64 dsq_id, u64 slice,
                               u64 enq_flags) __ksym;

static __always_inline void bump_stat(bool selected)
{
    u32 key = 0;
    struct magm_stat *stat = bpf_map_lookup_elem(&stats, &key);

    if (!stat)
        return;
    if (selected)
        __sync_fetch_and_add(&stat->selected_tasks, 1);
    else
        __sync_fetch_and_add(&stat->fallback_tasks, 1);
}

static __always_inline bool task_target_cpu(struct task_struct *p, s32 *cpu)
{
    u32 tid = BPF_CORE_READ(p, pid);
    u32 *target = bpf_map_lookup_elem(&target_cpu_by_tid, &tid);

    if (!target)
        return false;
    *cpu = (s32)*target;
    return true;
}

s32 BPF_STRUCT_OPS(magm_select_cpu, struct task_struct *p, s32 prev_cpu,
                   u64 wake_flags)
{
    bool is_idle = false;
    s32 cpu;

    /*
     * The MAGM decision is a placement hint at wakeup time.  If a task is not
     * in the map, fall back to the kernel's default sched_ext CPU choice.
     */
    if (task_target_cpu(p, &cpu)) {
        bump_stat(true);
        return cpu;
    }

    bump_stat(false);
    return scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
}

void BPF_STRUCT_OPS(magm_enqueue, struct task_struct *p, u64 enq_flags)
{
    /*
     * Keep dispatching simple: tasks enter the global DSQ and sched_ext uses
     * select_cpu's placement decision when the task becomes runnable.  A later
     * production version can replace this with per-CPU DSQs if stricter binding
     * semantics are required.
     */
    scx_bpf_dsq_insert(p, SCX_DSQ_GLOBAL, SCX_SLICE_DFL, enq_flags);
}

SEC(".struct_ops.link")
struct sched_ext_ops magm_ops = {
    .select_cpu = (void *)magm_select_cpu,
    .enqueue = (void *)magm_enqueue,
    .name = "magm_scx",
};
