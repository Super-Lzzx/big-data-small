#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "second_event.h"

struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(u32));
} events SEC(".maps");

SEC("perf_event")
int trace_perf_event(struct bpf_perf_event_data *ctx) {
    struct event_t event = {};
    __u32 cpu = bpf_get_smp_processor_id();

    // 读取 4 个新指标
    event.st_miss_l1 = bpf_perf_event_read(&events, cpu);    // L1 存储未命中
    event.data_from_l3 = bpf_perf_event_read(&events, cpu);  // 从 L3 读取数据
    event.llc_st_miss = bpf_perf_event_read(&events, cpu);   // LLC 存储未命中
    event.br_mpred_cmpl = bpf_perf_event_read(&events, cpu); // 分支预测命中数

    // 传输数据到用户态
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char _license[] SEC("license") = "GPL";
