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

#define NUM_EVENTS 1  // 采集 iTLB Miss
#define MAX_CPUS 128  // 最多支持 128 个 CPU
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
    "iTLB-load-misses"
};

// perf 事件类型和配置
struct perf_event_attr perf_events[NUM_EVENTS] = {
    { .type = PERF_TYPE_HW_CACHE, .size = sizeof(struct perf_event_attr),
      .config = (PERF_COUNT_HW_CACHE_ITLB | 
                 (PERF_COUNT_HW_CACHE_OP_READ << 8) | 
                 (PERF_COUNT_HW_CACHE_RESULT_MISS << 16)), // iTLB Miss
      .disabled = 1, .exclude_kernel = 0, .exclude_hv = 1, .read_format = PERF_FORMAT_GROUP }
};

// 处理 `Ctrl+C`
void handle_sigint(int sig) {
    stop = 1;
    printf("\n收到 Ctrl+C，停止采集...\n");
}

// 创建 `perf_event_open`
int create_perf_event(int cpu, int event_idx) {
    int fd = syscall(__NR_perf_event_open, &perf_events[event_idx], -1, cpu, -1, 0);
    if (fd == -1) {
        perror("perf_event_open failed");
        fprintf(stderr, "Error opening perf_event on CPU %d for event %s: %s\n",
                cpu, event_names[event_idx], strerror(errno));
    } else {
        printf("成功打开事件: CPU %d (fd=%d)\n", cpu, fd);
    }
    return fd;
}

int main() {
    int fds[MAX_CPUS][NUM_EVENTS];
    uint64_t values[MAX_CPUS][NUM_EVENTS];
    char buf[4096];
    struct read_format *rf = (struct read_format *)buf;
    int cpu_count = get_cpu_count();
    int i, j, k;

    signal(SIGINT, handle_sigint);

    printf("开始采集 %d 个 CPU 的 iTLB-load-misses（每 %d 秒更新一次）\n", cpu_count, SAMPLE_INTERVAL);

    // 创建 perf 事件
    for (i = 0; i < cpu_count; i++) {
        for (j = 0; j < NUM_EVENTS; j++) {
            fds[i][j] = create_perf_event(i, j);
            if (fds[i][j] < 0) return -1;
        }
    }

    while (!stop) {
        printf("\n==========  采样数据  ==========\n");

        // 开启 perf 事件
        for (i = 0; i < cpu_count; i++) {
            for (j = 0; j < NUM_EVENTS; j++) {
                if (ioctl(fds[i][j], PERF_EVENT_IOC_RESET, 0) < 0)
                    perror("ioctl RESET failed");
                if (ioctl(fds[i][j], PERF_EVENT_IOC_ENABLE, 0) < 0)
                    perror("ioctl ENABLE failed");
            }
        }

        sleep(SAMPLE_INTERVAL);

        // 停止 perf 事件
        for (i = 0; i < cpu_count; i++) {
            ioctl(fds[i][0], PERF_EVENT_IOC_DISABLE, 0);
        }

        // 读取 perf 数据
        for (i = 0; i < cpu_count; i++) {
            ssize_t bytes_read = read(fds[i][0], buf, sizeof(buf));
            if (bytes_read < 0) {
                perror("read failed");
                continue;
            }

            for (k = 0; k < rf->nr; k++) {
                for (j = 0; j < NUM_EVENTS; j++) {
                    values[i][j] = rf->values[k].value;
                }
            }

            // 输出采样数据
            printf("CPU %d:\n", i);
            for (j = 0; j < NUM_EVENTS; j++) {
                printf("  %s - Value: %lu\n", event_names[j], values[i][j]);
            }
        }
    }

    // 关闭 perf 事件
    for (i = 0; i < cpu_count; i++) {
        for (j = 0; j < NUM_EVENTS; j++) close(fds[i][j]);
    }

    printf("采集结束\n");
    return 0;
}
