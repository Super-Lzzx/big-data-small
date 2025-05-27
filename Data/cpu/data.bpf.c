#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
// 不再包含 <stdint.h>！
#include "data.h"

// Perf event map，和用户态 perf_event_array 一一对应
struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(__u32));
    __uint(value_size, sizeof(__u32));
} events SEC(".maps");

// 核心 trace 程序
SEC("perf_event")
int trace_perf_event(struct bpf_perf_event_data *ctx) {
    struct event_t event = {};
    __u32 cpu = bpf_get_smp_processor_id();
    event.cpu = cpu;

    // 这里的索引和你在用户态 perf_event_open 时的 event 顺序保持一致
    event.cpu_cycles         = bpf_perf_event_read(&events, 0);
    event.instructions       = bpf_perf_event_read(&events, 1);
    event.cache_misses       = bpf_perf_event_read(&events, 2);
    event.branch_instructions= bpf_perf_event_read(&events, 3);
    event.branch_misses      = bpf_perf_event_read(&events, 4);

    event.l1_icache_misses   = bpf_perf_event_read(&events, 5);
    event.l1_dcache_misses   = bpf_perf_event_read(&events, 6);

    event.itlb_misses        = bpf_perf_event_read(&events, 7);

    event.l2_cache_misses    = bpf_perf_event_read(&events, 8);

    event.dtlb_misses        = bpf_perf_event_read(&events, 9);

    // 输出到 perf_event_array，用户态用 read() 拿到
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
