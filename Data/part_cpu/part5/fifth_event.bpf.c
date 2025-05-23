#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "fifth_event.h"

struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(__u32));
    __uint(value_size, sizeof(__u32));
} events SEC(".maps");

SEC("perf_event")
int count_dtlb_misses(struct bpf_perf_event_data *ctx) {
    __u32 cpu = bpf_get_smp_processor_id();
    struct event_t event = {};
    
    event.cpu = cpu;
    event.dtlb_misses = ctx->sample_period;

    bpf_perf_event_output(ctx, &perf_event_map, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
