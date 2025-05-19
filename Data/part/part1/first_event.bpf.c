#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "first_event.h"

// eBPF perf_event_array
struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(__u32));
    __uint(value_size, sizeof(__u32));
} events SEC(".maps");

// 采集多个 perf 事件
SEC("perf_event")
int trace_perf_event(struct bpf_perf_event_data *ctx) {
    struct event_t event = {};
    __u32 cpu = bpf_get_smp_processor_id();
    event.cpu = cpu;

    // 读取多个 perf 事件
    event.cpu_cycles = bpf_perf_event_read(&events, cpu);
    event.instructions = bpf_perf_event_read(&events, 1);
    event.cache_misses = bpf_perf_event_read(&events, 2);
    event.branch_instructions = bpf_perf_event_read(&events, 3);
    event.branch_misses = bpf_perf_event_read(&events, 4);
    // event.l1_dcache_loads = bpf_perf_event_read(&events, 5);
    // event.l1_dcache_load_misses = bpf_perf_event_read(&events, 6);
    // event.l1_icache_loads = bpf_perf_event_read(&events, 7);
    // event.l1_icache_load_misses = bpf_perf_event_read(&events, 8);
    // event.dtlb_loads = bpf_perf_event_read(&events, 9);
    // event.dtlb_load_misses = bpf_perf_event_read(&events, 10);

    // Debug 输出
    bpf_printk("CPU %d - Cycles: %llu, Instructions: %llu, Cache Misses: %llu",
                event.cpu, event.cpu_cycles, event.instructions, event.cache_misses);

    // 发送数据到用户态
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char _license[] SEC("license") = "GPL";
