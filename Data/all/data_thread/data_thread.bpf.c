#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include "data_thread.h"

struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 24);
} events SEC(".maps");

SEC("tracepoint/sched/sched_switch")
int on_switch(struct trace_event_raw_sched_switch *ctx)
{
    struct switch_event_t *e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
    if (!e) return 0;

    e->cpu = bpf_get_smp_processor_id();
    e->prev_pid = ctx->prev_pid;
    e->next_pid = ctx->next_pid;
    e->ts = bpf_ktime_get_ns();

    // 使用 bpf_probe_read_kernel 读取 comm 字段
    bpf_probe_read_kernel(e->prev_comm, sizeof(e->prev_comm), ctx->prev_comm);
    bpf_probe_read_kernel(e->next_comm, sizeof(e->next_comm), ctx->next_comm);

    bpf_ringbuf_submit(e, 0);
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
