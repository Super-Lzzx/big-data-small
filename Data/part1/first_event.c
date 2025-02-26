#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/syscall.h>
#include <sys/resource.h>
#include <linux/perf_event.h>
#include "first_event.skel.h"
#include "first_event.h"

static volatile bool exiting = false;

void handle_event(void *ctx, int cpu, void *data, __u32 data_size) {
    struct event_t *event = data;
    printf("CPU: %d | RUN INST CMPL: %llu | RUN CYC: %llu | L1 ICACHE MISS: %llu | LD MISS L1: %llu\n",
           cpu, event->run_inst_cmpl, event->run_cyc, event->l1_icache_miss, event->ld_miss_l1);
}

void handle_lost_event(void *ctx, int cpu, __u64 lost_cnt) {
    fprintf(stderr, "Lost %llu events on CPU %d\n", lost_cnt, cpu);
}

void sig_handler(int sig) {
    exiting = true;
}

int perf_event_open(struct perf_event_attr *attr, pid_t pid, int cpu, int group_fd, unsigned long flags) {
    return syscall(__NR_perf_event_open, attr, pid, cpu, group_fd, flags);
}

int main() {
    struct first_event_bpf *skel;
    struct perf_buffer *pb;
    int cpu, fd;
    struct perf_event_attr attr = {};

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    skel = first_event_bpf__open_and_load();
    if (!skel) {
        fprintf(stderr, "Failed to open and load BPF program\n");
        return 1;
    }

    attr.type = PERF_TYPE_SOFTWARE;  // ✅ 兼容虚拟机
    attr.size = sizeof(struct perf_event_attr);
    attr.config = PERF_COUNT_SW_CPU_CLOCK;  // ✅ 代替硬件计数器
    attr.disabled = 0;
    attr.sample_period = 0;
    attr.sample_type = PERF_SAMPLE_RAW;
    attr.inherit = 1;
    attr.exclude_kernel = 0;
    attr.exclude_hv = 0;

    for (cpu = 0; cpu < sysconf(_SC_NPROCESSORS_ONLN); cpu++) {
        fd = perf_event_open(&attr, -1, cpu, -1, 0);
        if (fd < 0) {
            fprintf(stderr, "Failed to open perf event on CPU %d: %s\n", cpu, strerror(errno));
            first_event_bpf__destroy(skel);
            return 1;
        }

        if (ioctl(fd, PERF_EVENT_IOC_SET_BPF, bpf_program__fd(skel->progs.trace_perf_event)) < 0) {
            fprintf(stderr, "Failed to attach BPF program to perf event on CPU %d: %s\n", cpu, strerror(errno));
            close(fd);
            first_event_bpf__destroy(skel);
            return 1;
        }
    }

    pb = perf_buffer__new(bpf_map__fd(skel->maps.events), 64, handle_event, handle_lost_event, NULL, NULL);
    if (libbpf_get_error(pb)) {
        fprintf(stderr, "Failed to create perf buffer\n");
        first_event_bpf__destroy(skel);
        return 1;
    }

    printf("Tracing CPU performance events...\n");

    while (!exiting) {
        perf_buffer__poll(pb, 100);
    }

    perf_buffer__free(pb);
    first_event_bpf__destroy(skel);
    return 0;
}
