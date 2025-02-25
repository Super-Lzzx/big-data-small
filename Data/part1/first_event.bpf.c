#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "first_event.h"

struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(u32));
} events SEC(".maps");

struct trace_event_raw_perf_event {
    uint32_t event_id;
    uint64_t value;
};

// 跟踪 CPU 性能事件：RUN INST CMPL
SEC("tracepoint/perf/perf_event")
int trace_perf_event(struct trace_event_raw_perf_event *ctx) {
    struct event_t event = {};

    // 通过 BPF_CORE_READ 获取每个性能事件的计数值
    if (ctx->event_id == 0x003) { // RUN INST CMPL
        event.run_inst_cmpl = BPF_CORE_READ(ctx, value);
    } else if (ctx->event_id == 0x008) { // RUN CYC
        event.run_cyc = BPF_CORE_READ(ctx, value);
    } else if (ctx->event_id == 0x001) { // L1 ICACHE MISS
        event.l1_icache_miss = BPF_CORE_READ(ctx, value);
    } else if (ctx->event_id == 0x011) { // LD MISS L1
        event.ld_miss_l1 = BPF_CORE_READ(ctx, value);
    }

    // 将采集的数据输出到用户空间
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}

char _license[] SEC("license") = "GPL";
