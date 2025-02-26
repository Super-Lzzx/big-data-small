#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "third_event.h"

struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(u32));
} events SEC(".maps");

SEC("perf_event")
int trace_perf_event(struct bpf_perf_event_data *ctx) {
    struct event_t event = {};
    __u32 cpu = bpf_get_smp_processor_id();

    event.ierat_reload = bpf_perf_event_read(&events, cpu);
    event.lsu_derat_miss = bpf_perf_event_read(&events, cpu);
    event.data_all_from_mem = bpf_perf_event_read(&events, cpu);

    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char _license[] SEC("license") = "GPL";
