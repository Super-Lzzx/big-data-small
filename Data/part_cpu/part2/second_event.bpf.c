#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "second_event.h"

// eBPF perf_event_array
struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(__u32));
    __uint(value_size, sizeof(__u32));
} events SEC(".maps");

// 采集 L1 缓存未命中率
SEC("perf_event")
int trace_perf_event(struct bpf_perf_event_data *ctx) {
    struct event_t event = {};
    __u32 cpu = bpf_get_smp_processor_id();
    event.cpu = cpu;

    // 读取 L1 指令缓存和数据缓存未命中次数
    event.l1_icache_misses = bpf_perf_event_read(&events, 0);  // L1 ICACHE MISS
    event.l1_dcache_misses = bpf_perf_event_read(&events, 1);  // LD MISS L1

    // Debug 输出
    bpf_printk("CPU %d - L1 ICache Misses: %llu, L1 DCache Misses: %llu",
                event.cpu, event.l1_icache_misses, event.l1_dcache_misses);

    // 发送数据到用户态
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char _license[] SEC("license") = "GPL";
