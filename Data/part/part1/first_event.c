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

#define NUM_EVENTS 5  // 监控的事件数量
#define MAX_CPUS 128  // 假设最多 128 个 CPU
#define SAMPLE_INTERVAL 5  // 采样间隔（秒）

volatile sig_atomic_t stop = 0;  // 处理 Ctrl+C 退出

// `perf_event_open()` 读取的数据格式
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

// `perf` 事件 ID 和名称
enum perf_hw_id events[NUM_EVENTS] = {
    PERF_COUNT_HW_CPU_CYCLES,         // CPU Cycles
    PERF_COUNT_HW_INSTRUCTIONS,       // Instructions Retired
    PERF_COUNT_HW_CACHE_MISSES,       // Cache Misses
    PERF_COUNT_HW_BRANCH_INSTRUCTIONS,// Branch Instructions
    PERF_COUNT_HW_BRANCH_MISSES       // Branch Misses
};

const char* event_names[NUM_EVENTS] = {
    "CPU_CYCLES",
    "INSTRUCTIONS",
    "CACHE_MISSES",
    "BRANCH_INSTRUCTIONS",
    "BRANCH_MISSES"
};

// 创建 `perf_event_open`
int create_perf_event(int cpu, int grp_fd, enum perf_hw_id event, uint64_t *ioc_id) {
    struct perf_event_attr pea;
    memset(&pea, 0, sizeof(struct perf_event_attr));
    pea.type = PERF_TYPE_HARDWARE;
    pea.size = sizeof(struct perf_event_attr);
    pea.config = event;
    pea.disabled = 1;
    pea.exclude_kernel = 0;
    pea.exclude_hv = 1;
    pea.read_format = PERF_FORMAT_GROUP | PERF_FORMAT_ID;

    int fd = syscall(__NR_perf_event_open, &pea, -1, cpu, grp_fd > 2 ? grp_fd : -1, 0);
    if (fd == -1) {
        perror("perf_event_open failed");
        return -1;
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

    // 捕获 `Ctrl+C`，停止程序
    signal(SIGINT, handle_sigint);

    if (cpu_count > MAX_CPUS) {
        printf("CPU 数量超过限制，请增加 MAX_CPUS\n");
        return -1;
    }

    printf("开始采集 %d 个 CPU 的硬件事件（每秒更新一次，按 Ctrl+C 停止）\n", cpu_count);

    // 初始化 `perf_event_open`
    for (i = 0; i < cpu_count; i++) {
        fds[i][0] = create_perf_event(i, -1, events[0], &ids[i][0]);
        if (fds[i][0] < 0) return -1;

        for (j = 1; j < NUM_EVENTS; j++) {
            fds[i][j] = create_perf_event(i, fds[i][0], events[j], &ids[i][j]);
            if (fds[i][j] < 0) return -1;
        }
    }

    // 采集循环
    while (!stop) {
        printf("\n==========  采样数据  ==========\n");

        // 重置计数器
        for (i = 0; i < cpu_count; i++) {
            for (j = 0; j < NUM_EVENTS; j++) {
                ioctl(fds[i][j], PERF_EVENT_IOC_RESET, 0);
                ioctl(fds[i][j], PERF_EVENT_IOC_ENABLE, 0);
            }
        }

        sleep(SAMPLE_INTERVAL); // 采样间隔

        // 停止采样
        for (i = 0; i < cpu_count; i++) {
            ioctl(fds[i][0], PERF_EVENT_IOC_DISABLE, 0);
        }

        // 读取数据
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
            for (j = 0; j < NUM_EVENTS; j++) {
                printf("  %s - Value: %lu\n", event_names[j], values[i][j]);
            }
        }
    }

    // 关闭文件描述符
    for (i = 0; i < cpu_count; i++) {
        for (j = 0; j < NUM_EVENTS; j++) close(fds[i][j]);
    }

    printf("采集结束\n");
    return 0;
}
