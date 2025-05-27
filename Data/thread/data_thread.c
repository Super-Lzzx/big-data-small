#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <string.h>
#include <bpf/libbpf.h>
#include <sys/resource.h>
#include "data_thread.skel.h"
#include "data_thread.h"
#include <errno.h>

static volatile int exiting = 0;

static void sig_handler(int sig) {
    exiting = 1;
}

static int handle_event(void *ctx, void *data, size_t data_sz) {
    struct switch_event_t *e = data;

    // 原有打印可保留
    printf("CPU:%2u | %s(%d) --> %s(%d) | ts:%llu\n",
           e->cpu, e->prev_comm, e->prev_pid, e->next_comm, e->next_pid, e->ts);

    // 新增写入CSV文件
    FILE *fp = fopen("sched.csv", "a");
    if (fp) {
        fprintf(fp, "%llu,%u,%s,%d,%s,%d\n",
            e->ts,
            e->cpu,
            e->prev_comm,
            e->prev_pid,
            e->next_comm,
            e->next_pid);
        fclose(fp);
    }
    return 0;
}

int main()
{
    // 检查 sched.csv 是否存在，不存在则写表头
    FILE *fp = fopen("sched.csv", "r");
    if (!fp) { // 文件不存在，写表头
        fp = fopen("sched.csv", "w");
        if (fp) {
            fprintf(fp, "ts,cpu,prev_comm,prev_pid,next_comm,next_pid\n");
            fclose(fp);
        }
    } else {
        fclose(fp); // 文件已存在
    }

    struct rlimit r = {RLIM_INFINITY, RLIM_INFINITY};
    setrlimit(RLIMIT_MEMLOCK, &r);
    struct data_thread_bpf *skel = data_thread_bpf__open_and_load();
    if (!skel) {
        fprintf(stderr, "Failed to open/load skeleton\n");
        return 1;
    }
    if (data_thread_bpf__attach(skel)) {
        fprintf(stderr, "Failed to attach skeleton\n");
        data_thread_bpf__destroy(skel);
        return 1;
    }

    struct ring_buffer *rb = ring_buffer__new(
        bpf_map__fd(skel->maps.events), handle_event, NULL, NULL);
    if (!rb) {
        fprintf(stderr, "Failed to create ring buffer: %s\n", strerror(errno));
        data_thread_bpf__destroy(skel);
        return 1;
    }

    printf("Tracing sched_switch... Press Ctrl+C to stop.\n");
    signal(SIGINT, sig_handler);

    while (!exiting) {
        int err = ring_buffer__poll(rb, 100);
        if (err < 0 && errno != EINTR) {
            printf("Ring buffer poll error: %d\n", err);
            break;
        }
    }

    ring_buffer__free(rb);
    data_thread_bpf__destroy(skel);
    return 0;
}
