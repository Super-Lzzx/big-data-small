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
#include "third_event.skel.h"
#include "third_event.h"

static volatile bool exiting = false;

void handle_event(void *ctx, int cpu, void *data, __u32 data_size) {
    struct event_t *event = data;
    printf("CPU: %d | IERAT RELOAD: %llu | LSU DERAT MISS: %llu | DATA ALL FROM MEMORY: %llu\n",
           cpu, event->ierat_reload, event->lsu_derat_miss, event->data_all_from_mem);
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
    struct third_event_bpf *skel;
    struct perf_buffer *pb;
    int cpu, fd;
    struct perf_event_attr attr = {};

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    skel = third_event_bpf__open_and_load();
    if (!skel) {
        fprintf(stderr, "Failed to open and load BPF program\n");
        return 1;
    }

    attr.size = sizeof(struct perf_event_attr);
    attr.disabled = 0;
    attr.sample_period = 0;
    attr.sample_type = PERF_SAMPLE_RAW;
    attr.inherit = 1;
    attr.exclude_kernel = 0;
    attr.exclude_hv = 0;

    // 在每个 CPU 上创建 3 个 perf_event 计数器
    for (cpu = 0; cpu < sysconf(_SC_NPROCESSORS_ONLN); cpu++) {
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 0:
                    attr.type = PERF_TYPE_HW_CACHE;
                    attr.config = PERF_COUNT_HW_CACHE_ITLB | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16);
                    break;  // IERAT RELOAD（指令 TLB 重新加载）

                case 1:
                    attr.type = PERF_TYPE_HW_CACHE;
                    attr.config = PERF_COUNT_HW_CACHE_DTLB | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16);
                    break;  // LSU DERAT MISS（数据 TLB 未命中）

                case 2:
                    attr.type = PERF_TYPE_HW_CACHE;
                    attr.config = PERF_COUNT_HW_CACHE_LL | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16);
                    break;  // DATA ALL FROM MEMORY（从内存读取数据）
            }

            fd = perf_event_open(&attr, -1, cpu, -1, 0);
            if (fd < 0) {
                fprintf(stderr, "Failed to open perf event on CPU %d for metric %d: %s\n", cpu, i, strerror(errno));
                continue;
            }

            if (ioctl(fd, PERF_EVENT_IOC_SET_BPF, bpf_program__fd(skel->progs.trace_perf_event)) < 0) {
                fprintf(stderr, "Failed to attach BPF program to perf event on CPU %d for metric %d: %s\n", cpu, i, strerror(errno));
                close(fd);
                continue;
            }
        }
    }

    pb = perf_buffer__new(bpf_map__fd(skel->maps.events), 64, handle_event, handle_lost_event, NULL, NULL);
    if (libbpf_get_error(pb)) {
        fprintf(stderr, "Failed to create perf buffer\n");
        third_event_bpf__destroy(skel);
        return 1;
    }

    printf("Tracing CPU performance events...\n");

    while (!exiting) {
        perf_buffer__poll(pb, 100);
    }

    perf_buffer__free(pb);
    third_event_bpf__destroy(skel);
    return 0;
}
