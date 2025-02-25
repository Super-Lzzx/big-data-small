#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/resource.h>
#include <linux/perf_event.h>
#include "first_event.skel.h"
#include "first_event.h"

struct Event {
    uint64_t run_inst_cmpl;
    uint64_t run_cyc;
    uint64_t l1_icache_miss;
    uint64_t ld_miss_l1;
};

// 解析事件的回调函数
void parse_event(void *ctx, int cpu, void *data, __u32 data_size) {
    struct event_t *event = data;
    // 将 %llu 修改为 %lu
    printf("CPU: %d, RUN INST CMPL: %lu, RUN CYC: %lu, L1 ICACHE MISS: %lu, LD MISS L1: %lu\n", 
           cpu, event->run_inst_cmpl, event->run_cyc, event->l1_icache_miss, event->ld_miss_l1);
}

// 丢失事件的处理
void lost_event(void *ctx, int cpu, __u64 lost_cnt) {
    fprintf(stderr, "lost %llu events on CPU %d\n", lost_cnt, cpu);
}

static volatile bool exiting = false;

// 信号处理函数
void sig_handler(int sig) {
    exiting = true;
}

int main(int argc, char **argv) {
    struct first_event_bpf *bpf_obj = NULL;
    struct bpf_program *prog;
    struct perf_buffer *pb = NULL;
    int err;

    // 打开和加载 BPF 对象文件
    bpf_obj = first_event_bpf__open();
    if (!bpf_obj) {
        fprintf(stderr, "Failed to open BPF object\n");
        return 1;
    }

    err = first_event_bpf__load(bpf_obj);
    if (err) {
        fprintf(stderr, "Failed to load BPF object: %d\n", err);
        first_event_bpf__destroy(bpf_obj);
        return 1;
    }

    // 遍历并附加每个 BPF 程序到 tracepoint
    bpf_object__for_each_program(prog, bpf_obj->obj) {
        if (bpf_program__attach_tracepoint(prog, "perf", "perf_event") != 0) {
            fprintf(stderr, "Failed to attach tracepoint\n");
            return 1;
        }
    }

    printf("Tracing...\n");

    // 获取 events map 的文件描述符
    int map_fd = bpf_map__fd(bpf_object__find_map_by_name(bpf_obj->obj, "events"));
    if (map_fd < 0) {
        fprintf(stderr, "Failed to find map 'events'\n");
        return 1;
    }

    // 打开 Perf Buffer
    pb = perf_buffer__new(map_fd, 1024, parse_event, lost_event, NULL, NULL);
    if (libbpf_get_error(pb)) {
        fprintf(stderr, "Failed to open perf buffer\n");
        return 1;
    }

    // 设置信号处理
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    // 主循环，等待事件
    while (!exiting) {
        err = perf_buffer__poll(pb, 100);
        if (err < 0 && errno != EINTR) {
            fprintf(stderr, "Error polling perf buffer: %d\n", err);
            break;
        }
    }

    printf("Bye bye~\n");

    // 清理资源
    perf_buffer__free(pb);
    first_event_bpf__destroy(bpf_obj);

    return 0;
}
