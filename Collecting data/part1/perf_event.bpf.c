#include <linux/bpf.h>
#include <linux/ptrace.h>
#include <linux/perf_event.h>
#include <linux/if_ether.h>

BPF_PERF_OUTPUT(events);

// 用于传递给用户空间的结构体
struct data_t {
    __u64 run_inst_cmpl;
    __u64 run_cyc;
    __u64 l1_icache_miss;
    __u64 ld_miss_l1;
};

int monitor_perf(struct pt_regs *ctx) {
    struct data_t data = {};

    // 从 perf_event 获取硬件计数器数据
    data.run_inst_cmpl = bpf_perf_event_read("run_inst_cmpl");
    data.run_cyc = bpf_perf_event_read("run_cyc");
    data.l1_icache_miss = bpf_perf_event_read("l1_icache_miss");
    data.ld_miss_l1 = bpf_perf_event_read("ld_miss_l1");

    // 将数据发送给用户空间
    events.perf_submit(ctx, &data, sizeof(data));

    return 0;
}
