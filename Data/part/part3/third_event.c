#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <string.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <linux/hw_breakpoint.h>
#include <asm/unistd.h>
#include <errno.h>
#include <stdint.h>
#include <inttypes.h>
#include <sched.h>
#include <signal.h>

#define NUM_EVENTS 1  // 只采集 L2 Cache Miss
#define MAX_CPUS 128  // 假设最多 128 个 CPU
#define SAMPLE_INTERVAL 5  // 采样间隔（秒）

volatile sig_atomic_t stop = 0;  // 处理 Ctrl+C 退出

struct read_format {
    uint64_t nr;
    struct {
        uint64_t value;
        uint64_t id;
    } values[];
};

// 获取 CPU 数量
int get_cpu_count() {
    cpu_set_t mask;
    CPU_ZERO(&mask);
    sched_getaffinity(0, sizeof(mask), &mask);
    return CPU_COUNT(&mask);
}

// 事件名称
const char* event_names[NUM_EVENTS] = {
    "ALL_L2_CACHE_MISSES"
};

// L2 Cache Miss 事件 ID（请用 `perf list --details all_l2_cache_misses` 确认）
const uint64_t event_ids[NUM_EVENTS] = {
    0x26a1  // L2 Cache Miss
};

// 创建 `perf_event_open`
int create_perf_event(int cpu, int grp_fd, int event_idx, uint64_t *ioc_id) {
    struct perf_event_attr pea;
    memset(&pea, 0, sizeof(struct perf_event_attr));
    pea.type = PERF_TYPE_RAW;  // 使用 raw event
    pea.size = sizeof(struct perf_event_attr);
    pea.config = event_ids[event_idx];  // 绑定 L2 事件

    pea.disabled = 1;
    pea.exclude_kernel = 0;
    pea.exclude_hv = 1;
    pea.read_format = PERF_FORMAT_GROUP | PERF_FORMAT_ID;

    int fd = syscall(__NR_perf_event_open, &pea, -1, cpu, grp_fd > 2 ? grp_fd : -1, 0);
    if (fd == -1) {
        perror("perf_event_open failed");
        fprintf(stderr, "Error opening perf_event on CPU %d for event %s: %s\n",
                cpu, event_names[event_idx], strerror(errno));
    }
    ioctl(fd, PERF_EVENT_IOC_ID, ioc_id);
    return fd;
}

// 处理 `Ctrl+C`
void handle_sigint(int sig) {
    stop = 1;
    printf("\n收到 Ctrl+C，停止采集...\n");
}

int main() {
    int fds[MAX_CPUS][NUM_EVENTS];
    uint64_t ids[MAX_CPUS][NUM_EVENTS];
    uint64_t values[MAX_CPUS][NUM_EVENTS];
    char buf[4096];
    struct read_format *rf = (struct read_format *)buf;
    int cpu_count = get_cpu_count();
    int i, j, k;

    signal(SIGINT, handle_sigint);

    printf("开始采集 %d 个 CPU 的 L2 Cache Miss（每 %d 秒更新一次）\n", cpu_count, SAMPLE_INTERVAL);

    for (i = 0; i < cpu_count; i++) {
        fds[i][0] = create_perf_event(i, -1, 0, &ids[i][0]);
        if (fds[i][0] < 0) return -1;
    }

    while (!stop) {
        printf("\n==========  采样数据  ==========\n");

        for (i = 0; i < cpu_count; i++) {
            ioctl(fds[i][0], PERF_EVENT_IOC_RESET, 0);
            ioctl(fds[i][0], PERF_EVENT_IOC_ENABLE, 0);
        }

        sleep(SAMPLE_INTERVAL);

        for (i = 0; i < cpu_count; i++) {
            ioctl(fds[i][0], PERF_EVENT_IOC_DISABLE, 0);
        }

        for (i = 0; i < cpu_count; i++) {
            ssize_t bytes_read = read(fds[i][0], buf, sizeof(buf));
            if (bytes_read < 0) {
                perror("read failed");
                return -1;
            }

            for (k = 0; k < rf->nr; k++) {
                for (j = 0; j < NUM_EVENTS; j++) {
                    if (rf->values[k].id == ids[i][j]) {
                        values[i][j] = rf->values[k].value;
                    }
                }
            }

            printf("CPU %d:\n", i);
            printf("  %s - Value: %lu\n", event_names[0], values[i][0]);
        }
    }

    printf("采集结束\n");
    return 0;
}
