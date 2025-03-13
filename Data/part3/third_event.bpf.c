#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "third_event.h"

// eBPF perf_event_array
struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(__u32));
    __uint(value_size, sizeof(__u32));
} events SEC(".maps");

// 采集 L2、L3 缓存未命中
SEC("perf_event")
int trace_perf_event(struct bpf_perf_event_data *ctx) {
    struct event_t event = {};
    __u32 cpu = bpf_get_smp_processor_id();
    event.cpu = cpu;

    // 读取 L2 和 L3 缓存未命中数
    event.l2_cache_misses = bpf_perf_event_read(&events, 0);  // L2 CACHE MISS
    // event.l3_cache_misses = bpf_perf_event_read(&events, 1);  // L3 CACHE MISS

    // Debug 输出
    bpf_printk("CPU %d - L2 Cache Misses: %llu",
                event.cpu, event.l2_cache_misses);

    // 发送数据到用户态
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char _license[] SEC("license") = "GPL";
